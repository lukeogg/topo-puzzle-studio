# Optional. Native `make dev` is the supported primary path.
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY packages/mesh /app/packages/mesh
COPY apps/api /app/apps/api
RUN uv pip install --system -e /app/packages/mesh && \
    uv pip install --system -e /app/apps/api

COPY . /app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
