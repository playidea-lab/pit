import json

from git_watcher.backfill import transcript_events


def line(**kw: object) -> str:
    return json.dumps({"timestamp": "2026-10-04T00:00:00Z", "sessionId": "s1", **kw})


def test_transcript_keeps_human_prompts_lengths_only_and_skips_system_messages() -> None:
    lines = [
        line(type="user", promptSource="typed", message={"content": "비밀 지시 원문입니다"}),
        line(type="user", promptSource="system", message={"content": "<task-notification>끝났음"}),
        line(type="user", isMeta=True, message={"content": "메타"}),
        line(type="user", message={"content": [{"type": "tool_result", "content": "출력"}]}),
        line(type="user", message={"content": "<bash-input> ls"}),
    ]
    events = transcript_events(lines, "a@corp.com")
    expected = [("user_prompt", len("비밀 지시 원문입니다")), ("user_prompt", len("<bash-input> ls"))]
    assert [(e["event.name"], e["prompt_length"]) for e in events] == expected
    assert "비밀" not in json.dumps(events, ensure_ascii=False)


def test_transcript_counts_each_api_request_once_and_each_tool_use() -> None:
    usage = {"input_tokens": 5, "output_tokens": 7, "cache_read_input_tokens": 100}
    blocks = [{"type": "thinking"}, {"type": "tool_use", "name": "Bash", "input": {"command": "rm -rf x"}}]
    lines = [line(type="assistant", requestId="r1", message={"model": "m", "usage": usage, "content": blocks}),
             line(type="assistant", requestId="r1", message={"model": "m", "usage": usage, "content": []})]
    events = transcript_events(lines, "a@corp.com")
    assert [e["event.name"] for e in events] == ["tool_result", "api_request"]
    assert events[1]["output_tokens"] == 7 and "rm -rf" not in json.dumps(events)
