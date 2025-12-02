# Dockerfile pentru client_message_handler
FROM python:3.10-slim

# Setează directorul de lucru
WORKDIR /app

# Copiază fișierele din common și client_message_handler
COPY microservices/database_service /app

# Instalează dependențele
RUN pip install --no-cache-dir -r /app/requirements.txt

# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

# Comandă pentru a porni aplicația
CMD ["uvicorn", "database_service:app", "--host", "0.0.0.0", "--port", "8003"]
