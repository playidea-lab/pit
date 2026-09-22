"""`python -m pit.server` — 원격 MCP 서버를 HTTP로 띄운다"""

import logging
import sys

from pit.server.app import build_server
from pit.server.settings import SettingsError, load_settings

logger = logging.getLogger("pit.server")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings()
    except SettingsError as e:
        logger.error("서버를 시작할 수 없음: %s", e)
        sys.exit(1)

    logger.info("pithub MCP 서버 시작", extra={"host": settings.host, "port": settings.port})
    # stateless: 요청마다 독립 처리. 재배포로 프로세스가 바뀌어도 클라이언트의 세션 ID가
    # 무효가 되지 않는다 ("No valid session ID"). 서버가 먼저 알림을 보낼 일이 없어 잃는 것이 없다.
    build_server(settings).run(
        transport="http", host=settings.host, port=settings.port, stateless_http=True
    )


if __name__ == "__main__":
    main()
