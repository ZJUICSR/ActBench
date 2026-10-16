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

ARG HERMES_REVISION=daedf4f627c73859974e587783b7cef8ce80e19a
RUN mkdir -p /opt/hermes \
    && curl --fail --location --retry 3 "https://codeload.github.com/NousResearch/hermes-agent/tar.gz/${HERMES_REVISION}" \
       | tar -xz --strip-components=1 -C /opt/hermes \
    && pip install --no-cache-dir '/opt/hermes[mcp]'
LABEL org.actbench.os="ubuntu22.04" org.actbench.runtime="hermes" org.actbench.revision="${HERMES_REVISION}"
WORKDIR /workspace
