FROM python:3.12-slim
# WeasyPrint needs Pango for PDF rendering, and a font with the Naira sign (DejaVu).
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /code
# Install exactly the versions pinned in uv.lock, into the system Python
# (not /code/.venv, which is hidden by the dev volume mount).
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt
COPY . .
# Don't run as root.
RUN useradd --create-home --uid 10001 app && chown -R app /code
USER app
# --proxy-headers: behind the host's load balancer, see the real client IP (rate limits).
# WEB_CONCURRENCY: API processes per container (each keeps its own pub/sub fan-out).
# PORT: set by the host (Render); 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --workers ${WEB_CONCURRENCY:-1}"]
