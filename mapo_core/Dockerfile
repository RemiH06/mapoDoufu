FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8010
CMD ["uvicorn", "mapo_core.server:app", "--host", "0.0.0.0", "--port", "8010", "--reload"]