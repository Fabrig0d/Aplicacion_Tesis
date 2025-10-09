import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Para Railway - usar variable de entorno
DATABASE_URL = os.getenv("mysql://root:ZInBLnXUJiRrpobCXBMGSQvYLWMBlmnw@shinkansen.proxy.rlwy.net:44660/railway")

# Railway da mysql://, pero SQLAlchemy necesita mysql+pymysql://
if DATABASE_URL and DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_size=2,
    max_overflow=2
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()