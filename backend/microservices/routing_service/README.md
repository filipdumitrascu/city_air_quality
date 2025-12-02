# Routing Service

Serviciu pentru calcularea rutelor optime bazate pe poluare.

## Setup Local
```bash
# Create venv
python3 -m venv venv
source venv/bin/activate

# Install
pip install -r requirements.txt

# Run
uvicorn src.main:app --reload --port 8000
```

## Docker
```bash
# Build
docker build -t routing-service .

# Run
docker run -p 8000:8000 routing-service
```

## API

- `POST /route/optimal` - Găsește ruta optimă
- `GET /health` - Health check
