import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Obtener DATABASE_URL de variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Validar que existe la variable
if not DATABASE_URL:
    logger.error("❌ DATABASE_URL no encontrada en variables de entorno")
    DATABASE_URL = "sqlite:///./fallback.db"
    logger.warning("⚠️ Usando SQLite fallback - configura DATABASE_URL")
else:
    logger.info(f"🔗 DATABASE_URL encontrada: {DATABASE_URL[:50]}...")

# Clever Cloud suele dar URLs en formato mysql://
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)
    logger.info("🔄 Convertido mysql:// -> mysql+pymysql://")

# Configurar engine con pool MUY restrictivo para Clever Cloud
try:
    if "sqlite" in DATABASE_URL:
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_size=1,          # 1 conexión fija
            max_overflow=0,       # NO overflow; máximo 1 total
            pool_pre_ping=True,
            pool_recycle=900,     # 15 min
            pool_timeout=20,      # espera menor
            connect_args={
                "charset": "utf8mb4",
                "connect_timeout": 8,
                "read_timeout": 20,
                "write_timeout": 20,
                "autocommit": False,
            },
            echo=False
        )
        logger.info(f"✅ Engine creado - Pool size: 1, Max overflow: 0")
    
except Exception as e:
    logger.error(f"❌ Error creando engine: {e}")
    raise

# Crear sessionmaker con scoped_session para thread safety
SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
)

# Base para modelos
Base = declarative_base()

# Context manager para sesiones seguras
@contextmanager
def get_db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Error in database session: {e}")
        raise
    finally:
        try:
            session.close()
        finally:
            SessionLocal.remove()  # fuerza liberar el thread-local

# Funciones helper
def test_connection():
    """Prueba la conexión a la base de datos"""
    try:
        with get_db_session() as session:
            result = session.execute(text("SELECT 1 as test"))
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

def get_db_info():
    """Obtiene información de la base de datos conectada"""
    try:
        with get_db_session() as session:
            if "sqlite" in str(engine.url):
                db_type = "SQLite"
                version_query = "SELECT sqlite_version() as version"
            else:
                db_type = "MySQL"
                version_query = "SELECT VERSION() as version"
            
            version_result = session.execute(text(version_query))
            version = version_result.scalar()
            
            return {
                "type": db_type,
                "version": version,
                "url": str(engine.url).replace(str(engine.url).split('@')[0].split('://')[1], "***") if '@' in str(engine.url) else str(engine.url),
                "pool_size": engine.pool.size(),
                "checked_out": engine.pool.checkedout(),
                "overflow": engine.pool.overflow(),
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

# Función legacy para compatibilidad (NO USAR en nuevos endpoints)
def get_db():
    """LEGACY: Solo para compatibilidad. Usar get_db_session() en nuevos endpoints"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        SessionLocal.remove()