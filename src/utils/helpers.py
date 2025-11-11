"""Utility functions for blog article generation."""

import re
from datetime import datetime, timedelta
import random


def slugify(text: str) -> str:
    """
    Convert text to URL-friendly slug.

    Args:
        text: Text to slugify

    Returns:
        URL-friendly slug
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "article"


def generate_random_date(days_back: int = 90) -> str:
    """
    Generate a random date within the last N days.

    Args:
        days_back: Maximum days to go back (default: 90)

    Returns:
        Formatted date string (DD.MM.YYYY)
    """
    today = datetime.now()
    random_days = random.randint(0, days_back)
    random_date = today - timedelta(days=random_days)
    return random_date.strftime("%d.%m.%Y")


def count_words(text: str) -> int:
    """
    Count words in text.

    Args:
        text: Text to count words in

    Returns:
        Word count
    """
    return len(text.split())


def estimate_read_time(word_count: int, words_per_minute: int = 200) -> int:
    """
    Estimate read time in minutes.

    Args:
        word_count: Total word count
        words_per_minute: Reading speed (default: 200)

    Returns:
        Estimated read time in minutes
    """
    return max(1, (word_count + words_per_minute - 1) // words_per_minute)


def strip_html_tags(text: str) -> str:
    """
    Strip HTML tags from text.

    Args:
        text: Text with HTML tags

    Returns:
        Plain text without HTML tags
    """
    return re.sub(r"<[^>]*>", "", text)

