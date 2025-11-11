import os
import json
import sys
import re
import urllib.request


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"


def call_gemini(payload: dict, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_URL}?key={api_key}", data=data)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_text(resp: dict) -> str:
    return (
        resp.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "report"


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY is not set in the environment.")
        sys.exit(1)

    topic = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Trust dynamics in AI‑powered customer service"
    )
    scope = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "EU focus; B2C and B2B; service interactions"
    )
    out_slug = sys.argv[3] if len(sys.argv) > 3 else slugify(topic)

    # 1) Plan
    plan_prompt = (
        "You are a careful research assistant.\n"
        f"Topic: {topic}.\n"
        f"Scope: {scope}.\n"
        "Task: Plan a brief research strategy (queries to run; source types to check),\n"
        "then draft a structured outline with section headings for an evidence-based report.\n"
        "Do not write the report yet. Avoid bullet points; use short paragraphs.\n"
        "Output JSON with keys plan and outline."
    )
    # Seed references to anchor research
    seed_refs = """
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

    plan_prompt += (
        "\nMinimum sources: at least 50 primary or regulator/standards items.\n"
        "Use and expand the following seed references (do not replace them):\n"
        f"{seed_refs}\n"
        "Prefer peer‑reviewed journals, regulators, and standards; avoid blogs/press unless necessary."
    )

    plan_payload = {
        "contents": [{"role": "user", "parts": [{"text": plan_prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
    }
    plan_resp = call_gemini(plan_payload, api_key)
    plan_text = extract_text(plan_resp)

    # 2) Draft
    draft_prompt = (
        "You are a careful research assistant.\n"
        f"Topic: {topic}.\n"
        f"Scope: {scope}.\n"
        "Style: Academic prose; no bullet points; numbered sections allowed.\n"
        "Deliverable: A structured research report with sections: Background, Key findings, Implications, Measurement, Risks, References.\n"
        "Plan and outline provided below; follow them but improve if needed.\n"
        f"Plan+Outline:\n{plan_text}\n"
        "Write the full report now. Use paragraphs, no bullet points.\n"
        "End with a References section as plain lines with titles and canonical URLs or DOIs only."
    )
    draft_payload = {
        "contents": [{"role": "user", "parts": [{"text": draft_prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
    }
    draft_resp = call_gemini(draft_payload, api_key)
    draft_text = extract_text(draft_resp)

    # Write per-topic file
    out_dir = os.path.join("output", "thesis", "deep_research")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{out_slug}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(draft_text)

    # Optionally append to aggregate file
    aggregate_path = os.environ.get("AGGREGATE_FILE", "").strip()
    if aggregate_path:
        os.makedirs(os.path.dirname(aggregate_path), exist_ok=True)
        with open(aggregate_path, "a", encoding="utf-8") as agg:
            agg.write(f"\n\n## {topic}\n\n")
            agg.write(draft_text)

    print(out_path)


if __name__ == "__main__":
    main()

