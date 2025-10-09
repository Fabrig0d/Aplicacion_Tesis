import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

logger = logging.getLogger(__name__)

# Obtener DATABASE_URL de variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Validar que existe la variable
if not DATABASE_URL:
    logger.error("❌ DATABASE_URL no encontrada en variables de entorno")
    # Fallback temporal para desarrollo (cambiar por tu URL real)
    DATABASE_URL = "sqlite:///./fallback.db"
    logger.warning("⚠️ Usando SQLite fallback - configura DATABASE_URL")
else:
    logger.info(f"🔗 DATABASE_URL encontrada: {DATABASE_URL[:50]}...")

# Clever Cloud suele dar URLs en formato mysql://
# Convertir a mysql+pymysql:// para SQLAlchemy
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)
    logger.info("🔄 Convertido mysql:// -> mysql+pymysql://")

# Configurar engine con parámetros optimizados para cloud
try:
    if "sqlite" in DATABASE_URL:
        # Configuración para SQLite fallback
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False  # Cambiar a True para ver queries SQL
        )
    else:
        # Configuración para MySQL en Clever Cloud
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,          # Verifica conexiones antes de usar
            pool_recycle=3600,           # Recicla conexiones cada hora
            pool_size=5,                 # Pool pequeño para servicios gratuitos
            max_overflow=10,             # Máximo 15 conexiones totales
            connect_args={
                "charset": "utf8mb4",    # Soporte completo UTF-8
                "connect_timeout": 10,   # Timeout de conexión
                "read_timeout": 30,      # Timeout de lectura
                "write_timeout": 30,     # Timeout de escritura
            },
            echo=False  # Cambiar a True para debug SQL
        )
    
    logger.info("✅ Engine de SQLAlchemy creado exitosamente")
    
except Exception as e:
    logger.error(f"❌ Error creando engine: {e}")
    raise

# Crear sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos
Base = declarative_base()

# Función para probar la conexión
def test_connection():
    """Prueba la conexión a la base de datos"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            if test_value == 1:
                logger.info("✅ Conexión a BD exitosa")
                return True
            else:
                logger.error("❌ Conexión falló - resultado inesperado")
                return False
    except Exception as e:
        logger.error(f"❌ Error de conexión: {e}")
        return False

# Función helper para obtener info de la BD
def get_db_info():
    """Obtiene información de la base de datos conectada"""
    try:
        with engine.connect() as connection:
            # Detectar tipo de BD
            if "sqlite" in str(engine.url):
                db_type = "SQLite"
                version_query = "SELECT sqlite_version() as version"
            else:
                db_type = "MySQL"
                version_query = "SELECT VERSION() as version"
            
            version_result = connection.execute(text(version_query))
            version = version_result.scalar()
            
            return {
                "type": db_type,
                "version": version,
                "url": str(engine.url).replace(str(engine.url).split('@')[0].split('://')[1], "***") if '@' in str(engine.url) else str(engine.url),
                "pool_size": engine.pool.size(),
                "status": "connected"
            }
    except Exception as e:
        return {
            "type": "unknown",
            "version": "unknown", 
            "url": "error",
            "error": str(e),
            "status": "error"
        }

# Probar conexión al importar (opcional)
if __name__ == "__main__":
    print("🧪 Probando conexión a BD...")
    success = test_connection()
    if success:
        info = get_db_info()
        print(f"📊 BD Info: {info}")
    else:
        print("💥 Falló la conexión")