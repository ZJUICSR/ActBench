FROM python:3.12-slim-bookworm
ARG OPENAGENT_VERSION=2.83.1
ARG OPENAGENT_SHA256=75835584a6250eeb6904187c3d87ee3278aeddfc1f2dda3e67a2b2baed381961
RUN test "$(dpkg --print-architecture)" = amd64 \
    && apt-get update && apt-get install --no-install-recommends -y bash ca-certificates curl git jq ripgrep \
    && curl --fail --location --retry 3 "https://github.com/the-open-agent/openagent/releases/download/v${OPENAGENT_VERSION}/openagent_linux_x86" -o /usr/local/bin/openagent \
    && echo "${OPENAGENT_SHA256}  /usr/local/bin/openagent" | sha256sum -c - \
    && chmod 755 /usr/local/bin/openagent && rm -rf /var/lib/apt/lists/*
# The native service checks its listen port with lsof before starting.
RUN apt-get update && apt-get install --no-install-recommends -y lsof \
    && rm -rf /var/lib/apt/lists/*
LABEL org.actbench.runtime="openagent" org.actbench.version="${OPENAGENT_VERSION}"
WORKDIR /workspace
