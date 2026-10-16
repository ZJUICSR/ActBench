FROM ubuntu:22.04

RUN apt-get update && apt-get install --no-install-recommends -y \
        bash ca-certificates curl git jq python3 ripgrep xz-utils \
        libstdc++6 libgomp1 libportaudio2 lsof \
    && rm -rf /var/lib/apt/lists/*

ARG NODE_VERSION=22.23.2
RUN set -eu; \
    case "$(dpkg --print-architecture)" in amd64) arch=x64 ;; arm64) arch=arm64 ;; *) exit 1 ;; esac; \
    archive="node-v${NODE_VERSION}-linux-${arch}.tar.xz"; \
    cd /tmp; \
    curl --fail --location --retry 3 "https://nodejs.org/dist/v${NODE_VERSION}/${archive}" -o "$archive"; \
    curl --fail --location --retry 3 "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" -o SHASUMS256.txt; \
    grep "  ${archive}$" SHASUMS256.txt | sha256sum --check --strict -; \
    tar -xJf "$archive" --strip-components=1 -C /usr/local; \
    rm "$archive" SHASUMS256.txt; \
    node --version; npm --version

ARG CLAUDECODE_VERSION=2.1.218
RUN npm install --global "@anthropic-ai/claude-code@${CLAUDECODE_VERSION}" \
    && npm cache clean --force
LABEL org.actbench.os="ubuntu22.04" org.actbench.runtime="claudecode" org.actbench.version="${CLAUDECODE_VERSION}"
ENV DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
WORKDIR /workspace
