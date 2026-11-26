import logging
import random
import time
from typing import Any, Dict, List, Optional
from groq import Groq, APIError, RateLimitError, APITimeoutError

from universal_chatbot.backend.app.ai.provider_base import BaseLLMProvider
from universal_chatbot.backend.app.core.config import chatbot_settings

logger = logging.getLogger(__name__)


class GroqChatbotProvider(BaseLLMProvider):
    """
    Dedicated Groq provider for the Chatbot Platform.
    Implements key rotation across all available Groq API keys with automatic failover
    on Rate Limits (429), timeouts, or empty responses, plus multi-model cascading.
    """

    def __init__(self):
        self._keys = chatbot_settings.get_groq_keys()
        self._key_index = 0
        self._client_pool: Dict[str, Groq] = {}

    def is_available(self) -> bool:
        current_keys = chatbot_settings.get_groq_keys()
        if current_keys:
            self._keys = current_keys
        return len(self._keys) > 0

    def _get_client_for_key(self, api_key: str) -> Groq:
        if api_key not in self._client_pool:
            self._client_pool[api_key] = Groq(
                api_key=api_key,
                timeout=chatbot_settings.CHATBOT_GROQ_TIMEOUT
            )
        return self._client_pool[api_key]

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500,
    ) -> Dict[str, Any]:
        # Dynamically refresh keys from settings
        current_keys = chatbot_settings.get_groq_keys()
        if current_keys:
            self._keys = current_keys

        if not self._keys:
            raise RuntimeError("No Groq API keys configured.")

        # Candidate models to cascade through if a model is unavailable or rate-limited
        models_to_try = [
            chatbot_settings.CHATBOT_GROQ_MODEL,
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        ]
        # Remove duplicates while preserving priority
        unique_models: List[str] = []
        for m in models_to_try:
            if m and m not in unique_models:
                unique_models.append(m)

        # Ensure max_tokens doesn't blow past free-tier TPM (8000 tokens)
        effective_max_tokens = min(max_tokens, 1500)

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        attempts = 0
        max_attempts = len(self._keys) * max(2, chatbot_settings.CHATBOT_GROQ_MAX_RETRIES)
        last_error = None

        while attempts < max_attempts:
            current_key = self._keys[self._key_index % len(self._keys)]
            client = self._get_client_for_key(current_key)

            # Pick model: cycle through candidate models across retry attempts
            model_index = (attempts // len(self._keys)) % len(unique_models)
            selected_model = unique_models[model_index]

            try:
                t0 = time.perf_counter()
                completion = client.chat.completions.create(
                    model=selected_model,
                    messages=formatted_messages,
                    temperature=temperature,
                    max_tokens=effective_max_tokens,
                )
                latency = round(time.perf_counter() - t0, 3)

                reply_text = completion.choices[0].message.content or ""
                # If reply is completely empty (e.g. reasoning token exhaustion), trigger rotation
                if not reply_text.strip():
                    raise APIError(
                        message=f"Model {selected_model} returned empty content",
                        request=None,
                        body=None
                    )

                return {
                    "reply": reply_text.strip(),
                    "provider": "groq",
                    "model": selected_model,
                    "latency": latency,
                    "tokens_used": completion.usage.total_tokens if completion.usage else 0,
                    "key_masked": f"...{current_key[-6:]}" if len(current_key) > 6 else "key",
                }

            except (RateLimitError, APIError, APITimeoutError) as exc:
                last_error = exc
                attempts += 1
                logger.warning(
                    f"Groq Chatbot key ...{current_key[-6:]} with model '{selected_model}' encountered {exc.__class__.__name__}. "
                    f"Rotating to next key in pool..."
                )
                # Rotate to next key in round-robin fashion
                self._key_index = (self._key_index + 1) % len(self._keys)
                time.sleep(0.1)

            except Exception as exc:
                last_error = exc
                attempts += 1
                self._key_index = (self._key_index + 1) % len(self._keys)
                logger.warning(f"Unexpected error on Groq Chatbot provider with model '{selected_model}': {exc}")

        raise RuntimeError(f"All Groq Chatbot keys exhausted. Last error: {last_error}")
