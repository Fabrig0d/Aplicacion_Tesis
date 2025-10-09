import os
from typing import List

class Settings:
    # Base de datos
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "mysql+pymysql://root:1234fabri@localhost/inventario_db"
    )

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080", 
        "http://localhost:5353",
        "capacitor://localhost",
        "http://127.0.0.1:5500",
        "http://localhost"
    ]

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "app.log")

    # PLN/Chatbot
    PLN_MODEL_PATH: str = os.getenv("PLN_MODEL_PATH", "./pln_model")

    # App
    APP_NAME: str = "API Gestión de Inventarios"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

settings = Settings()