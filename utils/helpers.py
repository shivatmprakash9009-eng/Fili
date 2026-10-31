"""Utility functions for the Multi-Agent System."""

from __future__ import annotations

import asyncio
import functools
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with optional prefix."""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


def sanitize_email(email: str) -> str | None:
    """Validate and sanitize an email address.

    Returns:
        Cleaned email string or None if invalid.
    """
    email = email.strip().lower()
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if re.match(pattern, email):
        return email
    return None


def format_timestamp(dt: datetime | None = None) -> str:
    """Format a datetime as ISO 8601 string."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat()


def load_json_file(path: str | Path) -> Any:
    """Load and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(path: str | Path, data: Any, indent: int = 2) -> None:
    """Save data to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=str, ensure_ascii=False)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def extract_json_from_text(text: str) -> dict[str, Any] | list[Any] | None:
    """Extract JSON object or array from text (useful for LLM responses).

    Tries to find JSON in the text by looking for { } or [ ] delimiters.

    Returns:
        Parsed JSON data or None if not found.
    """
    text = text.strip()

    # Try to parse the whole string first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to find JSON object
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find matching closing bracket
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    return None


def retry_async(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator for async retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        delay: Initial delay in seconds.
        backoff: Multiplier for delay after each retry.
        exceptions: Tuple of exception types to catch.

    Usage:
        @retry_async(max_retries=3, delay=1.0)
        async def flaky_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            last_exception: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator
