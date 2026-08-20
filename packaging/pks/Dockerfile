# syntax=docker/dockerfile:1
# PKS / 银河麒麟 V10 SP1 基线：Ubuntu 20.04 (glibc 2.31) + WebKitGTK 4.0
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/root/.cargo/bin:/usr/local/bin:$PATH \
    HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy= NO_PROXY=* no_proxy=*

RUN apt-get update \
    && for attempt in 1 2 3 4 5; do \
         apt-get install -y --no-install-recommends --fix-missing -o Acquire::Retries=5 \
           ca-certificates curl xz-utils gnupg \
           build-essential pkg-config \
           libwebkit2gtk-4.0-dev librsvg2-dev patchelf \
           libssl-dev libgtk-3-dev libappindicator3-dev \
           libsoup2.4-dev \
         && break; \
         echo "apt attempt ${attempt} failed; retrying..." >&2; \
         apt-get update; \
         sleep 15; \
       done \
    && rm -rf /var/lib/apt/lists/*

# Standalone CPython 3.11 (arm64) — deadsnakes no longer publishes 3.11 for focal.
ARG PYTHON_STANDALONE=cpython-3.11.12+20250409-aarch64-unknown-linux-gnu-install_only.tar.gz
RUN curl -fsSL "https://github.com/astral-sh/python-build-standalone/releases/download/20250409/${PYTHON_STANDALONE}" \
    | tar -xz -C /opt \
    && ln -sfn /opt/python /install \
    && ln -sf /opt/python/bin/python3.11 /usr/local/bin/python3.11 \
    && ln -sf /opt/python/bin/python3.11 /usr/local/bin/python3 \
    && /usr/local/bin/python3.11 -c "import encodings; print('python ok')"

ARG NODE_VERSION=20.18.1
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1 \
    && node --version && npm --version

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
    && rustup target add aarch64-unknown-linux-gnu

WORKDIR /src
