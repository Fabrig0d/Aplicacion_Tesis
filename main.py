from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import logging

# Imports locales
from database import SessionLocal, engine, Base
import models
import schemas  
import crud
from auth import authenticate_user, create_access_token, require_role

# Crear tablas al iniciar (fallback seguro)
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas/verificadas")
except Exception as e:
    print(f"⚠️  Error creando tablas: {e}")

# App
app = FastAPI(
    title="API Inventario - Demo Ligera",
    description="API REST ligera para inventarios con chatbot demo",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dependencia DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Modelos Pydantic
class ChatbotRequest(BaseModel):
    mensaje: str
    usuario_id: Optional[int] = None

class ChatbotResponse(BaseModel):
    exito: bool
    respuesta_chatbot: str
    confianza: Optional[float] = None
    timestamp: str

# ========== ENDPOINTS ==========

@app.get("/")
def root():
    return {
        "message": "API Inventario - Demo funcionando",
        "version": "1.0.0",
        "endpoints": ["/docs", "/health", "/login", "/chatbot/inventario", "/productos"]
    }

@app.get("/health")
def health_check():
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            logger.error(f"DB health check failed: {e}")
            db_status = "disconnected"
        finally:
            db.close()
        
        return {
            "status": "healthy" if db_status == "connected" else "degraded",
            "database": db_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/login")
def login_endpoint(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas"
        )
    
    access_token = create_access_token(data={"sub": user.correo})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/chatbot/inventario", response_model=ChatbotResponse)
def chatbot_endpoint(
    request: ChatbotRequest,
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """
    Chatbot demo - versión ligera sin PLN pesado
    """
    
    # Respuesta demo sin procesamiento pesado
    mensaje = request.mensaje.lower()
    
    if "agrega" in mensaje or "añade" in mensaje:
        respuesta = f"✅ Demo: Procesaría agregar productos según: '{request.mensaje}'"
    elif "elimina" in mensaje or "quita" in mensaje:
        respuesta = f"✅ Demo: Procesaría eliminar productos según: '{request.mensaje}'"
    elif "consulta" in mensaje or "stock" in mensaje:
        respuesta = f"✅ Demo: Consultaría stock según: '{request.mensaje}'"
    else:
        respuesta = f"✅ Demo: Mensaje recibido y procesado: '{request.mensaje}'"
    
    logger.info(f"Chatbot request from {current_user.correo}: {request.mensaje}")
    
    return ChatbotResponse(
        exito=True,
        respuesta_chatbot=respuesta,
        confianza=0.95,
        timestamp=datetime.now().isoformat()
    )

@app.get("/productos/")
def listar_productos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    try:
        return crud.get_productos(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo productos: {str(e)}")

# Endpoint temporal para crear usuario admin
@app.post("/crear-admin-demo")
def crear_admin_demo(db: Session = Depends(get_db)):
    """
    TEMPORAL: Crear usuario admin para demo
    """
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Verificar si ya existe
        existing = db.query(models.Usuario).filter(models.Usuario.correo == "admin@demo.com").first()
        if existing:
            return {"message": "Usuario demo ya existe", "correo": "admin@demo.com"}
        
        # Crear usuario demo
        admin_user = models.Usuario(
            nombre="Admin",
            apellido="Demo",
            correo="admin@demo.com",
            rol=models.RolEnum.administrador if hasattr(models, 'RolEnum') else "administrador",
            password_hash=pwd_context.hash("demo123")
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        return {
            "message": "Usuario demo creado",
            "correo": "admin@demo.com",
            "password": "demo123",
            "instrucciones": "Usa estas credenciales para login. Elimina este endpoint después."
        }
        
    except Exception as e:
        db.rollback()
        return {"error": f"Error creando usuario: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)