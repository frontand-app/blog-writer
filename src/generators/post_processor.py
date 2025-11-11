"""Post-processing utilities for blog articles."""

import re
from typing import Dict, Any


def sanitize_citations(text: str) -> str:
    """
    Remove citation brackets like [1], [2 3], [9,10] from text.

    Args:
        text: Text with citations

    Returns:
        Text without citations
    """
    # Remove numbered citations
    pattern = r"\[\s*\d+(?:[\s,]+\d+)*\s*\]"
    text = re.sub(pattern, "", text)
    # Remove empty brackets
    text = re.sub(r"\[\s*\]", "", text)
    return text.strip()


def clean_html_content(text: str) -> str:
    """
    Clean HTML content by removing markdown-style bold and fixing common issues.

    Args:
        text: HTML text to clean

    Returns:
        Cleaned HTML text
    """
    if not text:
        return text
    
    # Remove markdown-style bold (**text**)
    text = re.sub(r"\*\*([^*]*)\*\*", r"<strong>\1</strong>", text)
    
    # Convert markdown-style emphasis (*text*) to <em> tags
    # Match *word* patterns but avoid matching within HTML tags or URLs
    # Use negative lookbehind/lookahead to avoid matching inside tags
    text = re.sub(r'(?<!<)(?<!\*)\*([^*<>]+?)\*(?!\*)(?![^<]*>)', r'<em>\1</em>', text)

    # Fix broken href attributes with whitespace
    text = re.sub(r'href="([^"]*?)\s+([^"]*)"', r'href="\1\2"', text)
    
    # Ensure text is wrapped in <p> tags if it's plain text
    text = text.strip()
    if text and not text.startswith("<"):
        text = f"<p>{text}</p>"
    
    # Fix multiple consecutive <p> tags
    text = re.sub(r"</p>\s*<p>", " ", text)
    
    return text


def format_literature(sources: list) -> str:
    """
    Format sources into HTML literature format.

    Args:
        sources: List of Source objects or dicts with 'url', 'title', and optionally 'index'

    Returns:
        Formatted HTML string
    """
    if not sources:
        return ""

    formatted = []
    for idx, source in enumerate(sources, 1):
        # Handle both Pydantic models and dicts
        if hasattr(source, 'url'):
            # Pydantic model
            url = source.url
            title = source.title
            index = source.index if hasattr(source, 'index') and source.index else idx
        else:
            # Dict
            url = source.get("url", "")
            title = source.get("title", source.get("url_meta_title", f"Source {idx}"))
            index = source.get("index", idx)
        
        formatted.append(f'<p>[{index}]: <a href="{url}" target="_blank">{title}</a></p>')

    return "".join(formatted)


def sanitize_output(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize output data by cleaning citations and HTML.

    Args:
        data: Output data dictionary

    Returns:
        Sanitized data dictionary
    """
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned[key] = sanitize_citations(clean_html_content(value))
        elif isinstance(value, dict):
            cleaned[key] = sanitize_output(value)
        elif isinstance(value, list):
            cleaned[key] = [
                sanitize_output(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned

