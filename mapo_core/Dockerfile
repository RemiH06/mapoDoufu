FROM python:3.12-slim
WORKDIR /app

# rasterio trae su GDAL, pero enlaza contra libexpat del sistema.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY tests ./tests
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -e ".[dev]"

EXPOSE 8010
CMD ["uvicorn", "mapo_core.server:app", "--host", "0.0.0.0", "--port", "8010", "--reload"]