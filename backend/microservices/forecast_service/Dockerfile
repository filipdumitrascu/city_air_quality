FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY microservices/forecast_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY microservices/forecast_service/forecast_service.py .
COPY microservices/forecast_service/polpred/ ./polpred/

# Copy pre-trained model
COPY microservices/forecast_service/model/polpred.pkl ./model/polpred.pkl

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "forecast_service:app", "--host", "0.0.0.0", "--port", "8000"]
 