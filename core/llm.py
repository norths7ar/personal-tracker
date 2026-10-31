from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI

from core.settings_store import decrypt_secret, read_settings


class LLMClient:
    def __init__(self, llm_config: dict):
        _, settings = read_settings()
        api_key = decrypt_secret(settings.api_key_encrypted)
        if not api_key:
            raise ValueError("请先在设置中配置模型 API Key")

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
