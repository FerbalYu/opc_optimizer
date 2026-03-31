import json
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("opc.mock_llm")


class MockLLMService:
    """Mock LLM Service for testing. Returns predefined responses without API calls."""
    
    _total_prompt_tokens = 0
    _total_completion_tokens = 0
    _total_calls = 0
    
    def __init__(self, 
                 text_response: str = "Mock response",
                 json_response: Optional[Dict[str, Any]] = None,
                 model_name: str = "mock/test-model",
                 max_retries: int = 1,
                 timeout: int = 10):
        self.model_name = model_name
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_context_tokens = 120000
        self._text_response = text_response
        self._json_response = json_response or {"modifications": []}
        self._call_log: List[Dict[str, Any]] = []
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Return the predefined text response."""
        self._call_log.append({
            "method": "generate",
            "messages": messages,
            "temperature": temperature,
        })
        MockLLMService._total_calls += 1
        return self._text_response
    
    def generate_json(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> Dict[str, Any]:
        """Return the predefined JSON response."""
        self._call_log.append({
            "method": "generate_json",
            "messages": messages,
            "temperature": temperature,
        })
        MockLLMService._total_calls += 1
        return self._json_response
    
    @classmethod
    def print_usage_summary(cls):
        """Print mock usage summary."""
        logger.info(f"MockLLM Usage: {cls._total_calls} calls")
    
    @property
    def call_log(self) -> List[Dict[str, Any]]:
        """Access the log of all calls made to this mock."""
        return self._call_log
    
    def reset(self):
        """Reset call log and counters."""
        self._call_log.clear()
        MockLLMService._total_calls = 0
