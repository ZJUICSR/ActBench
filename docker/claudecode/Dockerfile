FROM node:22-bookworm-slim
ARG CLAUDECODE_VERSION=2.1.268
RUN apt-get update && apt-get install --no-install-recommends -y bash ca-certificates curl git jq python3 ripgrep \
    && npm install --global "@anthropic-ai/claude-code@${CLAUDECODE_VERSION}" \
    && npm cache clean --force && rm -rf /var/lib/apt/lists/*
LABEL org.actbench.runtime="claudecode" org.actbench.version="${CLAUDECODE_VERSION}"
ENV DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
WORKDIR /workspace
