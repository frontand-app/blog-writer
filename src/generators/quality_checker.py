"""Quality checks for blog article generation."""

import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..schemas.output import OutputSchema, Section, Source


class QualityChecker:
    """Comprehensive quality checker for blog articles."""

    def __init__(self):
        """Initialize quality checker."""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.fixes: List[Tuple[str, str]] = []  # (field, fix_description)
        self.orphaned_citations_to_remove: Set[int] = set()

    def validate(self, output: OutputSchema, input_data) -> Tuple[bool, List[str], List[str]]:
        """
        Run all quality checks.

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []
        self.fixes = []
        self.orphaned_citations_to_remove = set()

        # Run all checks
        self._check_meta_tags(output)
        self._check_citations(output)
        self._check_html_structure(output)
        self._check_internal_links(output, input_data)
        self._check_word_count(output)
        self._check_duplicate_sources(output)
        self._check_section_structure(output)
        self._check_source_quality(output)
        self._check_content_quality(output, input_data)

        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings

    def _check_meta_tags(self, output: OutputSchema):
        """Check meta title and description length."""
        if len(output.meta_title) > 55:
            self.errors.append(
                f"Meta title too long ({len(output.meta_title)} chars, max 55): '{output.meta_title[:60]}...'"
            )
            # Suggest fix
            truncated = output.meta_title[:52].rsplit(" ", 1)[0] + "..."
            self.fixes.append(("meta_title", f"Truncate to: '{truncated}'"))

        if len(output.meta_description) > 130:
            self.errors.append(
                f"Meta description too long ({len(output.meta_description)} chars, max 130): '{output.meta_description[:135]}...'"
            )
            truncated = output.meta_description[:127].rsplit(" ", 1)[0] + "..."
            self.fixes.append(("meta_description", f"Truncate to: '{truncated}'"))

        if len(output.meta_title) < 30:
            self.warnings.append(f"Meta title might be too short ({len(output.meta_title)} chars)")

        if len(output.meta_description) < 50:
            self.warnings.append(f"Meta description might be too short ({len(output.meta_description)} chars)")

    def _check_citations(self, output: OutputSchema):
        """Check that citations match sources."""
        # Extract all citations from content
        citations_found: Set[int] = set()
        
        # Check intro
        citations_found.update(self._extract_citations(output.intro))
        
        # Check sections
        for section in output.sections:
            citations_found.update(self._extract_citations(section.content))
        
        # Check sources
        source_indices = {s.index for s in output.sources if s.index}
        
        # Find missing citations (sources without citations)
        missing_citations = source_indices - citations_found
        if missing_citations:
            self.warnings.append(
                f"Sources {sorted(missing_citations)} are not cited in the content"
            )
        
        # Find orphaned citations (citations without sources)
        orphaned_citations = citations_found - source_indices
        if orphaned_citations:
            # Instead of error, try to remove orphaned citations from content
            self.warnings.append(
                f"Citations {sorted(orphaned_citations)} reference non-existent sources - will be removed"
            )
            # Mark for removal (we'll handle this in a post-processing step)
            self.orphaned_citations_to_remove = orphaned_citations
        
        # Check citation format
        all_text = output.intro + " " + " ".join(s.content for s in output.sections)
        invalid_citations = re.findall(r"\[([^\]]+)\]", all_text)
        for citation in invalid_citations:
            if not re.match(r"^\d+(?:[\s,]+?\d+)*$", citation.strip()):
                if citation.strip() not in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
                    # Might be a link or other bracket, skip
                    continue

    def _extract_citations(self, text: str) -> Set[int]:
        """Extract citation numbers from text."""
        citations = set()
        # Match [1], [2], [1,2], [1 2], etc.
        matches = re.findall(r"\[(\d+(?:[\s,]+?\d+)*)\]", text)
        for match in matches:
            # Extract all numbers
            numbers = re.findall(r"\d+", match)
            citations.update(int(n) for n in numbers)
        return citations

    def _check_html_structure(self, output: OutputSchema):
        """Check HTML is well-formed."""
        all_html = output.intro + " " + " ".join(s.content for s in output.sections)
        
        # Check for markdown-style bold (**text**)
        markdown_bold = re.findall(r"\*\*[^*]+\*\*", all_html)
        if markdown_bold:
            self.errors.append(f"Markdown-style bold found (should use <strong>): {markdown_bold[:3]}")
        
        # Check for broken hrefs
        broken_hrefs = re.findall(r'href="([^"]*?)\s+([^"]*)"', all_html)
        if broken_hrefs:
            self.errors.append(f"Broken href attributes found: {len(broken_hrefs)} instances")
        
        # Check for unclosed tags (simplified check)
        # Count opening and closing tags for common elements
        tag_pairs = [
            ("<p>", "</p>"),
            ("<strong>", "</strong>"),
            ("<ul>", "</ul>"),
            ("<ol>", "</ol>"),
            ("<li>", "</li>"),
            ("<h2>", "</h2>"),
            ("<h3>", "</h3>"),
        ]
        
        for open_tag, close_tag in tag_pairs:
            open_count = all_html.count(open_tag)
            close_count = all_html.count(close_tag)
            if open_count != close_count:
                self.errors.append(f"Unmatched HTML tags: {open_tag} ({open_count}) vs {close_tag} ({close_count})")

    def _check_internal_links(self, output: OutputSchema, input_data):
        """Check internal links are valid."""
        all_html = output.intro + " " + " ".join(s.content for s in output.sections)
        
        # Extract internal links
        internal_links = re.findall(r'<a\s+href="([^"]+)"[^>]*>', all_html)
        
        # Check if internal links match provided links
        provided_links = set(input_data.links) if hasattr(input_data, 'links') else set()
        
        for link in internal_links:
            if link.startswith("/"):
                # Normalize link
                normalized = link.rstrip("/")
                if provided_links and normalized not in provided_links:
                    # Check if it's a close match
                    matches = [pl for pl in provided_links if normalized in pl or pl in normalized]
                    if not matches:
                        self.warnings.append(f"Internal link '{link}' not in provided links list")
        
        # Check for at least one internal link per section
        for i, section in enumerate(output.sections, 1):
            section_links = re.findall(r'<a\s+href="([^"]+)"[^>]*>', section.content)
            internal_in_section = [l for l in section_links if l.startswith("/")]
            if not internal_in_section and len(section.content) > 200:
                self.warnings.append(f"Section {i} ('{section.title[:50]}...') has no internal links")

    def _check_word_count(self, output: OutputSchema):
        """Check word count meets requirements."""
        def count_words(text: str) -> int:
            # Remove HTML tags for word count
            text_no_html = re.sub(r"<[^>]+>", "", text)
            return len(text_no_html.split())
        
        total_words = (
            count_words(output.intro) +
            sum(count_words(s.content) for s in output.sections)
        )
        
        if total_words < 1200:
            self.warnings.append(f"Total word count ({total_words}) is below recommended minimum (1200)")
        elif total_words > 1800:
            self.warnings.append(f"Total word count ({total_words}) exceeds recommended maximum (1800)")
        
        # Check intro length
        intro_words = count_words(output.intro)
        if intro_words < 80:
            self.warnings.append(f"Intro too short ({intro_words} words, recommended 80-120)")
        elif intro_words > 120:
            self.warnings.append(f"Intro too long ({intro_words} words, recommended 80-120)")

    def _check_duplicate_sources(self, output: OutputSchema):
        """Check for duplicate sources."""
        seen_urls: Set[str] = set()
        seen_domains: Set[str] = set()
        
        for source in output.sources:
            # Check duplicate URLs
            normalized_url = source.url.lower().rstrip("/")
            if normalized_url in seen_urls:
                self.errors.append(f"Duplicate source URL: {source.url}")
            seen_urls.add(normalized_url)
            
            # Check domain diversity
            domain = urlparse(source.url).netloc.lower().lstrip("www.")
            seen_domains.add(domain)
        
        # Warn if too many sources from same domain
        domain_counts: Dict[str, int] = {}
        for source in output.sources:
            domain = urlparse(source.url).netloc.lower().lstrip("www.")
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        for domain, count in domain_counts.items():
            if count > 3:
                self.warnings.append(f"Too many sources ({count}) from same domain: {domain}")

    def _check_section_structure(self, output: OutputSchema):
        """Check section structure."""
        if len(output.sections) < 2:
            self.errors.append(f"Too few sections ({len(output.sections)}, minimum 2)")
        elif len(output.sections) > 9:
            self.warnings.append(f"Too many sections ({len(output.sections)}, maximum 9)")
        
        # Check section titles
        for i, section in enumerate(output.sections, 1):
            if not section.title:
                self.errors.append(f"Section {i} has no title")
            elif len(section.title) > 100:
                self.warnings.append(f"Section {i} title too long ({len(section.title)} chars)")
            
            if not section.content:
                self.errors.append(f"Section {i} ('{section.title}') has no content")
        
        # Check for lists in sections
        list_count = 0
        for section in output.sections:
            if "<ul>" in section.content or "<ol>" in section.content:
                list_count += 1
        
        if list_count < 2:
            self.warnings.append(f"Too few sections with lists ({list_count}, recommended 2-4)")
        elif list_count > 4:
            self.warnings.append(f"Too many sections with lists ({list_count}, recommended 2-4)")

    def _check_source_quality(self, output: OutputSchema):
        """Check source quality."""
        if len(output.sources) < 8:
            self.warnings.append(f"Too few sources ({len(output.sources)}, recommended minimum 8)")
        elif len(output.sources) > 20:
            self.warnings.append(f"Too many sources ({len(output.sources)}, maximum 20)")
        
        # Check source titles
        for source in output.sources:
            if not source.title or len(source.title) < 5:
                self.warnings.append(f"Source {source.index} has invalid title: '{source.title}'")
            
            if len(source.title) > 200:
                self.warnings.append(f"Source {source.index} title too long ({len(source.title)} chars)")

    def _check_content_quality(self, output: OutputSchema, input_data):
        """Check overall content quality."""
        # Check key takeaways
        if len(output.key_takeaways) < 2:
            self.warnings.append(f"Too few key takeaways ({len(output.key_takeaways)}, recommended 2-3)")
        
        # Check FAQs
        if len(output.faq) < 3:
            self.warnings.append(f"Too few FAQs ({len(output.faq)}, recommended 3-6)")
        
        # Check PAA
        if len(output.paa) < 2:
            self.warnings.append(f"Too few PAA items ({len(output.paa)}, recommended 2-4)")
        
        # Check for primary keyword in content
        if hasattr(input_data, 'primary_keyword') and input_data.primary_keyword:
            keyword = input_data.primary_keyword.lower()
            all_text = (
                output.headline + " " + output.intro + " " +
                " ".join(s.content for s in output.sections)
            ).lower()
            
            # Remove HTML for keyword check
            all_text_no_html = re.sub(r"<[^>]+>", "", all_text)
            keyword_count = all_text_no_html.count(keyword)
            
            if keyword_count == 0:
                self.errors.append(f"Primary keyword '{input_data.primary_keyword}' not found in content")
            elif keyword_count < 3:
                self.warnings.append(f"Primary keyword '{input_data.primary_keyword}' appears only {keyword_count} times")

    def apply_fixes(self, output: OutputSchema) -> OutputSchema:
        """Apply automatic fixes to output."""
        import re
        
        # Apply meta title fix
        if len(output.meta_title) > 55:
            truncated = output.meta_title[:52].rsplit(" ", 1)[0] + "..."
            output.meta_title = truncated
        
        # Apply meta description fix
        if len(output.meta_description) > 130:
            truncated = output.meta_description[:127].rsplit(" ", 1)[0] + "..."
            output.meta_description = truncated
        
        # Remove orphaned citations from content
        if self.orphaned_citations_to_remove:
            # Remove citations from intro
            for cit_num in self.orphaned_citations_to_remove:
                output.intro = re.sub(rf'\[{cit_num}\]', '', output.intro)
                output.intro = re.sub(rf'\[{cit_num},\s*', '[', output.intro)
                output.intro = re.sub(rf',\s*{cit_num}\]', ']', output.intro)
                output.intro = re.sub(rf'\[{cit_num}\s+', '[', output.intro)
                output.intro = re.sub(rf'\s+{cit_num}\]', ']', output.intro)
            
            # Remove citations from sections
            for section in output.sections:
                for cit_num in self.orphaned_citations_to_remove:
                    section.content = re.sub(rf'\[{cit_num}\]', '', section.content)
                    section.content = re.sub(rf'\[{cit_num},\s*', '[', section.content)
                    section.content = re.sub(rf',\s*{cit_num}\]', ']', section.content)
                    section.content = re.sub(rf'\[{cit_num}\s+', '[', section.content)
                    section.content = re.sub(rf'\s+{cit_num}\]', ']', section.content)
        
        return output

