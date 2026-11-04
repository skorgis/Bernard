# Parking guidance (Musterloesung) for the hackathon Raspberry Pi (arm64).
# Build context is the repository root: the solution depends on the main
# package (src/) through a path dependency on "../".
FROM ghcr.io/astral-sh/uv:0.12.4-python3.12-trixie-slim

# Bytecode at build time: faster start. Copy mode: the uv cache and the
# venv are on different filesystems, so hardlinks would fail anyway.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY Musterloesung ./Musterloesung

WORKDIR /app/Musterloesung
# --frozen: install exactly uv.lock, fail instead of re-resolving.
# Without the "pi" extra: the TFT drivers are only needed once a sign is
# installed ([display] enabled = true).
RUN uv sync --frozen --no-dev

ENV PATH="/app/Musterloesung/.venv/bin:$PATH"
RUN useradd --system --no-create-home parkleitsystem
USER parkleitsystem

ENTRYPOINT ["parkleitsystem"]
CMD ["--config", "/config/config.toml"]
