# pithub MCP 서버 이미지 (Fly.io)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# 의존성 층을 먼저 만들어 코드만 바뀔 때 다시 받지 않게 한다
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra server --no-install-project

COPY pit ./pit
RUN uv sync --frozen --no-dev --extra server

# 호스트의 파일 권한(예: 600)이 그대로 복사되므로, 비루트 사용자가 읽을 수 있게 맞춘다
RUN useradd --create-home pithub && chmod -R a+rX /app
USER pithub

# 컨테이너 안에서는 모든 인터페이스에서 받는다. 포트는 fly.toml의 internal_port와 맞춘다.
ENV PITHUB_MCP_HOST=0.0.0.0 PITHUB_MCP_PORT=8080 PATH="/app/.venv/bin:$PATH"
EXPOSE 8080

CMD ["python", "-m", "pit.server"]
