"""개인 보관함 설정 (twin.yaml)

사람이 직접 고치는 파일이므로 코드는 읽기만 한다. 파일이 없으면 기본값으로 동작한다.
"""

import getpass
import socket
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from pit.personal.home import CONFIG_FILENAME


class ConfigError(Exception):
    """twin.yaml 을 읽을 수 없거나 값이 잘못됨"""


class TwinConfig(BaseModel):
    """개인 보관함 설정"""

    person_id: str = Field(default_factory=getpass.getuser, description="결정의 주인")
    device: str = Field(default_factory=socket.gethostname, description="이 기기 이름")

    # 수집 자체를 하지 않는 작업 디렉터리 (개인적인 일)
    private_cwd_globs: list[str] = Field(default_factory=list)
    # 수집은 하되 대화 뷰를 만들지 않는 작업 디렉터리 (고객 데이터가 섞이는 프로젝트)
    restricted_cwd_globs: list[str] = Field(default_factory=list)
    # 대화 뷰에서 가릴 고객·기관 용어
    customer_terms: list[str] = Field(default_factory=list)
    # 통제군 입력으로 스냅샷할 파일 (~/.claude 기준 glob)
    control_input_globs: list[str] = Field(
        default_factory=lambda: ["CLAUDE.md", "rules/*.md", "projects/*/memory/*.md"]
    )


def load_config(home: Path) -> TwinConfig:
    """twin.yaml 을 읽는다. 없으면 기본 설정을 돌려준다.

    Args:
        home: 개인 보관함 경로

    Raises:
        ConfigError: YAML이 깨졌거나 필드 타입이 맞지 않을 때
    """
    path = home / CONFIG_FILENAME
    if not path.exists():
        return TwinConfig()

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return TwinConfig.model_validate(data)
    except (yaml.YAMLError, ValidationError) as e:
        raise ConfigError(f"{path} 을 읽을 수 없습니다: {e}") from e
