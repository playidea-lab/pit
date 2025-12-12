"""pit MCP Server - Claude Desktop/Code에서 pit 도구 사용

.pit/ 폴더 기반 로컬 프로젝트 관리
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# pit 경로 설정
PIT_ROOT = os.environ.get("PIT_ROOT", str(Path.cwd()))
sys.path.insert(0, PIT_ROOT)

from pit.core.context import find_pit_root, get_project_context  # noqa: E402
from pit.core.health_check import check_feature_health, check_project_health  # noqa: E402
from pit.loaders import (  # noqa: E402
    get_feature,
    get_next_decision_id,
    get_next_feature_id,
    list_features,
    save_decision,
    save_feature,
    save_log,
)
from pit.models.feature import Checklist, Feature  # noqa: E402

# MCP Server 인스턴스
server = Server("pit")


@server.list_tools()
async def list_tools():
    """사용 가능한 pit 도구 목록"""
    return [
        Tool(
            name="pit_detect_context",
            description="주어진 경로에서 pit 프로젝트 컨텍스트(.pit/)를 감지합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: 현재 디렉토리)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="pit_list_features",
            description="현재 프로젝트의 Feature 목록을 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: PIT_ROOT)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="pit_get_feature",
            description="특정 Feature의 상세 정보를 조회합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID (예: F-0001)"},
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: PIT_ROOT)",
                    },
                },
                "required": ["feature_id"],
            },
        ),
        Tool(
            name="pit_check_health",
            description="프로젝트 또는 Feature의 헬스 상태를 확인합니다. Green/Yellow/Red 신호와 점수를 반환합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "feature_id": {
                        "type": "string",
                        "description": "Feature ID (선택, 없으면 프로젝트 전체 헬스)",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: PIT_ROOT)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="pit_create_feature",
            description="새로운 Feature를 생성합니다. 기획 내용을 구조화하여 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
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
                        "description": "할 일 목록 (체크리스트)",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "우선순위 (기본: medium)",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: PIT_ROOT)",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="pit_create_decision",
            description="새로운 Decision(결정 기록)을 생성합니다. 왜 이런 결정을 했는지 기록합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "결정 제목"},
                    "content": {"type": "string", "description": "결정 내용 (마크다운)"},
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: PIT_ROOT)",
                    },
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="pit_create_log",
            description="새로운 Log(회의/대화 기록)를 생성합니다. 논의 내용을 정리하여 저장합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "로그 제목"},
                    "content": {"type": "string", "description": "로그 내용 (마크다운)"},
                    "cwd": {
                        "type": "string",
                        "description": "작업 디렉토리 경로 (기본: PIT_ROOT)",
                    },
                },
                "required": ["title", "content"],
            },
        ),
    ]


def get_pit_dir(cwd: str | None) -> Path | None:
    """Get .pit directory from cwd"""
    start = Path(cwd) if cwd else Path(PIT_ROOT)
    return find_pit_root(start)


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """도구 실행"""
    cwd = arguments.get("cwd")

    try:
        if name == "pit_detect_context":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(
                    type="text",
                    text=json.dumps(
                        {"found": False, "message": "pit 프로젝트를 찾을 수 없습니다. 'pit init'으로 초기화하세요."},
                        ensure_ascii=False,
                    ),
                )]

            context = get_project_context(Path(cwd) if cwd else None)
            return [TextContent(
                type="text",
                text=json.dumps(
                    {
                        "found": True,
                        "pit_root": str(pit_dir),
                        "project_id": context.get("id") if context else None,
                        "project_name": context.get("name") if context else None,
                    },
                    ensure_ascii=False,
                ),
            )]

        elif name == "pit_list_features":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(type="text", text="pit 프로젝트를 찾을 수 없습니다.")]

            features_dir = pit_dir / "features"
            if not features_dir.exists():
                return [TextContent(type="text", text="[]")]

            features = list_features()
            result = [
                {
                    "id": f.id,
                    "title": f.title,
                    "status": f.status,
                    "priority": f.priority,
                    "progress": f"{f.progress[0]}/{f.progress[1]}",
                }
                for f in features
            ]
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

        elif name == "pit_get_feature":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(type="text", text="pit 프로젝트를 찾을 수 없습니다.")]

            feature = get_feature(feature_id=arguments["feature_id"])
            if not feature:
                return [TextContent(type="text", text="Feature not found")]
            return [TextContent(
                type="text",
                text=json.dumps(feature.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2),
            )]

        elif name == "pit_check_health":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(type="text", text="pit 프로젝트를 찾을 수 없습니다.")]

            feature_id = arguments.get("feature_id")

            if feature_id:
                feature = get_feature(feature_id=feature_id)
                if not feature:
                    return [TextContent(type="text", text="Feature not found")]
                result = check_feature_health(feature)
            else:
                features = list_features()
                result = check_project_health(features)

            return [TextContent(
                type="text",
                text=json.dumps(
                    {"status": result.status.value, "score": result.score, "reasons": result.reasons},
                    ensure_ascii=False,
                    indent=2,
                ),
            )]

        elif name == "pit_create_feature":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(type="text", text="pit 프로젝트를 찾을 수 없습니다.")]

            context = get_project_context()
            project_id = context.get("id") if context else "unknown"
            feature_id = get_next_feature_id()

            checklist = []
            for i, task in enumerate(arguments.get("checklist", []), 1):
                checklist.append(Checklist(id=f"T{i}", label=task, type="code", done=False))

            feature = Feature(
                id=feature_id,
                project_id=project_id,
                title=arguments["title"],
                context=arguments.get("context"),
                requirements=arguments.get("requirements", []),
                checklist=checklist,
                priority=arguments.get("priority", "medium"),
                status="planned",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            filepath = save_feature(feature)
            return [TextContent(
                type="text",
                text=json.dumps(
                    {"success": True, "feature_id": feature_id, "file": str(filepath)},
                    ensure_ascii=False,
                ),
            )]

        elif name == "pit_create_decision":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(type="text", text="pit 프로젝트를 찾을 수 없습니다.")]

            decision_id = get_next_decision_id()
            filepath = save_decision(
                None,  # project_id is None for new mode
                decision_id,
                arguments["title"],
                arguments["content"],
            )
            return [TextContent(
                type="text",
                text=json.dumps(
                    {"success": True, "decision_id": decision_id, "file": str(filepath)},
                    ensure_ascii=False,
                ),
            )]

        elif name == "pit_create_log":
            pit_dir = get_pit_dir(cwd)
            if not pit_dir:
                return [TextContent(type="text", text="pit 프로젝트를 찾을 수 없습니다.")]

            filepath = save_log(
                None,  # project_id is None for new mode
                arguments["title"],
                arguments["content"],
            )
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "file": str(filepath)}, ensure_ascii=False),
            )]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """MCP 서버 실행"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
