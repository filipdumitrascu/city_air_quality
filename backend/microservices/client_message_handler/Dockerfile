FROM python:3.10-slim

WORKDIR /app

# Copy files
COPY microservices/client_message_handler /app
COPY common /app/common

# Create __init__.py for common module
RUN touch /app/common/__init__.py && \
    touch /app/common/authentification_service/__init__.py && \
    touch /app/common/message_queue_googlepubsub/__init__.py

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "client_message_handler:app", "--host", "0.0.0.0", "--port", "8000"]
