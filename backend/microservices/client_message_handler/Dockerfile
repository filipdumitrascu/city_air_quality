# Dockerfile pentru client_message_handler
FROM python:3.10-slim

# Setează directorul de lucru
WORKDIR /app

# Copiază fișierele din common și client_message_handler
COPY microservices/client_message_handler /app
COPY common /app/common
COPY credentials.json /app/credentials.json

# Instalează dependențele
RUN pip install --no-cache-dir -r /app/requirements.txt

# Setează variabila de mediu
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json

# Comandă pentru a porni aplicația
CMD ["uvicorn", "client_message_handler:app", "--host", "0.0.0.0", "--port", "8000"]
