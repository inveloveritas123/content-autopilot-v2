FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "-m", "mcp", "run", "server.py", "--transport", "sse", "--host", "0.0.0.0", "--port", "8080"]
