FROM python:3.12-slim-bookworm
ARG HERMES_REVISION=daedf4f627c73859974e587783b7cef8ce80e19a
RUN apt-get update && apt-get install --no-install-recommends -y bash ca-certificates curl git jq ripgrep \
    && mkdir -p /opt/hermes \
    && curl --fail --location --retry 3 "https://github.com/NousResearch/hermes-agent/archive/${HERMES_REVISION}.tar.gz" \
       | tar -xz --strip-components=1 -C /opt/hermes \
    && pip install --no-cache-dir '/opt/hermes[mcp]' \
    && rm -rf /var/lib/apt/lists/*
LABEL org.actbench.runtime="hermes" org.actbench.revision="${HERMES_REVISION}"
WORKDIR /workspace
