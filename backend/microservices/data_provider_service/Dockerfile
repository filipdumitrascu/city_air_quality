FROM python:3.12-slim

WORKDIR /app

# Copy application files
COPY microservices/data_provider_service /app
COPY common /app/common
COPY microservices/database_service/client /app/database_service/client

# Create __init__.py files for Python module imports
RUN mkdir -p /app/database_service && \
    touch /app/database_service/__init__.py && \
    touch /app/database_service/client/__init__.py && \
    touch /app/common/__init__.py && \
    touch /app/common/authentification_service/__init__.py && \
    touch /app/common/message_queue_googlepubsub/__init__.py

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8001

CMD ["uvicorn", "data_provider_service:app", "--host", "0.0.0.0", "--port", "8001"]
