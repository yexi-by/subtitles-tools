FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md setting.toml ./
COPY subtitles_tools ./subtitles_tools
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

EXPOSE 8055

CMD ["uv", "run", "subtitles-tools"]
