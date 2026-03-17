FROM python:3.12-slim

WORKDIR /app

# Copy service files
COPY microservices/database_service /app

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "database_service:app", "--host", "0.0.0.0", "--port", "8000"]
