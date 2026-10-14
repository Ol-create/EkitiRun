FROM python:3.12-slim
# WeasyPrint needs Pango for PDF rendering.
RUN apt-get update && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /code
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
