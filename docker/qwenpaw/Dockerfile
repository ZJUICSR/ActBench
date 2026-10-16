FROM ubuntu:22.04

RUN apt-get update && apt-get install --no-install-recommends -y \
        bash ca-certificates curl git jq python3 ripgrep xz-utils \
        libstdc++6 libgomp1 libportaudio2 lsof \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ARG PYTHON_VERSION=3.12.14
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_NO_CACHE=1 \
    VIRTUAL_ENV=/opt/venv PATH="/opt/venv/bin:$PATH"
RUN uv python install "${PYTHON_VERSION}" \
    && uv venv --python "${PYTHON_VERSION}" /opt/venv \
    && uv pip install pip

ARG QWENPAW_VERSION=2.0.0.post2
# QwenPaw and AgentScope require MCP 1.x; FastMCP 4 requires MCP 2.
# Resolve the compatibility pins together to avoid backtracking through MCP 2 releases.
RUN pip install --no-cache-dir "qwenpaw==${QWENPAW_VERSION}" \
        "mcp==1.27.2" "fastmcp==3.4.2" "fastmcp-slim==3.4.2" \
        "agent-client-protocol==0.10.1" "anthropic==0.109.1" \
    && pip check
LABEL org.actbench.os="ubuntu22.04" org.actbench.runtime="qwenpaw" org.actbench.version="${QWENPAW_VERSION}"
WORKDIR /workspace
