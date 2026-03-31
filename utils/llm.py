import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
import litellm

# Load dotenv if available
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
logger = logging.getLogger("opc.llm")


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    """Extract the first valid JSON object from a noisy LLM response."""
    if not text:
        raise json.JSONDecodeError("Empty response", text or "", 0)

    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(clean):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(clean[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("No valid JSON object found", clean, 0)


class LLMService:
    """Wrapper around LiteLLM to provide a unified interface for agents."""

    # Track cumulative token usage across all calls
    _total_prompt_tokens = 0
    _total_completion_tokens = 0
    _total_calls = 0
    _total_cost: float = 0.0

    # Pricing per 1M tokens (input, output) in USD
    # Updated as of 2024-12 approximate pricing
    MODEL_PRICING: Dict[str, tuple] = {
        # OpenAI
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o1": (15.00, 60.00),
        "o1-mini": (3.00, 12.00),
        # Anthropic
        "claude-3-opus": (15.00, 75.00),
        "claude-3-sonnet": (3.00, 15.00),
        "claude-3-haiku": (0.25, 1.25),
        "claude-3.5-sonnet": (3.00, 15.00),
        # DeepSeek
        "deepseek-chat": (0.14, 0.28),
        "deepseek-coder": (0.14, 0.28),
        # MiniMax
        "minimax": (0.70, 0.70),
    }

    # Environment variable cache for performance
    _env_cache: dict = {}

    @classmethod
    def _get_env(cls, key: str, default: str) -> str:
        """Get cached environment variable."""
        if key not in cls._env_cache:
            cls._env_cache[key] = os.getenv(key, default)
        return cls._env_cache[key]

    def __init__(
        self,
        model_name: str = "openai/gpt-4o",
        max_retries: int = 3,
        timeout: int = 120,
    ):
        """
        Initialize the LLM Service.
        Supports OpenAI, MiniMax, Claude, etc via LiteLLM format.
        """
        self.model_name = model_name
        self.max_retries = max_retries
        self.timeout = int(self._get_env("LLM_TIMEOUT", str(timeout)))
        self.max_context_tokens = int(self._get_env("MAX_CONTEXT_TOKENS", "120000"))

        # Fallback to env if model is the default placeholder
        if model_name == "openai/gpt-4o":
            default_model = self._get_env("DEFAULT_LLM_MODEL", "")
            if default_model:
                self.model_name = default_model

    def _call_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Internal method with exponential backoff retry."""
        from utils.telemetry import trace_span

        last_error: Exception = RuntimeError("No LLM call attempted")

        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "timeout": self.timeout,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                with trace_span(
                    "llm.call",
                    {
                        "model": self.model_name,
                        "attempt": attempt,
                        "temperature": temperature,
                    },
                ) as span:
                    call_start = time.time()
                    response = litellm.completion(**kwargs)
                    call_elapsed = time.time() - call_start

                    # Track token usage
                    usage = getattr(response, "usage", None)
                    prompt_tok = 0
                    compl_tok = 0
                    if usage:
                        prompt_tok = getattr(usage, "prompt_tokens", 0)
                        compl_tok = getattr(usage, "completion_tokens", 0)
                        LLMService._total_prompt_tokens += prompt_tok
                        LLMService._total_completion_tokens += compl_tok
                        # Calculate cost
                        cost = self._calculate_cost(prompt_tok, compl_tok)
                        LLMService._total_cost += cost
                        # Add token info to span
                        if span:
                            span.set_attribute("tokens.prompt", prompt_tok)
                            span.set_attribute("tokens.completion", compl_tok)
                            span.set_attribute("cost.usd", round(cost, 6))
                        # Check budget limit
                        max_cost = float(os.getenv("MAX_COST_USD", "0"))
                        if max_cost > 0 and LLMService._total_cost >= max_cost:
                            logger.warning(
                                f"Budget limit ${max_cost:.2f} reached (spent ${LLMService._total_cost:.4f}). "
                                f"Set MAX_COST_USD to increase."
                            )
                    LLMService._total_calls += 1

                    # Record trace (v2.6.0)
                    try:
                        from utils.trace_logger import get_trace_logger

                        output_text = ""
                        if response.choices:
                            output_text = (
                                getattr(response.choices[0].message, "content", "")
                                or ""
                            )
                        get_trace_logger().log(
                            model_name=self.model_name,
                            input_messages=messages,
                            output_text=output_text,
                            prompt_tokens=prompt_tok,
                            completion_tokens=compl_tok,
                            elapsed_seconds=round(call_elapsed, 3),
                        )
                    except Exception:
                        pass  # Trace logging should never break LLM calls

                    return response

            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = 2**attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(
                        f"Attempt {attempt}/{self.max_retries} failed: {e}. Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)

        logger.error(
            f"All {self.max_retries} attempts failed. Last error: {last_error}"
        )
        raise last_error

    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Generate a text response using the selected model."""
        response = self._call_with_retry(messages, temperature)
        return response.choices[0].message.content

    def generate_json(
        self, messages: List[Dict[str, str]], temperature: float = 0.1
    ) -> Dict[str, Any]:
        """Generate a JSON response. Attempts structured output first, falls back to prompt-based."""
        # Copy messages to avoid mutating the caller's list
        messages = [msg.copy() for msg in messages]

        # Add JSON instruction to system message
        has_system = any(msg.get("role") == "system" for msg in messages)
        json_instruction = "You must output ONLY valid JSON, without markdown formatting or introductory text."

        if not has_system:
            messages.insert(0, {"role": "system", "content": json_instruction})
        else:
            for msg in messages:
                if msg.get("role") == "system":
                    msg["content"] = f"{msg['content']}\n{json_instruction}"
                    break

        # Try with response_format first (structured output)
        try:
            response = self._call_with_retry(
                messages, temperature, response_format={"type": "json_object"}
            )
            raw_output = response.choices[0].message.content
        except Exception:
            # Fallback: some models don't support response_format
            response = self._call_with_retry(messages, temperature)
            raw_output = response.choices[0].message.content

        try:
            return _extract_first_json_object(raw_output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}\nRaw output: {raw_output}")
            raise

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost in USD based on model pricing table."""
        # Strip provider prefix (e.g. 'openai/gpt-4o' → 'gpt-4o')
        model_key = (
            self.model_name.split("/")[-1]
            if "/" in self.model_name
            else self.model_name
        )
        # Try exact match, then prefix match
        pricing = self.MODEL_PRICING.get(model_key)
        if not pricing:
            for key, val in self.MODEL_PRICING.items():
                if model_key.startswith(key):
                    pricing = val
                    break
        if not pricing:
            return 0.0
        input_price, output_price = pricing
        return (
            prompt_tokens * input_price + completion_tokens * output_price
        ) / 1_000_000

    @classmethod
    def print_usage_summary(cls):
        """Print cumulative token usage and cost statistics."""
        total_tokens = cls._total_prompt_tokens + cls._total_completion_tokens
        logger.info(f"LLM Usage Summary:")
        logger.info(f"   Total Calls    : {cls._total_calls}")
        logger.info(f"   Prompt Tokens  : {cls._total_prompt_tokens:,}")
        logger.info(f"   Completion Tok : {cls._total_completion_tokens:,}")
        logger.info(f"   Total Tokens   : {total_tokens:,}")
        logger.info(f"   Total Cost     : ${cls._total_cost:.4f} USD")

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimation (~4 chars per token for English, ~2 for CJK).

        Use this to check if a prompt will exceed the model's context window
        before making an API call.
        """
        # Count CJK characters (roughly 1 token each)
        cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        # Non-CJK characters (~4 chars per token)
        other_count = len(text) - cjk_count
        return cjk_count + (other_count // 4)

    @classmethod
    def truncate_to_budget(
        cls, text: str, budget_tokens: int, label: str = "content"
    ) -> str:
        """Truncate text to fit within a token budget.

        If estimated tokens exceed budget, truncate and append a warning.
        """
        estimated = cls.estimate_tokens(text)
        if estimated <= budget_tokens:
            return text

        # Approximate character count for budget (use 3 chars/token as safe average)
        target_chars = budget_tokens * 3
        truncated = text[:target_chars]
        logger.warning(
            f"{label}: truncated from ~{estimated:,} to ~{budget_tokens:,} tokens"
        )
        return (
            truncated
            + f"\n\n... [TRUNCATED: ~{estimated:,} tokens exceeded budget of {budget_tokens:,}]"
        )
