import logging
from typing import Any, Dict, List, Optional
from universal_chatbot.backend.app.ai.groq_provider import GroqChatbotProvider
from universal_chatbot.backend.app.ai.fallback_provider import FallbackHTTPProvider

logger = logging.getLogger(__name__)


class MultiProviderAIEngine:
    """
    Master AI Provider Manager for Universal Chatbot.
    Orchestrates:
      1. Primary Groq Key Rotation Pool (instant failover on 429 rate limit)
      2. Secondary Multi-Provider Fallback Pool (OpenRouter / DeepSeek / Mistral)
      3. Graceful degradation when external providers are unreachable
    """

    def __init__(self):
        self.groq_provider = GroqChatbotProvider()
        self.fallback_provider = FallbackHTTPProvider()

    def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        language: str = "en",
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Generate response attempting primary key rotation pool first, then secondary fallback."""
        # 1. Attempt Primary Groq Key Rotation Pool
        if self.groq_provider.is_available():
            try:
                res = self.groq_provider.generate_response(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return res
            except Exception as exc:
                logger.warning(
                    f"Primary Groq Chatbot pool failed: {exc}. Trying secondary fallback provider..."
                )

        # 2. Attempt Secondary Fallback Provider Pool
        if self.fallback_provider.is_available():
            try:
                res = self.fallback_provider.generate_response(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return res
            except Exception as exc:
                logger.error(f"Secondary fallback provider failed: {exc}")

        # 3. Emergency Rule-Based Fallback if all API keys fail
        logger.error("All AI providers exhausted.")
        if language == "ta":
            fallback_text = (
                "மன்னிக்கவும், AI சேவை தற்போது அதிக சுமையில் உள்ளது. "
                "சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும் அல்லது மனித உதவியாளரை அணுகவும்."
            )
        else:
            fallback_text = (
                "I apologize, but our AI service is currently experiencing high demand. "
                "Please try again shortly or click 'Talk to Human Agent' for live support."
            )

        return {
            "reply": fallback_text,
            "provider": "emergency_fallback",
            "model": "offline_rule",
            "latency": 0.001,
            "tokens_used": 0,
        }


# Global singleton instance
ai_engine = MultiProviderAIEngine()
