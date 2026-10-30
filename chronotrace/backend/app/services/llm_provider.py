"""
ChronoTrace AI — LLM Provider Abstraction
Supports Gemini (default) and OpenAI. Provider selected via LLM_PROVIDER env var.
API keys are NEVER hard-coded — loaded from environment only.
"""
from __future__ import annotations

import json
from typing import Any, Optional
from app.config import settings


class LLMProvider:
    """Thin async wrapper around Gemini / OpenAI for structured extraction and QA."""

    def __init__(self) -> None:
        self._provider = settings.llm_provider

    # ── Gemini ────────────────────────────────────────────────────────────────

    async def _gemini_chat(self, system_prompt: str, user_prompt: str) -> str:
        import google.generativeai as genai  # lazy import

        if not settings.gemini_api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Add it to your .env file."
            )
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=system_prompt,
        )
        response = model.generate_content(user_prompt)
        return response.text

    # ── OpenAI ────────────────────────────────────────────────────────────────

    async def _openai_chat(self, system_prompt: str, user_prompt: str) -> str:
        from openai import AsyncOpenAI  # lazy import

        if not settings.openai_api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    # ── Public interface ──────────────────────────────────────────────────────

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Run a chat completion and return the raw text response."""
        if self._provider == "gemini":
            return await self._gemini_chat(system_prompt, user_prompt)
        return await self._openai_chat(system_prompt, user_prompt)

    async def complete_json(
        self, system_prompt: str, user_prompt: str
    ) -> Any:
        """Run a chat completion and parse the response as JSON."""
        raw = await self.complete(system_prompt, user_prompt)
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM returned invalid JSON: {exc}\n\nRaw response:\n{raw}"
            ) from exc


# Module-level singleton
llm = LLMProvider()

