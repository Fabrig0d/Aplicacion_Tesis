import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Obtener DATABASE_URL con fallback para evitar crash
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback para desarrollo/testing si no hay DATABASE_URL
if not DATABASE_URL:
    print("⚠️  DATABASE_URL no encontrada, usando SQLite fallback")
    DATABASE_URL = "sqlite:///./inventario_temp.db"
else:
    # Railway da mysql://, convertir a mysql+pymysql://
    if DATABASE_URL.startswith("mysql://"):
        DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

print(f"🔗 Conectando a: {DATABASE_URL}")

# Configurar engine según tipo de BD
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}  # Solo para SQLite
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=2,
        max_overflow=2
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()