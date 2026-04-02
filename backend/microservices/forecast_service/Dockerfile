FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY forecast_service.py .
COPY polpred/ ./polpred/

# Create model directory (model will be mounted or copied separately)
RUN mkdir -p /app/model

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "forecast_service:app", "--host", "0.0.0.0", "--port", "8000"]
