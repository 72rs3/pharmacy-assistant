FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY app /app/app
COPY main.py /app/main.py

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python", "-c", "import os, urllib.request; port = os.getenv('PORT', '9000'); urllib.request.urlopen('http://127.0.0.1:' + port + '/healthz', timeout=3).read()"]

CMD ["bash", "-lc", "python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-9000}"]
