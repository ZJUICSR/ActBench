FROM python:3.12-slim-bookworm
ARG QWENPAW_VERSION=1.1.11.post2
RUN apt-get update && apt-get install --no-install-recommends -y bash ca-certificates curl git jq ripgrep libgomp1 libportaudio2 \
    && pip install --no-cache-dir "qwenpaw==${QWENPAW_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
# AgentScope 1.0.20 imports MCP 1.x's streamablehttp_client alias. Upstream
# dependencies have no compatible upper bound; MCP 2/FastMCP 4 break startup.
# Keep this compatibility layer separate from the large native installation.
RUN pip install --no-cache-dir "mcp==1.27.2" "fastmcp==3.4.2" "fastmcp-slim==3.4.2" \
        "agent-client-protocol==0.10.1" "anthropic==0.109.1" \
    && pip check
LABEL org.actbench.runtime="qwenpaw" org.actbench.version="${QWENPAW_VERSION}"
WORKDIR /workspace
