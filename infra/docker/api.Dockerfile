FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.5
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY apps/__init__.py apps/__init__.py
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY dev_support dev_support
COPY worker worker
COPY scripts scripts
COPY evals evals
COPY infra/migrations infra/migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
