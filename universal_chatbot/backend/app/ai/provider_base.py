from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers in the Chatbot Platform."""

    @abstractmethod
    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Generate conversational response given chat history and system prompt."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider has valid configured credentials."""
        pass
