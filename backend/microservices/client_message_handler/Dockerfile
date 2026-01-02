FROM python:3.10-slim

WORKDIR /app

# Copy files
COPY microservices/client_message_handler /app
COPY pubsub /app/pubsub

# Create __init__.py for pubsub module
RUN touch /app/pubsub/__init__.py && \
    touch /app/pubsub/authentification_service/__init__.py && \
    touch /app/pubsub/message_queue_googlepubsub/__init__.py

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "client_message_handler:app", "--host", "0.0.0.0", "--port", "8000"]
