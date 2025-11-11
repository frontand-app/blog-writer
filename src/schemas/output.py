"""Output schema definitions for blog article generation."""

from typing import List, Optional
from pydantic import BaseModel, Field


class Section(BaseModel):
    """A section of the blog article."""

    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section content (HTML formatted)")


class FAQItem(BaseModel):
    """A FAQ item."""

    question: str = Field(..., description="FAQ question")
    answer: str = Field(..., description="FAQ answer")


class PAAItem(BaseModel):
    """A People Also Ask item."""

    question: str = Field(..., description="PAA question")
    answer: str = Field(..., description="PAA answer")


class Source(BaseModel):
    """A source reference."""

    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Source title/description")
    index: Optional[int] = Field(None, description="Citation index")


class OutputSchema(BaseModel):
    """Output schema for blog article generation."""

    headline: str = Field(..., description="Main headline")
    subtitle: Optional[str] = Field(None, description="Subtitle")
    teaser: str = Field(..., description="2-3 sentence hook/teaser")
    intro: str = Field(..., description="Opening paragraph (80-120 words)")
    meta_title: str = Field(..., description="SEO meta title (≤55 characters)")
    meta_description: str = Field(..., description="SEO meta description (≤130 characters)")
    sections: List[Section] = Field(default_factory=list, description="Article sections")
    key_takeaways: List[str] = Field(default_factory=list, description="Key takeaways (max 3)")
    faq: List[FAQItem] = Field(default_factory=list, description="FAQ items")
    paa: List[PAAItem] = Field(default_factory=list, description="People Also Ask items")
    sources: List[Source] = Field(default_factory=list, description="Source references")
    search_queries: List[str] = Field(default_factory=list, description="Search queries used")
    read_time: int = Field(..., description="Estimated read time in minutes")
    date: str = Field(..., description="Publication date")
    literature: str = Field(default="", description="Formatted literature/references")
    html: Optional[str] = Field(None, description="Full HTML output")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "headline": "AI Adoption in Customer Service: A Comprehensive Guide",
                "subtitle": "How AI is transforming customer experience",
                "teaser": "AI is revolutionizing customer service...",
                "intro": "<p>Customer service has evolved dramatically...</p>",
                "meta_title": "AI Adoption in Customer Service | Guide 2024",
                "meta_description": "Learn how AI transforms customer service...",
                "sections": [
                    {"title": "Introduction to AI in Customer Service", "content": "<p>Content here...</p>"}
                ],
                "key_takeaways": ["Takeaway 1", "Takeaway 2"],
                "faq": [{"question": "What is AI?", "answer": "AI is..."}],
                "paa": [{"question": "How does AI help?", "answer": "AI helps..."}],
                "sources": [{"url": "https://example.com", "title": "Example Source", "index": 1}],
                "search_queries": ["AI customer service", "AI adoption"],
                "read_time": 5,
                "date": "15.01.2024",
                "literature": "<p>[1]: <a href='...'>Source</a></p>",
            }
        }

