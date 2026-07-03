from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from core.secrets import get_secret


class LLMClient:
    def __init__(self, llm_config: dict):
        api_key = get_secret("LLM_API_KEY")
        if not api_key:
            raise ValueError("LLM_API_KEY not set in .env")

        self._llm = ChatOpenAI(
            model=llm_config.get("model", "deepseek-v4-flash"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 8000),
            api_key=api_key,
            base_url=llm_config.get("base_url", "https://api.deepseek.com"),
            timeout=llm_config.get("timeout", 30),
            extra_body={"thinking": {"type": "disabled"}},
        )

    def invoke(self, system_prompt: str, user_msg: str) -> dict:
        """Call the LLM with a system prompt and user message, return parsed JSON dict.

        Raises an exception on failure — callers are responsible for error handling.
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ]
        chain = (self._llm | JsonOutputParser()).with_retry(stop_after_attempt=2)
        return chain.invoke(messages)
