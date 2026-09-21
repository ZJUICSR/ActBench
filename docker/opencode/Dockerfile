FROM node:22-bookworm-slim

# Match the reference repository's verified OpenCode version. Override explicitly
# when upgrading; each ActBench run records and executes the immutable image ID.
ARG OPENCODE_VERSION=1.17.18
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        bash ca-certificates curl git jq python3 ripgrep \
    && npm install --global "opencode-ai@${OPENCODE_VERSION}" \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

LABEL org.actbench.runtime="opencode" org.actbench.opencode.version="${OPENCODE_VERSION}"
ENV OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_MODELS_FETCH=1
RUN mkdir -p /workspace /home/agent
WORKDIR /workspace
