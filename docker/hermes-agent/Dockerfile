FROM python:3.12-slim

ARG HERMES_AGENT_REF=main
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HERMES_HOME=/opt/data \
    UV_PROJECT_ENVIRONMENT=/opt/hermes/.venv

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    git \
    jq \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /opt/hermes
COPY docker/hermes-agent/hermes-agent-src/ /opt/hermes/
RUN uv sync --frozen \
    && chmod +x /opt/hermes/docker/entrypoint.sh

ENV PATH="/opt/hermes/.venv/bin:${PATH}"
VOLUME ["/opt/data"]
EXPOSE 8642
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["gateway"]
