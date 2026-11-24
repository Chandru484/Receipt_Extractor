import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from universal_chatbot.backend.app.ai.provider_base import BaseLLMProvider
from universal_chatbot.backend.app.core.config import chatbot_settings

logger = logging.getLogger(__name__)


class FallbackHTTPProvider(BaseLLMProvider):
    """
    Secondary multi-provider fallback (OpenRouter, DeepSeek, Mistral, etc.)
    using standard OpenAI-compatible completions API via HTTPX.
    """

    def __init__(self):
        self.api_key = chatbot_settings.CHATBOT_FALLBACK_API_KEY
        self.base_url = chatbot_settings.CHATBOT_FALLBACK_BASE_URL.rstrip("/")
        self.model = chatbot_settings.CHATBOT_FALLBACK_MODEL
        self.provider_name = chatbot_settings.CHATBOT_FALLBACK_PROVIDER

    def is_available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError(f"Fallback provider '{self.provider_name}' is not configured.")

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://universal-chatbot.platform",
            "X-Title": "Universal AI Chatbot",
        }
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        t0 = time.perf_counter()
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(endpoint, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Fallback provider {self.provider_name} returned {resp.status_code}: {resp.text}"
                )
            data = resp.json()

        latency = round(time.perf_counter() - t0, 3)
        reply = data["choices"][0]["message"]["content"] or ""
        tokens = data.get("usage", {}).get("total_tokens", 0)

        return {
            "reply": reply.strip(),
            "provider": self.provider_name,
            "model": self.model,
            "latency": latency,
            "tokens_used": tokens,
        }
