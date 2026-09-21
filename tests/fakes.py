"""테스트용 가짜 구현"""

from dataclasses import dataclass, field

from pit.llm.client import LLMError, StructuredRequest
from pit.transcripts.records import JsonObject


@dataclass
class FakeLLMClient:
    """정해 둔 응답을 차례로 돌려주고, 받은 요청을 전부 기록한다

    응답 자리에 예외 객체를 넣으면 그 차례에 예외를 던진다.
    기록된 요청은 '이 글이 LLM에게 넘어갔는가'를 단언하는 데 쓴다.
    """

    responses: list[JsonObject | Exception] = field(default_factory=list)
    requests: list[StructuredRequest] = field(default_factory=list)

    def complete_structured(self, request: StructuredRequest) -> JsonObject:
        self.requests.append(request)
        if not self.responses:
            raise LLMError("준비된 응답이 없습니다")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def all_request_text(self) -> str:
        return "\n".join(f"{r.system}\n{r.user}" for r in self.requests)


class FakeClock:
    """호출할 때마다 정해진 만큼 흐르는 단조 시계 (테스트에서 sleep을 쓰지 않기 위함)"""

    def __init__(self, step_seconds: float = 1.0) -> None:
        self._now = 0.0
        self._step = step_seconds

    def __call__(self) -> float:
        self._now += self._step
        return self._now
