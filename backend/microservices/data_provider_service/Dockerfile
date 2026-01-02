FROM python:3.10-slim
WORKDIR /app
COPY microservices/data_provider_service/requirements.txt .
COPY pubsub/requirements.txt pubsub_requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r pubsub_requirements.txt
COPY microservices/data_provider_service/ .
COPY microservices/database_service/client/ ./database_service/client/
COPY pubsub/ ./pubsub/
RUN mkdir -p database_service pubsub/message_queue_googlepubsub && \
    touch database_service/__init__.py && \
    touch database_service/client/__init__.py && \
    touch pubsub/__init__.py && \
    touch pubsub/message_queue_googlepubsub/__init__.py && \
    touch pubsub/authentification_service/__init__.py
EXPOSE 8001
CMD ["python", "data_provider_service.py"]
