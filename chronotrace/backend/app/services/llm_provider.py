"""
ChronoTrace AI — LLM Provider Abstraction
Supports Gemini, OpenAI, and Mock providers for controlled testing and offline operation.
Provider selected via LLM_PROVIDER env var.
API keys are NEVER hard-coded — loaded strictly from environment configuration.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict

from app.config import settings

logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract interface for LLM completion providers."""

    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Run text completion."""
        pass

    @abstractmethod
    async def complete_json(self, system_prompt: str, user_prompt: str) -> Any:
        """Run JSON-structured completion."""
        pass


class GeminiProvider(BaseLLMProvider):
    """Google Gemini completion provider using google-genai or google.generativeai."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model_name or settings.gemini_model

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key or self.api_key == "test-key":
            raise EnvironmentError("GEMINI_API_KEY is not configured with a valid key.")

        try:
            # Prefer modern google.genai if installed
            from google import genai
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config={"system_instruction": system_prompt},
            )
            return response.text or ""
        except ImportError:
            # Fall back to legacy google.generativeai
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=self.api_key)
            model = legacy_genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt,
            )
            resp = model.generate_content(user_prompt)
            return resp.text or ""

    async def complete_json(self, system_prompt: str, user_prompt: str) -> Any:
        raw = await self.complete(system_prompt, user_prompt)
        return _parse_json_payload(raw)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API completion provider."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model_name = model_name or settings.openai_model

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key or self.api_key == "test-key":
            raise EnvironmentError("OPENAI_API_KEY is not configured with a valid key.")

        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self.api_key)
        response = await client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    async def complete_json(self, system_prompt: str, user_prompt: str) -> Any:
        raw = await self.complete(system_prompt, user_prompt)
        return _parse_json_payload(raw)


class MockLLMProvider(BaseLLMProvider):
    """
    Mock provider for automated deterministic testing and simulated self-correction.
    Can be loaded with preset responses or mock errors.
    """

    def __init__(self, canned_response: Optional[Any] = None) -> None:
        self.canned_response = canned_response
        self.call_count = 0
        self.history: list[dict] = []

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        self.history.append({"system": system_prompt, "user": user_prompt})
        if isinstance(self.canned_response, str):
            return self.canned_response
        return json.dumps(self.canned_response or [])

    async def complete_json(self, system_prompt: str, user_prompt: str) -> Any:
        self.call_count += 1
        self.history.append({"system": system_prompt, "user": user_prompt})
        if self.canned_response is not None:
            if isinstance(self.canned_response, (list, dict)):
                return self.canned_response
            return _parse_json_payload(str(self.canned_response))
        return []


def _parse_json_payload(raw: str) -> Any:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()
    return json.loads(cleaned)


class LLMProvider:
    """Delegating provider factory that routes to configured backend."""

    def __init__(self) -> None:
        self._active_provider: Optional[BaseLLMProvider] = None

    def get_provider(self) -> BaseLLMProvider:
        if self._active_provider:
            return self._active_provider

        prov_type = settings.llm_provider.lower()
        if prov_type == "openai":
            self._active_provider = OpenAIProvider()
        elif prov_type == "mock":
            self._active_provider = MockLLMProvider()
        else:
            self._active_provider = GeminiProvider()
        return self._active_provider

    def set_mock_provider(self, mock_provider: BaseLLMProvider) -> None:
        """Inject a test or mock provider for controlled evaluations."""
        self._active_provider = mock_provider

    def reset_provider(self) -> None:
        """Reset back to environment-based provider."""
        self._active_provider = None

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        return await self.get_provider().complete(system_prompt, user_prompt)

    async def complete_json(self, system_prompt: str, user_prompt: str) -> Any:
        return await self.get_provider().complete_json(system_prompt, user_prompt)


# Module singleton
llm = LLMProvider()
