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

ARG OPENAGENT_VERSION=2.83.1
ARG OPENAGENT_SHA256=75835584a6250eeb6904187c3d87ee3278aeddfc1f2dda3e67a2b2baed381961
RUN test "$(dpkg --print-architecture)" = amd64 \
    && curl --fail --location --retry 3 "https://github.com/the-open-agent/openagent/releases/download/v${OPENAGENT_VERSION}/openagent_linux_x86" -o /usr/local/bin/openagent \
    && echo "${OPENAGENT_SHA256}  /usr/local/bin/openagent" | sha256sum -c - \
    && chmod 755 /usr/local/bin/openagent
LABEL org.actbench.os="ubuntu22.04" org.actbench.runtime="openagent" org.actbench.version="${OPENAGENT_VERSION}"
WORKDIR /workspace
