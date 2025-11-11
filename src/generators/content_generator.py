"""Main content generator for blog articles."""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions

from ..agents.validator import ValidatorAgent
from ..config import Config
from ..schemas.input import InputSchema
from ..schemas.output import OutputSchema, Section, FAQItem, PAAItem, Source
from .post_processor import sanitize_citations, format_literature, sanitize_output, clean_html_content
from .quality_checker import QualityChecker
from ..utils.helpers import count_words, estimate_read_time, generate_random_date


class ContentGenerator:
    """Main content generator for blog articles."""

    def __init__(self, config: Optional[Config] = None, api_key: Optional[str] = None):
        """
        Initialize the content generator.

        Args:
            config: Configuration object (optional)
            api_key: Google AI API key (optional, uses config if not provided)
        """
        import requests
        self.config = config or Config()
        self.api_key = api_key or self.config.get_api_key()
        self.validator_agent = ValidatorAgent(api_key=self.api_key)
        self._client = None
        # Create HTTP session with connection pooling for better performance
        self._http_session = requests.Session()
        self._http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    @property
    def client(self):
        """Get or create the Gemini client."""
        if self._client is None:
            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
            else:
                self._client = genai.Client(http_options=HttpOptions(api_version="v1"))
        return self._client

    def generate(self, input_data: InputSchema) -> OutputSchema:
        """
        Generate a complete blog article.

        Args:
            input_data: Input schema with all required parameters

        Returns:
            OutputSchema with generated content
        """
        # Generate main content
        content_json = self._generate_content(input_data)

        # Validate and enrich sources
        sources = self._process_sources(content_json, input_data)

        # Parse sections
        sections = self._parse_sections(content_json)

        # Parse FAQs
        faq_items = self._parse_faqs(content_json)

        # Parse PAA
        paa_items = self._parse_paa(content_json)

        # Parse key takeaways
        key_takeaways = self._parse_key_takeaways(content_json)

        # Parse search queries
        search_queries = self._parse_search_queries(content_json)

        # Calculate read time
        total_words = self._calculate_total_words(content_json)
        read_time = estimate_read_time(total_words)

        # Generate date
        date = generate_random_date()

        # Format literature
        literature = format_literature(sources)

        # Extract and clean intro
        intro = content_json.get("Intro", "")
        intro = clean_html_content(intro)

        # Clean section content
        for section in sections:
            section.content = clean_html_content(section.content)

        # Generate HTML
        html = self._generate_html(
            headline=content_json.get("Headline", ""),
            subtitle=content_json.get("Subtitle", ""),
            teaser=content_json.get("Teaser", ""),
            intro=intro,
            sections=sections,
            key_takeaways=key_takeaways,
            literature=literature,
            search_queries=search_queries,
        )

        # Build output schema
        output = OutputSchema(
            headline=content_json.get("Headline", ""),
            subtitle=content_json.get("Subtitle"),
            teaser=content_json.get("Teaser", ""),
            intro=intro,
            meta_title=content_json.get("Meta Title", ""),
            meta_description=content_json.get("Meta Description", ""),
            sections=sections,
            key_takeaways=key_takeaways,
            faq=faq_items,
            paa=paa_items,
            sources=sources,
            search_queries=search_queries,
            read_time=read_time,
            date=date,
            literature=literature,
            html=html,
        )

        # Run quality checks
        quality_checker = QualityChecker()
        is_valid, errors, warnings = quality_checker.validate(output, input_data)
        
        # Apply automatic fixes FIRST (before checking errors)
        output = quality_checker.apply_fixes(output)
        
        # Re-validate after fixes (in case fixes introduced new issues)
        is_valid_after_fixes, errors_after_fixes, warnings_after_fixes = quality_checker.validate(output, input_data)
        
        # Log warnings (non-blocking)
        all_warnings = warnings + warnings_after_fixes
        if all_warnings:
            import logging
            logger = logging.getLogger(__name__)
            for warning in all_warnings:
                logger.warning(f"Quality warning: {warning}")
        
        # If critical errors remain after fixes, raise exception
        if errors_after_fixes:
            error_msg = "Quality check failed after automatic fixes:\n" + "\n".join(f"  - {e}" for e in errors_after_fixes)
            raise ValueError(error_msg)
        
        return output

    def _generate_content(self, input_data: InputSchema) -> Dict:
        """Generate main content using Gemini."""
        prompt = self._build_prompt(input_data)

        model_id = self.config.content_model
        cfg = GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=65536,
        )

        response = self.client.models.generate_content(
            model=model_id,
            contents=[prompt],
            config=cfg,
        )

        # Extract text from response
        text = self._extract_text_from_response(response)

        # Parse JSON from response
        return self._parse_json_response(text)

    def _build_prompt(self, input_data: InputSchema) -> str:
        """Build the content generation prompt."""
        internal_links_str = ", ".join(input_data.links) if input_data.links else ""
        competitors_str = json.dumps(input_data.company_competitors)
        company_info_str = json.dumps(input_data.company_info)

        prompt = f"""*** INPUT ***
Primary Keyword: {input_data.primary_keyword};
Content Generation Instructions: {input_data.content_generation_instruction};
Company Info: {company_info_str};
Output Language: {input_data.company_language};
Target Country: {input_data.company_location};
Company URL: {input_data.company_url};
Competitors: {competitors_str};
Internal Links: {internal_links_str};

*** TASK ***
You are writing a long-form blog post in {input_data.company_name}'s voice, fully optimised for LLM discovery, on the topic defined by **Primary Keyword**.

*** CONTENT RULES ***
1. Word count flexible (~1 200–1 800) – keep storyline tight, info-dense.
2. One-sentence hook → two-sentence summary.
3. Create a <h2> "Key Takeaways" part into the dedicated variables.
4. New H2/H3 every 150–200 words; headings packed with natural keywords.
5. Every paragraph ≤ 25 words & ≥ 90 % active voice, and **must contain** a number, KPI or real example.
6. **Primary Keyword** must appear **naturally** (variations/inflections allowed for grammar and readability; no keyword stuffing).
7. **NEVER** embed PAA, FAQ or Key Takeaways inside sections or section titles, intro or teaser; they live in separate JSON keys.
8. **Internal links**: at least one per H2 block, woven seamlessly into the surrounding sentence.  
   Example: `<a href="/target-slug">Descriptive Anchor</a>` (≤ 6 words, varied). ENSURE correct html format.
9. Citations in-text as [1], [2]… matching the **Sources** list. MAX 20 sources. STRICT citation format in text [1],[2],[4][9].
10. Highlight 1–2 insights per section with `<strong>…</strong>` (never `**…**`).
11. Follow instructions from **Content Generation Instructions**.
12. Rename each title to a McKinsey/BCG-style action title (concise, data/benefit-driven; **no HTML in titles**).
13. In **2–4 sections**, insert either an HTML bulleted (`<ul>`) or numbered (`<ol>`) list **introduced by one short lead-in sentence**; 4–8 items per list.
14. Avoid repetition—vary examples, phrasing and data across sections.
15. **Narrative flow**: end every section with one bridging sentence that naturally sets up the next section.

*** SOURCES ***
• Minimum 8 authoritative references for {input_data.company_location}.  
• One line each: `[1]: https://… – 8–15-word note` (canonical URLs only).

*** SEARCH QUERIES ***
• One line each: `Q1: keyword phrase …`

*** HARD RULES ***
• Keep all HTML tags intact (<p>, <ul>, <ol>, <h2>, <h3> …).  
• No extra keys, comments or process explanations.  
• **Meta Description CTA** must be clear, actionable and grounded in company info—no vague buzzwords.  
• Always follow the Content Generation Instructions, even if other sources differ.  
• JSON must be valid and minified (no line breaks inside values).    
• Maximum 3 citations per section (if more facts, cite at end of paragraph).  
• IMPORTANT: Whole textual Output language = {input_data.company_language}.
• NEVER create the article sections using this kind of text structure using <p>, this text looks terrible in rendered html (overuse of <p> for each sentence): </p><p>It supports continuous manufacturing, increasing throughput by up to 50%. [1]</p><p>This efficiency directly translates to reduced production costs per dose of at least 10%.</p><p>Ethris and Lonza are collaborating on scalable spray-dried mRNA vaccines. [3]</p><p><strong>Many overlook the 20% reduction in facility footprint with continuous systems.</strong></p>;
• **NEVER** embed PAA, FAQ or Key Takeaways inside sections or section titles, intro or teaser; they live in separate JSON keys.
• **NEVER** mention or link to competing companies (Competitors) in the article.

*** OUTPUT ***
Please separate the generated content into the output fields and ensure all required output fields are generated.

***IMPORTANT OUTPUT RULES***
- **NEVER** embed PAA, FAQ or Key Takeaways inside section_XX_content or section_XX_title, intro or teaser; they live in separate JSON keys.

ENSURE correct JSON output format
Output format:

```json
{{
  "Headline": "Concise, eye-catching headline that states the main topic and includes the primary keyword",
  "Subtitle": "Optional sub-headline that adds context or a fresh angle",
  "Teaser": "2–3-sentence hook that highlights a pain point or benefit and invites readers to continue",
  "Intro": "Brief opening paragraph (≈80–120 words) that frames the problem, shows relevance, and previews the value",
  "Meta Title": "≤55-character SEO title with the primary keyword and (optionally) brand",
  "Meta Description": "≤130-character SEO description summarising the benefit and including a CTA",
  "section_01_title": "Logical Section 01 Heading (H2)",
  "section_01_content": "HTML content for Section 01. Separate the article logically; wrap each paragraph in <p>. Leave unused sections blank.",
  "section_02_title": "Logical Section 02 Heading",
  "section_02_content": "",
  "section_03_title": "",
  "section_03_content": "",
  "section_04_title": "",
  "section_04_content": "",
  "section_05_title": "",
  "section_05_content": "",
  "section_06_title": "",
  "section_06_content": "",
  "section_07_title": "",
  "section_07_content": "",
  "section_08_title": "",
  "section_08_content": "",
  "section_09_title": "",
  "section_09_content": "",

  "key_takeaway_01": "Key point or insight #1 (1 sentence). Leave unused takeaways blank.",
  "key_takeaway_02": "",
  "key_takeaway_03": "",

  "paa_01_question": "People also ask question #1",
  "paa_01_answer": "Concise answer to question #1.",
  "paa_02_question": "",
  "paa_02_answer": "",
  "paa_03_question": "",
  "paa_03_answer": "",
  "paa_04_question": "",
  "paa_04_answer": "",

  "faq_01_question": "Main FAQ question #1",
  "faq_01_answer": "Clear, concise answer.",
  "faq_02_question": "",
  "faq_02_answer": "",
  "faq_03_question": "",
  "faq_03_answer": "",
  "faq_04_question": "",
  "faq_04_answer": "",
  "faq_05_question": "",
  "faq_05_answer": "",
  "faq_06_question": "",
  "faq_06_answer": "",

  "Sources": "[1]: https://… – 8-15-word note. List one source per line; leave blank until populated. LIMIT TO 20 sources",
  "Search Queries": "Q1: keyword …  List one query per line; leave blank until populated."
}}
```

ALWAYS AT ANY TIMES STRICTLY OUTPUT IN THE JSON FORMAT. No extra keys or commentary."""

        return prompt

    def _extract_text_from_response(self, response) -> str:
        """Extract text from Gemini response."""
        try:
            return response.text
        except AttributeError:
            # Fallback for different response formats
            candidates = getattr(response, "candidates", [])
            if candidates:
                content = getattr(candidates[0], "content", {})
                parts = getattr(content, "parts", [])
                if parts:
                    return getattr(parts[0], "text", "")
        return ""

    def _parse_json_response(self, text: str) -> Dict:
        """Parse JSON from response text."""
        # Try to find JSON in the response
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try to extract JSON from code blocks
        code_block_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Fallback: return empty dict
        return {}

    def _process_sources(self, content_json: Dict, input_data: InputSchema) -> List[Source]:
        """Process and validate sources."""
        sources_text = content_json.get("Sources", "")
        if not sources_text:
            return []

        # Parse all sources first
        parsed_sources = []
        lines = sources_text.strip().split("\n")
        for idx, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            # Parse source line: [1]: https://... – description
            match = re.match(r"\[(\d+)\]:\s*(https?://[^\s]+)\s*[–-]\s*(.+)", line)
            if match:
                source_idx, url, description = match.groups()
                parsed_sources.append({
                    "index": int(source_idx),
                    "url": url,
                    "title": description.strip(),
                })

        if not parsed_sources:
            return []

        # Validate URLs concurrently for better performance
        validated_sources = self._validate_sources_concurrent(
            parsed_sources[:20],  # Limit to 20 sources
            input_data
        )
        
        return validated_sources

    def _validate_source_url(
        self,
        url: str,
        original_title: str,
        company_url: str,
        competitors: List[str],
    ) -> Tuple[bool, str, str]:
        """
        Validate a source URL.
        
        Returns:
            Tuple of (is_valid, final_url, final_title)
        """
        try:
            from urllib.parse import urlparse
            
            # Parse and normalize URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False, url, original_title
            
            host = parsed.netloc.lower().lstrip(".").removeprefix("www.")
            
            # Check forbidden hosts
            forbidden = {"vertexaisearch.cloud.google.com", "cloud.google.com"}
            if host in forbidden:
                return False, url, original_title
            
            # Exclude company domain
            if company_url:
                company_host = urlparse(company_url).netloc.lower().lstrip(".").removeprefix("www.")
                if host == company_host or host.endswith("." + company_host):
                    return False, url, original_title
            
            # Exclude competitors
            for competitor in competitors:
                comp_url = competitor if competitor.startswith("http") else f"https://{competitor}"
                comp_host = urlparse(comp_url).netloc.lower().lstrip(".").removeprefix("www.")
                if host == comp_host or host.endswith("." + comp_host):
                    return False, url, original_title
            
            # Check HTTP status (HEAD request, fallback to GET)
            try:
                response = self._http_session.head(url, allow_redirects=True, timeout=8)
                
                # Check for 404 or error pages
                final_url = response.url
                if response.status_code == 200:
                    # For HEAD requests, we need to check URL path for error indicators
                    # Full content check will happen in GET request below
                    url_lower = final_url.lower()
                    error_url_patterns = ['/notfound', '/not-found', '/404', '/error', 'notfound.aspx', '/notfound.aspx']
                    if any(pattern in url_lower for pattern in error_url_patterns):
                        return False, url, original_title
                    
                    # Do GET request to check content and get title
                    get_response = self._http_session.get(final_url, timeout=8)
                    if get_response.status_code == 200:
                        if self._is_error_page(final_url, get_response):
                            return False, url, original_title
                        title = self._extract_title_from_response(get_response) or original_title
                        return True, final_url, title
                elif response.status_code in (301, 302, 303, 307, 308):
                    # Follow redirect
                    final_url = response.url
                    get_response = self._http_session.get(final_url, timeout=8)
                    if get_response.status_code == 200:
                        if self._is_error_page(final_url, get_response):
                            return False, url, original_title
                        title = self._extract_title_from_response(get_response) or original_title
                        return True, final_url, title
                elif response.status_code == 404:
                    return False, url, original_title
            except requests.RequestException:
                pass
            
            # If HEAD fails, try GET
            try:
                response = self._http_session.get(url, allow_redirects=True, timeout=8)
                if response.status_code == 200:
                    final_url = response.url
                    # Check for error pages
                    if self._is_error_page(final_url, response):
                        return False, url, original_title
                    title = self._extract_title_from_response(response) or original_title
                    return True, final_url, title
                elif response.status_code == 404:
                    return False, url, original_title
            except requests.RequestException:
                pass
            
            return False, url, original_title
            
        except Exception:
            return False, url, original_title

    def _is_error_page(self, url: str, response) -> bool:
        """Check if URL is an error page (404, etc.)."""
        try:
            # Check URL path for error indicators
            error_indicators = [
                '/notfound', '/not-found', '/404', '/error', '/page-not-found',
                'notfound.aspx', '404.aspx', 'error.aspx', 'page-not-found.aspx',
                '/NotFound', '/NotFound.aspx', 'NotFound.aspx'
            ]
            url_lower = url.lower()
            if any(indicator.lower() in url_lower for indicator in error_indicators):
                return True
            
            # Check response content for error page indicators
            if hasattr(response, 'text') and response.text:
                content_lower = response.text.lower()
                error_phrases = [
                    'page not found', '404', 'not found', 'error 404',
                    'die seite wurde nicht gefunden', 'seite nicht gefunden',
                    'page introuvable', 'página no encontrada', 'nicht gefunden'
                ]
                # If multiple error phrases found, it's likely an error page
                error_count = sum(1 for phrase in error_phrases if phrase in content_lower)
                if error_count >= 2:
                    return True
                
                # Check title for error indicators
                title_match = re.search(r'<title[^>]*>(.*?)</title>', response.text, re.IGNORECASE | re.DOTALL)
                if title_match:
                    title = title_match.group(1).lower()
                    error_title_phrases = ['not found', '404', 'error', 'nicht gefunden', 'page not found']
                    if any(phrase in title for phrase in error_title_phrases):
                        return True
            
            # Check status code
            if hasattr(response, 'status_code'):
                if response.status_code in (404, 410, 500, 503):
                    return True
            
            return False
        except Exception:
            return False

    def _extract_title_from_response(self, response) -> Optional[str]:
        """Extract title from response object."""
        try:
            from html import unescape
            if response.status_code == 200 and "text/html" in response.headers.get("Content-Type", ""):
                match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.IGNORECASE | re.DOTALL)
                if match:
                    title = unescape(match.group(1)).strip()
                    title = re.sub(r"\s+", " ", title)
                    if len(title) > 140:
                        title = title[:137] + "..."
                    return title
        except Exception:
            pass
        return None

    def _validate_sources_concurrent(
        self,
        parsed_sources: List[Dict],
        input_data: InputSchema
    ) -> List[Source]:
        """
        Validate sources concurrently using thread pool.
        
        Args:
            parsed_sources: List of source dicts with 'url', 'title', 'index'
            input_data: Input schema with company info
            
        Returns:
            List of validated Source objects
        """
        validated_sources = []
        invalid_sources = []
        
        # Validate all URLs concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all validation tasks
            future_to_source = {
                executor.submit(
                    self._validate_source_url,
                    url=source["url"],
                    original_title=source["title"],
                    company_url=input_data.company_url,
                    competitors=input_data.company_competitors,
                ): source
                for source in parsed_sources
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    is_valid, validated_url, validated_title = future.result()
                    if is_valid:
                        validated_sources.append(
                            Source(
                                url=validated_url,
                                title=validated_title,
                                index=source["index"],
                            )
                        )
                    else:
                        invalid_sources.append(source)
                except Exception:
                    invalid_sources.append(source)
        
        # Try to replace invalid URLs (limit to first 3 to avoid performance issues)
        if invalid_sources:
            replacement_sources = self._find_replacements_concurrent(
                invalid_sources[:3],
                input_data
            )
            validated_sources.extend(replacement_sources)
        
        # Sort by index to maintain order
        validated_sources.sort(key=lambda s: s.index)
        return validated_sources
    
    def _find_replacements_concurrent(
        self,
        invalid_sources: List[Dict],
        input_data: InputSchema
    ) -> List[Source]:
        """
        Find replacement URLs concurrently for invalid sources.
        
        Args:
            invalid_sources: List of invalid source dicts
            input_data: Input schema
            
        Returns:
            List of replacement Source objects
        """
        replacement_sources = []
        
        # Use thread pool to search for replacements concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_source = {
                executor.submit(
                    self.validator_agent.validate_urls,
                    query=f"{input_data.primary_keyword} {source['title']}",
                    company_url=input_data.company_url,
                    competitors=input_data.company_competitors,
                    language=input_data.company_language,
                    max_results=1,
                ): source
                for source in invalid_sources
            }
            
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    replacement = future.result()
                    if replacement:
                        replacement_sources.append(
                            Source(
                                url=replacement[0]["url"],
                                title=replacement[0]["url_meta_title"],
                                index=source["index"],
                            )
                        )
                except Exception:
                    pass  # Skip if replacement fails
        
        return replacement_sources

    def _fetch_url_title(self, url: str) -> Optional[str]:
        """Fetch page title from URL."""
        try:
            response = self._http_session.get(url, timeout=8)
            
            # Don't fetch title for error pages
            if self._is_error_page(url, response):
                return None
                
            return self._extract_title_from_response(response)
        except Exception:
            pass
        return None


    def _parse_sections(self, content_json: Dict) -> List[Section]:
        """Parse sections from content JSON."""
        sections = []
        for i in range(1, 10):
            title_key = f"section_{i:02d}_title"
            content_key = f"section_{i:02d}_content"
            title = content_json.get(title_key, "").strip()
            content = content_json.get(content_key, "").strip()

            if title or content:
                sections.append(Section(title=title, content=content))

        return sections

    def _parse_faqs(self, content_json: Dict) -> List[FAQItem]:
        """Parse FAQ items from content JSON."""
        faqs = []
        for i in range(1, 7):
            question_key = f"faq_{i:02d}_question"
            answer_key = f"faq_{i:02d}_answer"
            question = content_json.get(question_key, "").strip()
            answer = content_json.get(answer_key, "").strip()

            if question and answer:
                faqs.append(FAQItem(question=question, answer=answer))

        return faqs

    def _parse_paa(self, content_json: Dict) -> List[PAAItem]:
        """Parse PAA items from content JSON."""
        paa_items = []
        for i in range(1, 5):
            question_key = f"paa_{i:02d}_question"
            answer_key = f"paa_{i:02d}_answer"
            question = content_json.get(question_key, "").strip()
            answer = content_json.get(answer_key, "").strip()

            if question and answer:
                paa_items.append(PAAItem(question=question, answer=answer))

        return paa_items

    def _parse_key_takeaways(self, content_json: Dict) -> List[str]:
        """Parse key takeaways from content JSON."""
        takeaways = []
        for i in range(1, 4):
            key = f"key_takeaway_{i:02d}"
            value = content_json.get(key, "").strip()
            if value:
                takeaways.append(value)

        return takeaways

    def _parse_search_queries(self, content_json: Dict) -> List[str]:
        """Parse search queries from content JSON."""
        queries_text = content_json.get("Search Queries", "")
        if not queries_text:
            return []

        queries = []
        lines = queries_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and line.startswith("Q"):
                # Extract query after "Q1: " or similar
                match = re.match(r"Q\d+:\s*(.+)", line)
                if match:
                    queries.append(match.group(1).strip())

        return queries

    def _calculate_total_words(self, content_json: Dict) -> int:
        """Calculate total word count."""
        total = 0
        for key, value in content_json.items():
            if isinstance(value, str):
                total += count_words(value)
        return total

    def _generate_html(
        self,
        headline: str,
        subtitle: str,
        teaser: str,
        intro: str,
        sections: List[Section],
        key_takeaways: List[str],
        literature: str,
        search_queries: List[str],
    ) -> str:
        """Generate HTML output."""
        sections_html = ""
        for section in sections:
            if section.title:
                sections_html += f'<section id="section{section.title[:20]}">\n'
                sections_html += f"<h2>{section.title}</h2>\n"
                sections_html += f"{section.content}\n"
                sections_html += "</section>\n\n"

        takeaways_html = ""
        if key_takeaways:
            takeaways_html = "<section class=\"key-takeaways\">\n<h2>Key Takeaways</h2>\n<ul>\n"
            for takeaway in key_takeaways:
                takeaways_html += f"<li>{takeaway}</li>\n"
            takeaways_html += "</ul>\n</section>\n"

        queries_html = ""
        if search_queries:
            queries_html = "<section class=\"queries\">\n<h2>Search Queries</h2>\n<ul>\n"
            for query in search_queries:
                queries_html += f"<li>{query}</li>\n"
            queries_html += "</ul>\n</section>\n"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{headline}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body{{font-family:Arial, sans-serif;line-height:1.5;margin:0;padding:20px;color:#333;}}
    article{{max-width:800px;margin:0 auto;}}
    h1{{font-size:2em;margin-bottom:0.3em;}}
    h2{{font-size:1.6em;margin-top:1em;color:#222;}}
    h3{{font-size:1.3em;margin-top:0.8em;color:#444;}}
    .key-takeaways ul{{padding-left:20px;}}
    .sources{{font-size:0.9em;margin:24px 0;white-space:pre-wrap;}}
  </style>
</head>
<body>
  <article>
    <header>
      <h1>{headline}</h1>
      {f'<h2>{subtitle}</h2>' if subtitle else ''}
      <p class="teaser">{teaser}</p>
      {intro}
    </header>

{sections_html}

{takeaways_html}

    <section class="sources">
      <h2>Literature</h2>
      {literature}
    </section>

{queries_html}

  </article>
</body>
</html>"""

        return html

