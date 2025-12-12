"""pit chat - LLM 연동 채팅"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from pit.core.health_check import check_feature_health, check_project_health
from pit.loaders import (
    get_feature,
    get_next_decision_id,
    get_next_feature_id,
    list_features,
    list_projects,
    save_decision,
    save_feature,
    save_log,
)
from pit.models.feature import Checklist, Feature

# Load .env
load_dotenv()

SYSTEM_PROMPT = """당신은 pit (Product/Idea Tracker)의 AI 어시스턴트입니다.

## pit이란?
- 기획/아이디어/결정/체크리스트를 Git처럼 버전 관리하는 PM용 도구
- Feature ID(F-0001)로 기획 ↔ git 브랜치/PR을 연결
- 파일 기반 SSOT (projects/<project_id>/ 폴더에 YAML/MD 저장)

## 핵심 개념
- **Project**: 제품/서비스 단위 (예: pit, slam)
- **Feature**: 기획→개발→배포 작업 단위 (F-0001, F-0002...)
- **Checklist**: Feature 내 할 일 (T1, T2...)
- **Decision**: 결정 기록 (D-0001)
- **Log**: 회의/대화 로그

## pit-flow
planned → in_progress → ready_for_merge → merged → released

## 당신의 역할
1. 사용자와 대화하며 기획 내용을 정리
2. 대화 내용을 Feature/Decision/Log로 구조화
3. pit 도구를 사용해 데이터 조회/생성
4. 헬스 체크 결과 설명

## 규칙
- 항상 한국어로 응답
- Feature 생성 시 사용자 확인 후 저장
- 간결하고 실용적으로 응답
"""

# Tool definitions for Claude
TOOLS = [
    {
        "name": "list_projects",
        "description": "모든 프로젝트 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_features",
        "description": "특정 프로젝트의 Feature 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "프로젝트 ID (예: pit, slam)",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_feature",
        "description": "특정 Feature의 상세 정보를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "프로젝트 ID"},
                "feature_id": {"type": "string", "description": "Feature ID (예: F-0001)"},
            },
            "required": ["project_id", "feature_id"],
        },
    },
    {
        "name": "check_health",
        "description": "프로젝트 또는 Feature의 헬스 상태를 확인합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "프로젝트 ID"},
                "feature_id": {
                    "type": "string",
                    "description": "Feature ID (선택, 없으면 프로젝트 전체 헬스)",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "create_feature",
        "description": "새로운 Feature를 생성합니다. 사용자가 확인한 후에만 호출하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "프로젝트 ID"},
                "title": {"type": "string", "description": "Feature 제목"},
                "context": {"type": "string", "description": "Feature 배경/맥락"},
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "요구사항 목록",
                },
                "checklist": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "할 일 목록",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "우선순위",
                },
            },
            "required": ["project_id", "title"],
        },
    },
    {
        "name": "create_decision",
        "description": "새로운 Decision(결정 기록)을 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "프로젝트 ID"},
                "title": {"type": "string", "description": "결정 제목"},
                "content": {"type": "string", "description": "결정 내용 (마크다운)"},
            },
            "required": ["project_id", "title", "content"],
        },
    },
    {
        "name": "create_log",
        "description": "새로운 Log(회의/대화 기록)를 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "프로젝트 ID"},
                "title": {"type": "string", "description": "로그 제목"},
                "content": {"type": "string", "description": "로그 내용 (마크다운)"},
            },
            "required": ["project_id", "title", "content"],
        },
    },
]


def execute_tool(name: str, input_data: dict) -> str:
    """Execute a tool and return result as string"""
    try:
        if name == "list_projects":
            projects = list_projects()
            return json.dumps(
                [{"id": p.id, "name": p.name, "status": p.status} for p in projects],
                ensure_ascii=False,
            )

        elif name == "list_features":
            features = list_features(input_data["project_id"])
            return json.dumps(
                [
                    {
                        "id": f.id,
                        "title": f.title,
                        "status": f.status,
                        "progress": f"{f.progress[0]}/{f.progress[1]}",
                    }
                    for f in features
                ],
                ensure_ascii=False,
            )

        elif name == "get_feature":
            feature = get_feature(input_data["project_id"], input_data["feature_id"])
            if not feature:
                return json.dumps({"error": "Feature not found"})
            return json.dumps(feature.model_dump(mode="json", exclude_none=True), ensure_ascii=False)

        elif name == "check_health":
            project_id = input_data["project_id"]
            feature_id = input_data.get("feature_id")

            if feature_id:
                feature = get_feature(project_id, feature_id)
                if not feature:
                    return json.dumps({"error": "Feature not found"})
                result = check_feature_health(feature)
            else:
                features = list_features(project_id)
                result = check_project_health(features)

            return json.dumps(
                {"status": result.status.value, "score": result.score, "reasons": result.reasons},
                ensure_ascii=False,
            )

        elif name == "create_feature":
            from datetime import datetime

            project_id = input_data["project_id"]
            feature_id = get_next_feature_id(project_id)

            checklist = []
            for i, task in enumerate(input_data.get("checklist", []), 1):
                checklist.append(Checklist(id=f"T{i}", label=task, type="code", done=False))

            feature = Feature(
                id=feature_id,
                project_id=project_id,
                title=input_data["title"],
                context=input_data.get("context"),
                requirements=input_data.get("requirements", []),
                checklist=checklist,
                priority=input_data.get("priority", "medium"),
                status="planned",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            filepath = save_feature(feature)
            return json.dumps(
                {"success": True, "feature_id": feature_id, "file": str(filepath)},
                ensure_ascii=False,
            )

        elif name == "create_decision":
            decision_id = get_next_decision_id(input_data["project_id"])
            filepath = save_decision(
                input_data["project_id"],
                decision_id,
                input_data["title"],
                input_data["content"],
            )
            return json.dumps(
                {"success": True, "decision_id": decision_id, "file": str(filepath)},
                ensure_ascii=False,
            )

        elif name == "create_log":
            filepath = save_log(
                input_data["project_id"],
                input_data["title"],
                input_data["content"],
            )
            return json.dumps({"success": True, "file": str(filepath)}, ensure_ascii=False)

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


class PitChat:
    """pit 채팅 세션"""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")

        self.client = Anthropic(api_key=api_key)
        self.messages = []

    def chat(self, user_message: str) -> str:
        """Send a message and get response"""
        self.messages.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self.messages,
        )

        # Process response (may involve tool calls)
        while response.stop_reason == "tool_use":
            # Find tool use blocks
            tool_results = []
            assistant_content = response.content

            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            # Add assistant message and tool results
            self.messages.append({"role": "assistant", "content": assistant_content})
            self.messages.append({"role": "user", "content": tool_results})

            # Get next response
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
            )

        # Extract final text response
        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        self.messages.append({"role": "assistant", "content": response.content})

        return final_text
