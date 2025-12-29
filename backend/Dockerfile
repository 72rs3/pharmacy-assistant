FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY app /app/app
COPY main.py /app/main.py

EXPOSE 9000

CMD ["bash", "-lc", "python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 9000"]

