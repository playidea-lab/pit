"""환경변수(.env)에서 실행 설정을 읽는다. URL·토큰·주소는 코드에 두지 않는다."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# launchd는 WorkingDirectory를 프로젝트 루트로 잡으므로 .env도 루트 기준으로 찾는다
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    gitlab_url: str
    gitlab_token: SecretStr

    # launchd의 PATH에는 ~/.local/bin이 없을 수 있어 절대경로로도 지정 가능
    claude_bin: str = "claude"
    claude_model: str = "opus"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    mail_from: str = ""
    mail_to: list[str] = Field(default_factory=list)
    # 인사 평가 메일 수신자. 브리핑 수신자와 일부러 분리한다 (비어 있으면 발송 거부)
    eval_mail_to: list[str] = Field(default_factory=list)
    # 평가에서 '직접 push 금지'·'테스트 동반'을 면제하는 연구 저장소 그룹 (경로 첫 부분)
    research_namespaces: list[str] = Field(default_factory=lambda: ["research"])
    # 에이전트 텔레메트리 수집기 (OTLP/HTTP JSON). 개발 기본값은 로컬만
    telemetry_host: str = "127.0.0.1"
    telemetry_port: int = 4318
    # GitHub (선택). 토큰이 없으면 GitLab만 본다. GHES면 API 주소를 바꾼다
    github_api_url: str = "https://api.github.com"
    github_token: SecretStr | None = None
    github_owners: list[str] = Field(default_factory=list)
    # --backfill 에 --who 가 없을 때 쓰는 계정 (세션 종료 훅용)
    backfill_who: str = ""

    timezone: str = "Asia/Seoul"
    # 일일 보고 기준 시각 (launchd 일정과 맞춘다). --date 재발송의 기간 경계로 쓴다
    report_hour: int = 20
    state_dir: Path = PROJECT_ROOT / ".state"
    # 첫 실행이거나 상태 파일이 없을 때 돌아볼 시간
    default_lookback_hours: int = 24
    # Mac이 며칠 꺼져 있었어도 이 이상은 한 번에 요약하지 않는다
    max_lookback_days: int = 7
