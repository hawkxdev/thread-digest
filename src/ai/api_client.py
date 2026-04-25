"""DeepSeek API client with unified logging."""

import time
from dataclasses import dataclass
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from ..config import Config


@dataclass
class APIResponse:
    content: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    execution_time: float
    success: bool


class DeepSeekClient:
    """Async DeepSeek API client."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._client = AsyncOpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            max_retries=3,
            timeout=120.0,
        )

    async def close(self) -> None:
        await self._client.close()

    async def chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = True,
        operation_name: str = 'API Call',
        request_id: str = '',
    ) -> APIResponse:
        """Execute Chat API request with logging."""
        temp = (
            temperature
            if temperature is not None
            else self.config.DEEPSEEK_TEMPERATURE
        )
        tokens = (
            max_tokens
            if max_tokens is not None
            else self.config.DEEPSEEK_MAX_TOKENS
        )

        messages: list[dict[str, Any]] = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ]

        start_time = time.time()

        try:
            kwargs: dict[str, Any] = {
                'model': self.config.DEEPSEEK_MODEL,
                'messages': messages,
                'temperature': temp,
                'max_tokens': tokens,
            }

            if json_mode:
                kwargs['response_format'] = {'type': 'json_object'}

            response = await self._client.chat.completions.create(**kwargs)

            execution_time = time.time() - start_time

            prompt_tokens = (
                response.usage.prompt_tokens if response.usage else 0
            )
            completion_tokens = (
                response.usage.completion_tokens if response.usage else 0
            )
            total_tokens = response.usage.total_tokens if response.usage else 0

            content = (
                response.choices[0].message.content
                if response.choices
                else None
            )

            req_suffix = f' | 📄 Request: {request_id}' if request_id else ''

            logger.debug(
                f'🤖 DeepSeek API - {operation_name} | '
                f'✅ Success | '
                f'📤 Sent: {prompt_tokens} tokens | '
                f'📥 Received: {completion_tokens} tokens | '
                f'📊 Total: {total_tokens} tokens | '
                f'⏱️ Time: {execution_time:.2f}s{req_suffix}'
            )

            return APIResponse(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                execution_time=execution_time,
                success=content is not None,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            req_suffix = f' | 📄 Request: {request_id}' if request_id else ''

            logger.error(
                f'🤖 DeepSeek API - {operation_name} | '
                f'❌ Error | '
                f'⏱️ Time: {execution_time:.2f}s{req_suffix} | '
                f'🔥 {e}'
            )

            return APIResponse(
                content=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                execution_time=execution_time,
                success=False,
            )
