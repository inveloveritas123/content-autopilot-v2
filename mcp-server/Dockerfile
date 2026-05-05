FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN groupadd -r app && useradd -r -g app -u 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app

USER app

EXPOSE 8080
CMD ["python", "server.py"]
