"""Input schema definitions for blog article generation."""

from typing import List, Optional
from pydantic import BaseModel, Field


class InputSchema(BaseModel):
    """Input schema for blog article generation."""

    primary_keyword: str = Field(..., description="Primary keyword/topic for the blog article")
    company_url: str = Field(..., description="Company root URL")
    company_name: str = Field(..., description="Company name")
    company_language: str = Field(default="en", description="Company language code (e.g., en, de, fr)")
    company_location: str = Field(..., description="Target country/location")
    company_competitors: List[str] = Field(default_factory=list, description="List of competitor domains to exclude")
    company_info: dict = Field(default_factory=dict, description="Company information dictionary")
    content_generation_instruction: str = Field(default="", description="Specific instructions for content generation")
    links: List[str] = Field(default_factory=list, description="Internal links to include in the article")
    scope: Optional[str] = Field(None, description="Optional scope for research (e.g., 'EU focus; B2C and B2B')")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "primary_keyword": "AI adoption in customer service",
                "company_url": "https://example.com",
                "company_name": "Example Corp",
                "company_language": "en",
                "company_location": "Germany",
                "company_competitors": ["competitor1.com", "competitor2.io"],
                "company_info": {"industry": "SaaS", "focus": "Customer experience"},
                "content_generation_instruction": "Focus on B2B use cases",
                "links": ["/product", "/features"],
                "scope": "EU focus; B2C and B2B; service interactions",
            }
        }

