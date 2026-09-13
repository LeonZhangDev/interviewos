from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import settings


class LLMClient:
    """Small OpenAI-compatible adapter used by InterviewOS.

    Works with OpenAI-compatible gateways, DeepSeek compatible endpoints and
    local vLLM servers. When no provider is configured, deterministic offline
    fallbacks keep the product usable.
    """

    def __init__(self) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def _url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.25, max_tokens: int = 900) -> str | None:
        if not self.enabled:
            return None
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                response = await client.post(self._url(), headers=self._headers(), json=payload)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

    async def chat_json(self, system: str, user: str) -> dict[str, Any] | None:
        text = await self.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.2, max_tokens=900)
        if not text:
            return None
        return _extract_json(text)

    async def stream(self, messages: list[dict[str, str]], *, fallback_text: str = "") -> AsyncIterator[str]:
        if not self.enabled:
            for token in _chunk_text(fallback_text or "请继续说明你的设计选择、失败边界和权衡。"):
                yield token
                await asyncio.sleep(0)
            return

        payload = {
            "model": self.model,
            "temperature": 0.35,
            "max_tokens": 700,
            "stream": True,
            "messages": messages,
        }
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", self._url(), headers=self._headers(), json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            obj = json.loads(data)
                            token = obj["choices"][0].get("delta", {}).get("content", "")
                        except (json.JSONDecodeError, KeyError, TypeError):
                            continue
                        if token:
                            yield token
        except httpx.HTTPError:
            for token in _chunk_text(fallback_text or "模型暂时不可用。请继续解释你的结论、证据和工程边界。"):
                yield token
                await asyncio.sleep(0)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _chunk_text(text: str) -> list[str]:
    parts = re.findall(r"[^，。！？,.!?\n]+[，。！？,.!?]?|\n", text)
    return [part for part in parts if part]


llm = LLMClient()
