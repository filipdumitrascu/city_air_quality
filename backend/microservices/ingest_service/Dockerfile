# Dockerfile pentru client_message_handler
FROM python:3.10-slim

# Setează directorul de lucru
WORKDIR /app

# Copiază fișierele din common și client_message_handler
COPY microservices/ingest_service /app
COPY common /app/common
COPY microservices/database_service/client /app/database_service/client

# Instalează dependențele
RUN pip install --no-cache-dir -r /app/requirements.txt

ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

# Comandă pentru a porni aplicația
CMD ["uvicorn", "ingest_service:app", "--host", "0.0.0.0", "--port", "8002"]
