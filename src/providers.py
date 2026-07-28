"""LLM providers for baseline, RAG chatbot and grounded Agent answers."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from dotenv import load_dotenv

load_dotenv()


class BaseLLMProvider(Protocol):
    model_name: str

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate natural-language text."""

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility method for structured experiments."""


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model không trả JSON object hoàn chỉnh.") from first_error
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as second_error:
            raise ValueError("Model trả JSON sai cú pháp hoặc bị cắt giữa chừng.") from second_error
    if not isinstance(value, dict):
        raise ValueError("JSON output phải là object.")
    return value

class GeminiProvider:
    """Google Gemini provider through the official google-genai SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.15"))
        self.max_output_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1200"))
        self._client: Any = None

    def _get_client(self) -> Any:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            raise RuntimeError("Chưa có GEMINI_API_KEY trong file .env.")
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "Chưa cài google-genai. Chạy: python -m pip install -U google-genai"
                ) from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _call(
        self,
        prompt: str,
        system_prompt: str,
        *,
        json_mode: bool,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        try:
            from google.genai import types

            kwargs: dict[str, Any] = {
                "system_instruction": system_prompt or None,
                "temperature": 0.0 if json_mode else self.temperature,
                "max_output_tokens": self.max_output_tokens,
            }
            if json_mode:
                kwargs["response_mime_type"] = "application/json"
                if response_schema:
                    kwargs["response_json_schema"] = response_schema
            try:
                config = types.GenerateContentConfig(**kwargs)
            except TypeError:
                schema = kwargs.pop("response_json_schema", None)
                if schema is not None:
                    kwargs["response_schema"] = schema
                try:
                    config = types.GenerateContentConfig(**kwargs)
                except TypeError:
                    kwargs.pop("response_schema", None)
                    kwargs.pop("response_mime_type", None)
                    config = types.GenerateContentConfig(**kwargs)

            response = self._get_client().models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            parsed = getattr(response, "parsed", None)
            if json_mode and isinstance(parsed, dict):
                return json.dumps(parsed, ensure_ascii=False)
            text = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Gemini không trả nội dung văn bản.")
            return text.strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini generation failed: {exc}") from exc

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            return self._call(prompt, system_prompt, json_mode=False)
        except RuntimeError as exc:
            return f"[Gemini Error] {exc}"

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        strict_prompt = (
            prompt
            + "\n\nChỉ trả về một JSON object hợp lệ, ngắn gọn, không dùng markdown."
        )
        text = self._call(
            strict_prompt,
            system_prompt,
            json_mode=True,
            response_schema=response_schema,
        )
        return _extract_json_object(text)


class MockProvider:
    """Offline provider. Agent code uses deterministic fallback answers with it."""

    model_name = "offline-grounded-mock-v2"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        del prompt, system_prompt
        return "[Mock] Dùng câu trả lời fallback từ Observation."

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = "",
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del prompt, system_prompt, response_schema
        return {}


def get_llm_provider(provider_name: str | None = None) -> BaseLLMProvider:
    name = (provider_name or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError("LLM_PROVIDER chỉ hỗ trợ 'gemini' hoặc 'mock'.")
