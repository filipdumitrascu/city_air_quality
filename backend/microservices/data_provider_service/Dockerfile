FROM python:3.10-slim

WORKDIR /app

# Copy files
COPY microservices/data_provider_service /app
COPY pubsub /app/pubsub
COPY microservices/database_service/client /app/database_service/client

# Create __init__.py files
RUN mkdir -p /app/database_service && \
    touch /app/database_service/__init__.py && \
    touch /app/database_service/client/__init__.py && \
    touch /app/pubsub/__init__.py && \
    touch /app/pubsub/authentification_service/__init__.py && \
    touch /app/pubsub/message_queue_googlepubsub/__init__.py

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8001

CMD ["uvicorn", "data_provider_service:app", "--host", "0.0.0.0", "--port", "8001"]
