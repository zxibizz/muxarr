# syntax=docker/dockerfile:1

FROM node:22-alpine AS web

WORKDIR /web
COPY web/package.json web/package-lock.json* ./
# `npm ci` needs a lockfile; fall back so a fresh clone still builds.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY web/ ./
RUN npm run build


FROM python:3.11-slim AS base

# mkvtoolnix is the only hard runtime dependency.
RUN apt-get update \
    && apt-get install -y --no-install-recommends mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md ./
COPY src ./src


FROM base AS runtime

# ffmpeg only adds an ffprobe fallback for containers mkvmerge cannot read -- but
# those cannot be muxed either, so it is off by default. Build with
# --build-arg INCLUDE_FFMPEG=true if you want `muxarr inspect` to handle them.
ARG INCLUDE_FFMPEG=false
RUN if [ "$INCLUDE_FFMPEG" = "true" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ffmpeg \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN pip install --no-cache-dir '.[server]'
COPY scripts ./scripts
COPY --from=web /web/dist ./web

EXPOSE 8710
ENV MUXARR_HOST=0.0.0.0 \
    MUXARR_PORT=8710 \
    MUXARR_DATA_DIR=/data \
    MUXARR_WEB_DIR=/app/web

# No USER directive on purpose: set `user: "1000:1000"` in compose to match the
# uid that owns your library, the same way the *arr images use PUID/PGID.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8710/healthz', timeout=3).status==200 else 1)"

CMD ["muxarr", "serve"]


FROM base AS test

# ffmpeg generates the test fixtures; curl exercises the shim.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -e '.[dev]'
COPY tests ./tests
COPY scripts ./scripts

CMD ["pytest", "-q", "-p", "no:warnings"]