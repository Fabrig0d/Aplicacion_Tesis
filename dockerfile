# Usar Python 3.11
FROM python:3.11.8

# Crear y usar directorio de la app
WORKDIR /app

# Copiar requirements y luego instalar
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Copiar todo el proyecto
COPY . .

# Exponer puerto 8000 (el que usa uvicorn)
EXPOSE 8000

# Comando para iniciar FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]