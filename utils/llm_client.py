"""Unified LLM client supporting OpenAI and Google Gemini APIs."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger("llm_client")

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class LLMClient:
    """Provider-agnostic async LLM client.

    Supports OpenAI-compatible and Google Gemini APIs via HTTP.
    Includes retry logic, rate limiting, and cost tracking.
    """

    OPENAI_URL = "https://api.openai.com/v1/chat/completions"
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROK_URL = "https://api.x.ai/v1/chat/completions"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # Approximate cost per 1K tokens (USD)
    COST_PER_1K = {
        "openai/gpt-oss-120b": {"input": 0.0005, "output": 0.0007},
        "qwen/qwen3.8-27b": {"input": 0.0002, "output": 0.0003},
        "openai/gpt-oss-20b": {"input": 0.0001, "output": 0.0002},
        "llama-3.3-70b-versatile": {"input": 0.00059, "output": 0.00079},
        "llama-3.1-8b-instant": {"input": 0.00005, "output": 0.00008},
        "mixtral-8x7b-32768": {"input": 0.00024, "output": 0.00024},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "grok-2-latest": {"input": 0.002, "output": 0.01},
        "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    }

    def __init__(
        self,
        provider: str = "groq",
        api_key: str = "",
        model: str = "openai/gpt-oss-120b",
        base_url: str = "",
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._total_tokens_used: int = 0
        self._total_cost: float = 0.0
        self._request_count: int = 0

        if not HAS_HTTPX:
            logger.warning(
                "httpx not installed. Install with: pip install httpx. "
                "LLM calls will fail."
            )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Generate text using the configured LLM provider.

        Args:
            prompt: User prompt.
            system_prompt: System instruction.
            temperature: Sampling temperature.
            max_tokens: Max tokens in response.

        Returns:
            Generated text string.

        Raises:
            RuntimeError: If API call fails after all retries.
        """
        if not self.api_key:
            raise RuntimeError(
                "LLM API key not configured. Set LLM_API_KEY environment variable."
            )
        if not HAS_HTTPX:
            raise RuntimeError("httpx not installed. Run: pip install httpx")

        if self.provider == "gemini":
            return await self._call_gemini(prompt, system_prompt, temperature, max_tokens)
        else:
            if self.provider == "groq":
                default_url = self.GROQ_URL
            elif self.provider in ["grok", "xai"]:
                default_url = self.GROK_URL
            else:
                default_url = self.OPENAI_URL

            endpoint_url = self.base_url or default_url
            return await self._call_openai_compatible(endpoint_url, prompt, system_prompt, temperature, max_tokens)

    async def _call_openai_compatible(
        self,
        endpoint_url: str,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call OpenAI/Groq/Grok-compatible API."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = await self._request_with_retry(endpoint_url, payload, headers)

        # Extract response text
        text = data["choices"][0]["message"]["content"]

        # Track usage
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        self._total_tokens_used += tokens
        self._track_cost(
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

        return text

    async def _call_gemini(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call Google Gemini API."""
        url = self.GEMINI_URL.format(model=self.model)

        contents: list[dict[str, Any]] = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": system_prompt}],
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}],
            })
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}],
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        headers = {"Content-Type": "application/json"}
        full_url = f"{url}?key={self.api_key}"

        data = await self._request_with_retry(full_url, payload, headers)

        # Extract text
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = parts[0].get("text", "") if parts else ""

        # Track usage
        usage = data.get("usageMetadata", {})
        tokens = usage.get("totalTokenCount", 0)
        self._total_tokens_used += tokens

        return text

    async def _request_with_retry(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Make HTTP request with exponential backoff retry."""
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)

                self._request_count += 1

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited
                    delay = 2 ** attempt
                    logger.warning(f"Rate limited. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    error_detail = response.text[:200]
                    raise RuntimeError(
                        f"LLM API error {response.status_code}: {error_detail}"
                    )
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    logger.warning(f"Request failed (attempt {attempt}): {exc}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)

        raise RuntimeError(f"LLM API call failed after {self.max_retries} retries: {last_error}")

    def _track_cost(self, input_tokens: int, output_tokens: int) -> None:
        """Track approximate API costs."""
        costs = self.COST_PER_1K.get(self.model, {"input": 0.001, "output": 0.002})
        cost = (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])
        self._total_cost += cost

    def get_usage_stats(self) -> dict[str, Any]:
        """Get API usage statistics."""
        return {
            "provider": self.provider,
            "model": self.model,
            "total_requests": self._request_count,
            "total_tokens": self._total_tokens_used,
            "estimated_cost_usd": round(self._total_cost, 4),
        }
