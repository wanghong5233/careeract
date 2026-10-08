FROM ghcr.io/steel-dev/steel-browser:latest@sha256:6dd29f73c33bb0f5bc9d950e8e4492c3f8458a06313346fa1767f68936a36fc8

COPY compat/package.json compat/package-lock.json /opt/compat/
RUN npm ci --prefix /opt/compat --ignore-scripts --no-audit --no-fund \
    && mv /app/node_modules/puppeteer-core /app/node_modules/puppeteer-core.original \
    && ln -s /opt/compat/node_modules/puppeteer-core /app/node_modules/puppeteer-core

COPY configure-runtime.cjs /opt/compat/configure-runtime.cjs
RUN node /opt/compat/configure-runtime.cjs

ENV CAREERACT_STEEL_RUNTIME_OBSERVATION=false
ENV REBROWSER_PATCHES_RUNTIME_FIX_MODE=alwaysIsolated
