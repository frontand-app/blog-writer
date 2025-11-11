"""Research Agent using Gemini 1.5 Pro for deep research reports."""

import json
import os
import re
import urllib.request
from typing import Optional


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"


class ResearchAgent:
    """Research agent for generating deep research reports."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the research agent.

        Args:
            api_key: Google AI API key. If None, uses GEMINI_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be set or provided as api_key parameter")

    def generate_research_report(
        self,
        topic: str,
        scope: str = "",
        seed_references: Optional[str] = None,
    ) -> dict:
        """
        Generate a research report for a given topic.

        Args:
            topic: Research topic
            scope: Scope description (e.g., "EU focus; B2C and B2B")
            seed_references: Optional seed references to include

        Returns:
            Dict with 'plan', 'outline', and 'report' keys
        """
        # Generate plan and outline
        plan_result = self._generate_plan(topic, scope, seed_references)
        plan_text = plan_result.get("plan", "")
        outline_text = plan_result.get("outline", "")

        # Generate full report
        report_text = self._generate_report(topic, scope, plan_text, outline_text)

        return {
            "plan": plan_text,
            "outline": outline_text,
            "report": report_text,
        }

    def _generate_plan(self, topic: str, scope: str, seed_references: Optional[str] = None) -> dict:
        """Generate research plan and outline."""
        plan_prompt = (
            "You are a careful research assistant.\n"
            f"Topic: {topic}.\n"
            f"Scope: {scope}.\n"
            "Task: Plan a brief research strategy (queries to run; source types to check),\n"
            "then draft a structured outline with section headings for an evidence-based report.\n"
            "Do not write the report yet. Avoid bullet points; use short paragraphs.\n"
            "Output JSON with keys plan and outline."
        )

        default_seed_refs = """
Lemon & Verhoef (2016) Journal of Marketing (Customer experience)
Tax, Brown & Chandrashekaran (1998) Journal of Marketing Research (Service justice)
Dixon, Freeman & Toman (2010) HBR and later service‑journal replications (Customer Effort)
Green & Chen (2019) Management Science (Algorithmic advice reliance)
Lai & Tan (2019) MIS Quarterly (Human–AI collaboration)
NIST AI Risk Management Framework 1.0 (2023)
ISO/IEC 42001:2023 AI Management System
EU AI Act (Reg. 2024/1689, OJ)
GDPR (2016)
EDPB Opinion 28/2024 (AI models)
ENISA AI Threat Landscape (2024)
Nature 2024 s41586-024-07421-0 (Hallucination measurement)
Scientific Reports 2024 s41598-024-71761-0 (Trust and AI governance)
npj Digital Medicine 2024 s41746-024-01258-7 (QUEST – human evaluation)
RAG Evaluation Surveys (2024–2025, arXiv)
Agentic RAG Surveys (2025, arXiv)
OECD AI Principles update (2024)
Gioia, Corley & Hamilton (2013) Organizational Research Methods
Baymard Institute 2024–2025 Checkout/Account UX (methodology + findings)
Service recovery paradox meta‑work (peer‑reviewed 2010s)
""".strip()

        seed_refs = seed_references or default_seed_refs

        plan_prompt += (
            "\nMinimum sources: at least 50 primary or regulator/standards items.\n"
            "Use and expand the following seed references (do not replace them):\n"
            f"{seed_refs}\n"
            "Prefer peer‑reviewed journals, regulators, and standards; avoid blogs/press unless necessary."
        )

        payload = {
            "contents": [{"role": "user", "parts": [{"text": plan_prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
        }

        resp = self._call_gemini(payload)
        plan_text = self._extract_text(resp)

        # Try to parse JSON from response
        try:
            # Look for JSON in the response
            json_match = re.search(r"\{[\s\S]*\}", plan_text)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # Fallback: return as text
        return {"plan": plan_text, "outline": ""}

    def _generate_report(self, topic: str, scope: str, plan_text: str, outline_text: str) -> str:
        """Generate full research report."""
        draft_prompt = (
            "You are a careful research assistant.\n"
            f"Topic: {topic}.\n"
            f"Scope: {scope}.\n"
            "Style: Academic prose; no bullet points; numbered sections allowed.\n"
            "Deliverable: A structured research report with sections: Background, Key findings, "
            "Implications, Measurement, Risks, References.\n"
            "Plan and outline provided below; follow them but improve if needed.\n"
            f"Plan+Outline:\n{plan_text}\n{outline_text}\n"
            "Write the full report now. Use paragraphs, no bullet points.\n"
            "End with a References section as plain lines with titles and canonical URLs or DOIs only."
        )

        payload = {
            "contents": [{"role": "user", "parts": [{"text": draft_prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
        }

        resp = self._call_gemini(payload)
        return self._extract_text(resp)

    def _call_gemini(self, payload: dict) -> dict:
        """Call Gemini API."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{API_URL}?key={self.api_key}", data=data)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _extract_text(self, resp: dict) -> str:
        """Extract text from Gemini response."""
        return (
            resp.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to URL-friendly slug."""
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text or "report"

