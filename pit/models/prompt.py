"""Prompt model - 재사용 가능한 프롬프트 템플릿"""

import re
from typing import Optional

from pydantic import BaseModel, Field


class PromptVariable(BaseModel):
    """프롬프트 변수 정의"""

    name: str = Field(..., description="변수 이름")
    description: Optional[str] = Field(None, description="변수 설명")
    required: bool = Field(default=True, description="필수 여부")
    default: Optional[str] = Field(None, description="기본값")
    enum: Optional[list[str]] = Field(None, description="허용 값 목록")


class Prompt(BaseModel):
    """Prompt - 재사용 가능한 프롬프트 템플릿"""

    id: str = Field(..., description="Prompt ID (파일명에서 추출)")
    name: str = Field(..., description="Prompt 이름")
    description: Optional[str] = Field(None, description="Prompt 설명")

    # 변수 정의
    variables: list[PromptVariable] = Field(
        default_factory=list, description="템플릿 변수 목록"
    )

    # 프롬프트 본문 (Markdown)
    content: str = Field(..., description="프롬프트 템플릿 본문")

    # 출력 연결
    output_tool: Optional[str] = Field(
        None, description="실행 후 호출할 Tool (예: pit_create_feature)"
    )

    # 연결된 Agent
    agent: Optional[str] = Field(None, description="이 프롬프트를 사용할 Agent ID")

    def render(self, variables: dict[str, str]) -> str:
        """변수를 치환하여 최종 프롬프트 생성

        {{variable_name}} 패턴을 실제 값으로 치환
        """
        result = self.content

        # 변수 유효성 검사
        for var in self.variables:
            if var.required and var.name not in variables and var.default is None:
                raise ValueError(f"Required variable '{var.name}' is missing")

            # 기본값 적용
            if var.name not in variables and var.default is not None:
                variables[var.name] = var.default

            # enum 검증
            if var.enum and var.name in variables:
                if variables[var.name] not in var.enum:
                    raise ValueError(
                        f"Variable '{var.name}' must be one of {var.enum}, "
                        f"got '{variables[var.name]}'"
                    )

        # 변수 치환
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return variables.get(var_name, match.group(0))

        result = re.sub(r"\{\{(\w+)\}\}", replacer, result)

        return result

    def get_variable(self, name: str) -> Optional[PromptVariable]:
        """변수 정의 조회"""
        for var in self.variables:
            if var.name == name:
                return var
        return None

    def get_required_variables(self) -> list[PromptVariable]:
        """필수 변수 목록"""
        return [v for v in self.variables if v.required and v.default is None]

    def get_optional_variables(self) -> list[PromptVariable]:
        """선택 변수 목록"""
        return [v for v in self.variables if not v.required or v.default is not None]
