FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY mac_messages_mcp ./mac_messages_mcp

RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "--no-dev", "mac-messages-mcp"]
