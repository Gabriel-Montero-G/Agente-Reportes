FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# /srv, not /app: the application package is itself named `app`, so mounting it
# at /app/app would be needlessly confusing.
WORKDIR /srv

# Requirements first so the pip layer is cached across code-only rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# `app` and `static` must stay siblings: app/server.py resolves STATIC_DIR as
# parent.parent / "static".
COPY app ./app
COPY static ./static

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# python, not curl — the slim image has no curl and it is not worth installing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/')"]

# Shell form so ${PORT} expands: PaaS providers inject it, local falls back to
# 8000. No --workers — sessions live in a per-process dict (app/session.py).
CMD uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000}
