FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

# Instalar solo lo esencial
RUN pip install --no-cache-dir -r requirements.txt

# Instalar PyTorch CPU-only si necesitas PLN
# RUN pip install --no-cache-dir torch==2.1.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$PORT"]