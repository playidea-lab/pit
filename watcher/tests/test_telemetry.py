from git_watcher.telemetry import summarize_logs


def otlp(attrs: dict[str, object], resource: dict[str, object] | None = None) -> dict:
    def kv(d: dict[str, object]) -> list[dict]:
        out = []
        for k, v in d.items():
            key = "intValue" if isinstance(v, int) and not isinstance(v, bool) else "stringValue"
            out.append({"key": k, "value": {key: str(v) if key == "intValue" else v}})
        return out
    return {"resourceLogs": [{"resource": {"attributes": kv(resource or {"service.name": "claude-code"})},
                              "scopeLogs": [{"logRecords": [{"timeUnixNano": "1790000000000000000",
                                                             "attributes": kv(attrs)}]}]}]}


def test_summarize_keeps_summary_fields_and_drops_text() -> None:
    events, keys = summarize_logs(otlp({
        "event.name": "user_prompt", "prompt_length": 120, "prompt": "비밀 프롬프트 원문",
        "session.id": "s1", "user.email": "a@corp.com",
    }))
    e = events[0]
    assert e["event.name"] == "user_prompt" and e["prompt_length"] == 120 and e["session.id"] == "s1"
    assert "prompt" not in e and "비밀" not in str(e)
    # 받은 속성 '이름'은 남겨 무엇이 오는지 알 수 있게 한다
    assert "prompt" in keys


def test_summarize_drops_tool_output_snippet_even_if_named_like_allowed() -> None:
    events, _ = summarize_logs(otlp({"event.name": "codex.tool_result", "tool_name": "shell",
                                     "duration_ms": 30, "output": "ls 결과", "arguments": "rm -rf"},
                                    {"service.name": "codex_cli_rs"}))
    e = events[0]
    assert e["tool_name"] == "shell" and e["duration_ms"] == 30 and e["service.name"] == "codex_cli_rs"
    assert "output" not in e and "arguments" not in e
    assert e["ts"].startswith("2026-09-")


def test_summarize_keeps_token_counts_and_custom_repo_attribute() -> None:
    events, _ = summarize_logs(otlp({"event.name": "api_request", "output_tokens": 50, "input_tokens": 9},
                                    {"service.name": "claude-code", "repo.name": "pi/phenotype"}))
    e = events[0]
    assert e["output_tokens"] == 50 and e["input_tokens"] == 9 and e["repo.name"] == "pi/phenotype"


def test_summarize_falls_back_to_event_timestamp_when_otlp_time_is_empty() -> None:
    payload = otlp({"event.name": "codex.user_prompt", "event.timestamp": "2026-10-03T23:05:49.393Z"},
                   {"service.name": "codex_exec"})
    payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["timeUnixNano"] = "0"
    (e,), _ = summarize_logs(payload)
    assert e["ts"].startswith("2026-10-03T23:05:49")
