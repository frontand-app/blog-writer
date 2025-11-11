#!/usr/bin/env python3
"""
Gemini URL Validator Agent (Python)

Purpose:
- Use Gemini 2.5 Flash with Google Search grounding to find/validate source URLs.
- Mirror the n8n validator-agent.json behavior: search → validate (HTTP 200) → exclude company/competitors/forbidden → return strict JSON.

Requirements:
- pip install -r requirements.txt
- Auth (choose ONE):
  Option A) Google AI API key
    export GOOGLE_API_KEY=<your_key>
    (or pass --api-key)
  Option B) Vertex AI via google-genai SDK
    export GOOGLE_GENAI_USE_VERTEXAI=True
    export GOOGLE_CLOUD_PROJECT=<project_id>
    export GOOGLE_CLOUD_LOCATION=global
    gcloud auth application-default login

Notes:
- Uses Google Search tool (grounding) and parses grounding citations to derive candidate URLs.
- Unwraps Google grounding redirect links to final target URLs before validation.
- Validates with HEAD, falling back to GET; requires status_code 200.
- Generates a short meta title from the page <title>; if unavailable, falls back to a concise domain-based title.
- Enforces rules similar to the reference agent:
  * external links only (not the provided company domain)
  * exclude competitor domains
  * exclude forbidden hosts (vertexaisearch.cloud.google.com, cloud.google.com)

CLI example:
  python3 gemini_validator_agent.py \
    --query "AI adoption in European CX" \
    --company-url "https://example.com" \
    --competitors "competitor1.com,competitor2.io" \
    --language "en" \
    --max-results 3 \
    --api-key "YOUR_GOOGLE_API_KEY"

Outputs to stdout a strict JSON array of objects:
[
  { "url": "https://...", "url_meta_title": "..." },
  ...
]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from html import unescape
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl

import requests

# Google GenAI (Google AI API or Vertex AI) SDK
from google import genai
from google.genai.types import GenerateContentConfig, Tool, GoogleSearch, HttpOptions


FORBIDDEN_HOSTS: Set[str] = {
    "vertexaisearch.cloud.google.com",  # grounding redirect host
    "cloud.google.com",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def normalize_hostname(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower().lstrip(".").removeprefix("www.")
    except Exception:
        return ""


def is_same_or_subdomain(host: str, root: str) -> bool:
    if not host or not root:
        return False
    host = host.lower()
    root = root.lower().lstrip(".")
    return host == root or host.endswith("." + root)


def unwrap_redirect(url: str, timeout: float = 8.0) -> str:
    """Follow redirects to reveal the final destination (handles grounding redirect URIs)."""
    try:
        with requests.Session() as s:
            s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
            resp = s.head(url, allow_redirects=True, timeout=timeout)
            if resp.ok:
                return resp.url
            # Some servers reject HEAD; try GET quickly (no stream)
            resp = s.get(url, allow_redirects=True, timeout=timeout)
            if resp.ok:
                return resp.url
    except requests.RequestException:
        pass
    return url


def check_url_ok(url: str, timeout: float = 8.0) -> bool:
    try:
        with requests.Session() as s:
            s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
            # Prefer HEAD
            r = s.head(url, allow_redirects=True, timeout=timeout)
            if r.status_code == 200:
                return True
            # Some sites don't support HEAD properly
            r = s.get(url, allow_redirects=True, timeout=timeout)
            return r.status_code == 200
    except requests.RequestException:
        return False


def extract_html_title(html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    title = unescape(m.group(1)).strip()
    # Collapse whitespace
    title = re.sub(r"\s+", " ", title)
    # Remove trailing site separators if overly long
    parts = re.split(r"[\-|•|·|:|—]", title)
    if len(title) > 120 and parts:
        title = parts[0].strip()
    return title if title else None


def fetch_page_title(url: str, timeout: float = 8.0) -> Optional[str]:
    try:
        with requests.Session() as s:
            s.headers.update({"User-Agent": DEFAULT_USER_AGENT})
            r = s.get(url, timeout=timeout)
            if r.status_code != 200 or "text/html" not in (r.headers.get("Content-Type", "")):
                return None
            return extract_html_title(r.text)
    except requests.RequestException:
        return None


def _strip_utm_params(u: str) -> str:
    """Remove common tracking parameters (utm_*, gclid, fbclid)."""
    try:
        p = urlparse(u)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not (k.lower().startswith("utm_") or k.lower() in {"gclid", "fbclid"})]
        new_q = "&".join(f"{k}={v}" for k, v in q)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
    except Exception:
        return u


def filter_and_validate_urls(
    urls: Iterable[str],
    company_url: Optional[str],
    competitor_domains: Set[str],
) -> List[str]:
    company_host = normalize_hostname(company_url or "")
    results: List[str] = []
    seen: Set[str] = set()

    for raw in urls:
        if not raw:
            continue
        # unwrap grounding redirectors
        final_url = unwrap_redirect(raw)
        # strip tracking params
        final_url = _strip_utm_params(final_url)
        host = normalize_hostname(final_url)
        if not host:
            continue
        if host in FORBIDDEN_HOSTS:
            continue
        if company_host and is_same_or_subdomain(host, company_host):
            # must be external
            continue
        # exclude competitors (match root or subdomain)
        if any(is_same_or_subdomain(host, normalize_hostname(c)) for c in competitor_domains):
            continue
        if final_url in seen:
            continue
        if not check_url_ok(final_url):
            continue
        results.append(final_url)
        seen.add(final_url)
    return results


def grounded_sources_from_response(resp) -> List[Tuple[str, str]]:
    """Return list of (title, uri) from grounding metadata (deduped by uri)."""
    out: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    try:
        # Prefer the first candidate
        cand = resp.candidates[0]
        # The SDK may expose snake_case or camelCase; check both.
        gm = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None)
        if not gm:
            return out
        chunks = getattr(gm, "grounding_chunks", None) or getattr(gm, "groundingChunks", None)
        if not chunks:
            return out
        for ch in chunks:
            # chunk.web.uri / chunk.web.title
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


def make_client(api_key: Optional[str]):
    # Prefer explicit API key (Google AI API)
    key = api_key or os.environ.get("GOOGLE_API_KEY")
    if key:
        return genai.Client(api_key=key)
    # Else try Vertex AI (requires env configuration)
    return genai.Client(http_options=HttpOptions(api_version="v1"))


def call_gemini_with_search(user_query: str, api_key: Optional[str]) -> any:
    client = make_client(api_key)
    model_id = "gemini-2.5-flash"
    cfg = GenerateContentConfig(
        tools=[Tool(google_search=GoogleSearch())],
        temperature=1.0,
        response_modalities=["TEXT"],
    )
    system_hint = (
        "When answering, use Google Search grounding and prefer authoritative, non-competitive, external sources. "
        "Avoid using vertexaisearch.cloud.google.com and cloud.google.com as final citations."
    )
    contents = [system_hint, user_query]
    return client.models.generate_content(model=model_id, contents=contents, config=cfg)


def make_meta_title(url: str, language: str) -> str:
    title = fetch_page_title(url)
    if title:
        return title if len(title) <= 140 else title[:137] + "..."
    # fallback to host if title missing
    host = normalize_hostname(url)
    if language.lower().startswith("de"):
        return f"Quelle: {host}"
    if language.lower().startswith("fr"):
        return f"Source : {host}"
    if language.lower().startswith("pt"):
        return f"Fonte: {host}"
    if language.lower().startswith("es"):
        return f"Fuente: {host}"
    return f"Source: {host}"


def run_agent(
    query: str,
    company_url: Optional[str],
    competitors: Iterable[str],
    language: str,
    max_results: int,
    api_key: Optional[str],
) -> List[dict]:
    resp = call_gemini_with_search(query, api_key)
    grounded = grounded_sources_from_response(resp)
    uris = [u for (_t, u) in grounded]

    valid_urls = filter_and_validate_urls(uris, company_url, set(competitors))
    valid_urls = valid_urls[:max_results]

    results = []
    for url in valid_urls:
        meta = make_meta_title(url, language)
        results.append({"url": url, "url_meta_title": meta})
    return results


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gemini grounded URL validator agent")
    p.add_argument("--query", required=True, help="User query / topic to search")
    p.add_argument("--company-url", default="", help="Company root URL (to exclude)")
    p.add_argument(
        "--competitors",
        default="",
        help="Comma-separated competitor domains to exclude (e.g. rival.com,other.io)",
    )
    p.add_argument("--language", default="en", help="Meta title language (e.g. en, de, fr)")
    p.add_argument("--max-results", type=int, default=3, help="Max URLs to return")
    p.add_argument("--api-key", default="", help="Google AI API key (optional; else uses env or Vertex)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]

    results = run_agent(
        query=args.query,
        company_url=args.company_url if args.company_url else None,
        competitors=competitors,
        language=args.language,
        max_results=max(1, args.max_results),
        api_key=args.api_key or None,
    )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)