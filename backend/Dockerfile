FROM python:3.13-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir uv
RUN uv sync

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]