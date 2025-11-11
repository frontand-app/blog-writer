"""Modal deployment entry point for blog article generation."""

import json
from typing import Dict, Any

import modal

import sys
from pathlib import Path

# Add src to path for Modal
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.generators.content_generator import ContentGenerator
from src.schemas.input import InputSchema
from src.schemas.output import OutputSchema

# Create Modal app
app = modal.App("blog-writer")

# Define image with dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "google-genai",
        "pydantic>=2.0.0",
        "requests",
    )
    .env({"GOOGLE_API_KEY": modal.Secret.from_name("google-api-key")})
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("google-api-key")],
    timeout=600,
)
@modal.web_endpoint(method="POST")
def generate_blog_article(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a blog article from input data.

    Args:
        input_data: Input dictionary matching InputSchema

    Returns:
        Output dictionary matching OutputSchema
    """
    try:
        # Validate input
        input_schema = InputSchema(**input_data)

        # Initialize generator
        config = Config()
        generator = ContentGenerator(config=config)

        # Generate content
        output = generator.generate(input_schema)

        # Return as dict
        return output.model_dump()

    except Exception as e:
        return {"error": str(e)}


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("google-api-key")],
    timeout=300,
)
def validate_urls(
    query: str,
    company_url: str = "",
    competitors: list = None,
    language: str = "en",
    max_results: int = 3,
) -> list:
    """
    Validate URLs for a given query.

    Args:
        query: Search query
        company_url: Company URL to exclude
        competitors: List of competitor domains
        language: Language code
        max_results: Maximum results

    Returns:
        List of validated URLs
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.agents.validator import ValidatorAgent

    config = Config()
    agent = ValidatorAgent(api_key=config.get_api_key())

    return agent.validate_urls(
        query=query,
        company_url=company_url if company_url else None,
        competitors=competitors or [],
        language=language,
        max_results=max_results,
    )


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("google-api-key")],
    timeout=600,
)
def generate_research_report(
    topic: str,
    scope: str = "",
    seed_references: str = None,
) -> Dict[str, str]:
    """
    Generate a research report.

    Args:
        topic: Research topic
        scope: Scope description
        seed_references: Optional seed references

    Returns:
        Dict with 'plan', 'outline', and 'report' keys
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.agents.research import ResearchAgent

    config = Config()
    agent = ResearchAgent(api_key=config.get_api_key())

    return agent.generate_research_report(
        topic=topic,
        scope=scope,
        seed_references=seed_references,
    )


if __name__ == "__main__":
    # For local testing
    with app.run():
        pass

