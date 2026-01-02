# Dockerfile pentru routing_service
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy routing service files
COPY microservices/routing_service /app

# Instalează dependențele
RUN pip install --no-cache-dir -r /app/requirements.txt

# Expose port
EXPOSE 8000

# Run service
CMD ["uvicorn", "src.routing_service:app", "--host", "0.0.0.0", "--port", "8000"]
