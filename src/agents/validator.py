"""URL Validator Agent using Gemini with Google Search grounding."""

from __future__ import annotations

import os
import re
from html import unescape
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl

import requests
from google import genai
from google.genai.types import GenerateContentConfig, Tool, GoogleSearch, HttpOptions


FORBIDDEN_HOSTS: Set[str] = {
    "vertexaisearch.cloud.google.com",
    "cloud.google.com",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class ValidatorAgent:
    """URL validator agent using Gemini 2.5 Flash with Google Search grounding."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the validator agent.

        Args:
            api_key: Google AI API key. If None, uses GOOGLE_API_KEY env var or Vertex AI.
        """
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client = None

    @property
    def client(self):
        """Get or create the Gemini client."""
        if self._client is None:
            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
            else:
                self._client = genai.Client(http_options=HttpOptions(api_version="v1"))
        return self._client

    def validate_urls(
        self,
        query: str,
        company_url: Optional[str] = None,
        competitors: Iterable[str] = (),
        language: str = "en",
        max_results: int = 3,
    ) -> List[dict]:
        """
        Search and validate URLs for a given query.

        Args:
            query: Search query/topic
            company_url: Company URL to exclude from results
            competitors: List of competitor domains to exclude
            language: Language code for meta titles
            max_results: Maximum number of URLs to return

        Returns:
            List of dicts with 'url' and 'url_meta_title' keys
        """
        resp = self._call_gemini_with_search(query)
        grounded = self._grounded_sources_from_response(resp)
        uris = [u for (_t, u) in grounded]

        valid_urls = self._filter_and_validate_urls(uris, company_url, set(competitors))
        valid_urls = valid_urls[:max_results]

        results = []
        for url in valid_urls:
            meta = self._make_meta_title(url, language)
            results.append({"url": url, "url_meta_title": meta})
        return results

    def _call_gemini_with_search(self, user_query: str):
        """Call Gemini with Google Search grounding."""
        model_id = "gemini-2.5-flash"
        cfg = GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch())],
            temperature=1.0,
            response_modalities=["TEXT"],
        )
        system_hint = (
            "When answering, use Google Search grounding and prefer authoritative, "
            "non-competitive, external sources. "
            "Avoid using vertexaisearch.cloud.google.com and cloud.google.com as final citations."
        )
        contents = [system_hint, user_query]
        return self.client.models.generate_content(model=model_id, contents=contents, config=cfg)

    def _grounded_sources_from_response(self, resp) -> List[Tuple[str, str]]:
        """Extract (title, uri) pairs from grounding metadata."""
        out: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        try:
            cand = resp.candidates[0]
            gm = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None)
            if not gm:
                return out
            chunks = getattr(gm, "grounding_chunks", None) or getattr(gm, "groundingChunks", None)
            if not chunks:
                return out
            for ch in chunks:
                web = getattr(ch, "web", None)
                if not web:
                    continue
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None) or ""
                if uri and uri not in seen:
                    out.append((title, uri))
                    seen.add(uri)
        except Exception:
            pass
        return out

    def _normalize_hostname(self, url: str) -> str:
        """Normalize hostname for comparison."""
        try:
            host = urlparse(url).hostname or ""
            return host.lower().lstrip(".").removeprefix("www.")
        except Exception:
            return ""

    def _is_same_or_subdomain(self, host: str, root: str) -> bool:
        """Check if host is same or subdomain of root."""
        if not host or not root:
            return False
        host = host.lower()
        root = root.lower().lstrip(".")
        return host == root or host.endswith("." + root)

    def _unwrap_redirect(self, url: str, timeout: float = 8.0) -> str:
        """Follow redirects to reveal final destination."""
        try:
            with requests.Session() as s:
                s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
                resp = s.head(url, allow_redirects=True, timeout=timeout)
                if resp.ok:
                    return resp.url
                resp = s.get(url, allow_redirects=True, timeout=timeout)
                if resp.ok:
                    return resp.url
        except requests.RequestException:
            pass
        return url

    def _check_url_ok(self, url: str, timeout: float = 8.0) -> bool:
        """Check if URL returns HTTP 200."""
        try:
            with requests.Session() as s:
                s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
                r = s.head(url, allow_redirects=True, timeout=timeout)
                if r.status_code == 200:
                    return True
                r = s.get(url, allow_redirects=True, timeout=timeout)
                return r.status_code == 200
        except requests.RequestException:
            return False

    def _strip_utm_params(self, u: str) -> str:
        """Remove common tracking parameters."""
        try:
            p = urlparse(u)
            q = [
                (k, v)
                for k, v in parse_qsl(p.query, keep_blank_values=True)
                if not (k.lower().startswith("utm_") or k.lower() in {"gclid", "fbclid"})
            ]
            new_q = "&".join(f"{k}={v}" for k, v in q)
            return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
        except Exception:
            return u

    def _filter_and_validate_urls(
        self,
        urls: Iterable[str],
        company_url: Optional[str],
        competitor_domains: Set[str],
    ) -> List[str]:
        """Filter and validate URLs according to rules."""
        company_host = self._normalize_hostname(company_url or "")
        results: List[str] = []
        seen: Set[str] = set()

        for raw in urls:
            if not raw:
                continue
            final_url = self._unwrap_redirect(raw)
            final_url = self._strip_utm_params(final_url)
            host = self._normalize_hostname(final_url)
            if not host:
                continue
            if host in FORBIDDEN_HOSTS:
                continue
            if company_host and self._is_same_or_subdomain(host, company_host):
                continue
            if any(self._is_same_or_subdomain(host, self._normalize_hostname(c)) for c in competitor_domains):
                continue
            if final_url in seen:
                continue
            if not self._check_url_ok(final_url):
                continue
            results.append(final_url)
            seen.add(final_url)
        return results

    def _extract_html_title(self, html: str) -> Optional[str]:
        """Extract title from HTML."""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        title = unescape(m.group(1)).strip()
        title = re.sub(r"\s+", " ", title)
        parts = re.split(r"[\-|•|·|:|—]", title)
        if len(title) > 120 and parts:
            title = parts[0].strip()
        return title if title else None

    def _fetch_page_title(self, url: str, timeout: float = 8.0) -> Optional[str]:
        """Fetch page title from URL."""
        try:
            with requests.Session() as s:
                s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
                r = s.get(url, timeout=timeout)
                if r.status_code != 200 or "text/html" not in (r.headers.get("Content-Type", "")):
                    return None
                return self._extract_html_title(r.text)
        except requests.RequestException:
            return None

    def _make_meta_title(self, url: str, language: str) -> str:
        """Generate meta title for URL."""
        title = self._fetch_page_title(url)
        if title:
            return title if len(title) <= 140 else title[:137] + "..."
        host = self._normalize_hostname(url)
        lang_map = {
            "de": f"Quelle: {host}",
            "fr": f"Source : {host}",
            "pt": f"Fonte: {host}",
            "es": f"Fuente: {host}",
        }
        return lang_map.get(language.lower()[:2], f"Source: {host}")

