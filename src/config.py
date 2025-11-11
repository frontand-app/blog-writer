"""Configuration management for blog article generation."""

import os
from typing import Optional


class Config:
    """Configuration manager for blog article generation."""

    def __init__(self):
        """Initialize configuration from environment variables."""
        # Google AI API keys
        self.google_api_key: Optional[str] = os.environ.get("GOOGLE_API_KEY")
        self.gemini_api_key: Optional[str] = os.environ.get("GEMINI_API_KEY") or self.google_api_key

        # Vertex AI configuration
        self.use_vertex_ai: bool = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        self.google_cloud_project: Optional[str] = os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.google_cloud_location: str = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

        # Supabase configuration (optional)
        self.supabase_url: Optional[str] = os.environ.get("SUPABASE_URL")
        self.supabase_key: Optional[str] = os.environ.get("SUPABASE_KEY")

        # Model configuration
        self.content_model: str = os.environ.get("CONTENT_MODEL", "gemini-2.5-pro")
        self.validator_model: str = os.environ.get("VALIDATOR_MODEL", "gemini-2.5-flash")
        self.research_model: str = os.environ.get("RESEARCH_MODEL", "gemini-1.5-pro")

        # Output configuration
        self.output_dir: str = os.environ.get("OUTPUT_DIR", "output")
        self.aggregate_file: Optional[str] = os.environ.get("AGGREGATE_FILE")

    def validate(self) -> bool:
        """
        Validate that required configuration is present.

        Returns:
            True if configuration is valid
        """
        if not self.use_vertex_ai and not self.google_api_key:
            return False
        if self.use_vertex_ai and not self.google_cloud_project:
            return False
        return True

    def get_api_key(self) -> Optional[str]:
        """
        Get the appropriate API key.

        Returns:
            API key if available
        """
        return self.google_api_key or self.gemini_api_key

