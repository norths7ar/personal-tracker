import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv(Path(__file__).parent.parent / ".env")


class LLMClient:
    def __init__(self, llm_config: dict):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY not set in .env")

        self._llm = ChatOpenAI(
            model=llm_config.get("model", "deepseek-chat"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 500),
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=30,
        )

    def invoke(self, system_prompt: str, user_msg: str) -> dict:
        """Call the LLM with a system prompt and user message, return parsed JSON dict.

        Raises an exception on failure — callers are responsible for error handling.
        """
        # Escape braces so LangChain doesn't treat JSON examples as template variables.
        escaped = system_prompt.replace("{", "{{").replace("}", "}}")
        prompt = ChatPromptTemplate.from_messages([
            ("system", escaped),
            ("human", "{user_msg}"),
        ])
        chain = (prompt | self._llm | JsonOutputParser()).with_retry(stop_after_attempt=2)
        return chain.invoke({"user_msg": user_msg})
