FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements-runtime.lock .
RUN python -m pip install --no-cache-dir -r requirements-runtime.lock
COPY src ./src
USER 10001:10001
CMD ["python", "-m", "audience_ops.service", "console", "--config", "/console/console.json", "--host", "0.0.0.0", "--port", "8596"]
