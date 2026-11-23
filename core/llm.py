"""Synchronous model requests with explicit wire-protocol dispatch."""

import json
import re
import time
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self
from urllib.parse import urlsplit

import httpx


@dataclass(frozen=True)
class LLMConfig:
    protocol: Literal["openai_chat_completions"]
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    timeout: float
    thinking: Literal["default", "disabled"]


class LLMError(RuntimeError):
    """Public-safe failure without request or response contents."""


class ChatProtocol(Protocol):
    @property
    def endpoint(self) -> str: ...

    def auth_headers(self, api_key: str) -> dict[str, str]: ...

    def payload(self, system_prompt: str, user_msg: str) -> dict: ...

    def parse(self, response: httpx.Response) -> dict: ...


class OpenAIChatCompletions:
    def __init__(self, config: LLMConfig):
        self._config = config
        base = config.base_url.rstrip("/")
        parsed = urlsplit(base)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise LLMError("模型地址必须是无凭据、查询参数或片段的 HTTP(S) 地址")
        self._endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def auth_headers(self, api_key: str) -> dict[str, str]:
        if not api_key:
            raise LLMError("请先在设置中配置模型 API Key")
        if not api_key.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in api_key):
            raise LLMError("模型 API Key 格式无效，请检查设置")
        return {"Authorization": f"Bearer {api_key}"}

    def payload(self, system_prompt: str, user_msg: str) -> dict:
        payload = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        }
        if self._config.thinking == "disabled":
            payload["thinking"] = {"type": "disabled"}
        return payload

    def parse(self, response: httpx.Response) -> dict:
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Missing text content")
        content = content.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL | re.IGNORECASE)
        if fenced:
            content = fenced.group(1)
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return result


def create_protocol(config: LLMConfig) -> ChatProtocol:
    if config.protocol == "openai_chat_completions":
        return OpenAIChatCompletions(config)
    raise LLMError("不支持的模型协议")


class LLMClient:
    """Own one HTTP client for a workflow, shared by all its extractors."""

    def __init__(
        self,
        config: LLMConfig,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self._protocol = create_protocol(config)
        self._http = httpx.Client(
            headers=self._protocol.auth_headers(api_key),
            timeout=config.timeout,
            transport=transport,
            follow_redirects=False,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def invoke(self, system_prompt: str, user_msg: str) -> dict:
        payload = self._protocol.payload(system_prompt, user_msg)
        error = "模型请求失败"
        for attempt in range(2):
            retry = False
            try:
                response = self._http.post(self._protocol.endpoint, json=payload)
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    error = f"模型服务暂不可用（HTTP {response.status_code}），请稍后重试"
                    retry = True
                elif not 200 <= response.status_code < 300:
                    error = f"模型服务拒绝请求（HTTP {response.status_code}），请检查模型设置"
                else:
                    try:
                        return self._protocol.parse(response)
                    except ValueError, KeyError, IndexError, TypeError:
                        error = "模型返回的内容不是有效的 JSON 对象，请重试"
                        retry = True
            except (
                httpx.NetworkError,
                httpx.TimeoutException,
                httpx.RemoteProtocolError,
                httpx.ProxyError,
            ):
                error = "无法连接模型服务或请求超时，请检查网络与模型设置"
                retry = True
            except httpx.DecodingError:
                error = "模型响应无法解码，请重试"
                retry = True
            except httpx.HTTPError, ValueError, UnicodeError:
                error = "模型请求无法发送，请检查模型设置"
            if not retry or attempt == 1:
                break
            time.sleep(0.5)
        # Raw transport/parser errors may contain secrets; do not chain them.
        raise LLMError(error) from None
