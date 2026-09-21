"""Anthropic Messages API 구현

자유 텍스트를 파싱하지 않는다. 도구 하나를 강제로 호출하게 해서
스키마에 맞는 입력값만 받는다.
"""

import logging
import os

import anthropic

from pit.llm.client import LLMError, StructuredRequest
from pit.transcripts.records import JsonObject

logger = logging.getLogger(__name__)

API_KEY_ENV = "ANTHROPIC_API_KEY"


class AnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get(API_KEY_ENV)
        if not key:
            raise LLMError(f"환경변수 {API_KEY_ENV} 가 없습니다.")
        self._client = anthropic.Anthropic(api_key=key)

    def complete_structured(self, request: StructuredRequest) -> JsonObject:
        try:
            response = self._client.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                tools=[
                    {
                        "name": request.tool_name,
                        "description": request.tool_description,
                        "input_schema": request.schema,
                    }
                ],
                tool_choice={"type": "tool", "name": request.tool_name},
            )
        except anthropic.APIError as e:
            logger.error("LLM 호출 실패", extra={"model": request.model, "error": type(e).__name__})
            raise LLMError(f"LLM 호출 실패: {type(e).__name__}") from e

        for block in response.content:
            if block.type == "tool_use" and isinstance(block.input, dict):
                return block.input
        raise LLMError("응답에 구조화된 값이 없습니다.")
