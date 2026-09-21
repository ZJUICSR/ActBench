FROM node:22-bookworm-slim
ARG OPENCLAW_VERSION=2026.5.18
ENV NODE_LLAMA_CPP_SKIP_DOWNLOAD=1
RUN apt-get update && apt-get install --no-install-recommends -y bash ca-certificates curl git jq python3 ripgrep \
    && npm install --global "openclaw@${OPENCLAW_VERSION}" \
    && npm cache clean --force && rm -rf /var/lib/apt/lists/*
LABEL org.actbench.runtime="openclaw" org.actbench.version="${OPENCLAW_VERSION}"
WORKDIR /workspace
