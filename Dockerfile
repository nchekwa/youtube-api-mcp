FROM python:3.14-alpine AS builder
WORKDIR /app
RUN apk add --no-cache gcc musl-dev linux-headers
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-alpine
WORKDIR /app
COPY --from=builder /install /usr/local
COPY ./app ./app
RUN mkdir -p /app/cache
EXPOSE 8000

# Use environment variables for host and port
# Default to 0.0.0.0:8000 if _APP_PORT is not set
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${_APP_PORT:-8000}"]
