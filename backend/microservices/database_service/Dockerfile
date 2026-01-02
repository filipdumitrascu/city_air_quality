FROM python:3.10-slim

WORKDIR /app

COPY microservices/database_service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/database_service/ .

EXPOSE 8000

CMD ["python", "database_service.py"]
