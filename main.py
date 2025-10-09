from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from datetime import datetime
import traceback

# Módulos locales
import models, schemas, crud
from auth import authenticate_user, create_access_token, require_role
from database import SessionLocal, engine, Base

# Crear tablas al iniciar
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas/verificadas")
except Exception as e:
    print(f"⚠️ Error creando tablas: {e}")

# App
app = FastAPI(
    title="API Gestión de Inventarios",
    description="API REST para gestión de inventarios con chatbot PLN integrado",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (abrir en pruebas; restringir dominios en producción)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar a dominios específicos en prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dependencia de DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Schemas Pydantic
class ChatbotRequest(BaseModel):
    mensaje: str
    usuario_id: Optional[int] = None

class ChatbotResponse(BaseModel):
    exito: bool
    respuesta_chatbot: str
    confianza: Optional[float] = None
    orden_procesada: Optional[Dict[str, Any]] = None
    detalles_operacion: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    sugerencias: Optional[list] = None
    timestamp: str
    request_id: Optional[str] = None

# Root
@app.get("/")
def root():
    return {
        "message": "API Inventario activa",
        "version": "1.0.0",
        "endpoints": ["/docs", "/health", "/login", "/chatbot/inventario", "/productos"]
    }

# ========== AUTENTICACIÓN ==========
@app.post("/login")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.correo})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/usuarios/me")
def read_users_me(
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return {
        "id": current_user.id_usuario,
        "correo": current_user.correo,
        "rol": getattr(current_user.rol, "value", current_user.rol),
    }

# ========== CHATBOT ==========
@app.post("/chatbot/inventario", response_model=ChatbotResponse, tags=["Chatbot"])
def chatbot_inventario_endpoint(
    request: ChatbotRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """
    Procesa órdenes de inventario en lenguaje natural y
    ejecuta operaciones en la BD a través de 'chatbot.procesar_mensaje_chatbot'.
    """
    request_id = f"req_{int(datetime.now().timestamp())}"
    logger.info(f"[{request_id}] Chatbot: '{request.mensaje}' - User: {current_user.correo}")

    try:
        # Import diferido para evitar problemas de cold start y ciclos
        from chatbot import procesar_mensaje_chatbot

        resultado = procesar_mensaje_chatbot(
            request.mensaje,
            current_user.id_usuario,
            db=db  # pasa la sesión si la función la admite
        )

        if not isinstance(resultado, dict):
            raise ValueError("El chatbot debe retornar un dict estructurado")

        exito = bool(resultado.get('exito', False))
        resp = ChatbotResponse(
            exito=exito,
            respuesta_chatbot=resultado.get('respuesta_chatbot', 'Sin respuesta'),
            confianza=resultado.get('confianza'),
            orden_procesada=resultado.get('orden_procesada'),
            detalles_operacion=resultado.get('detalles_operacion'),
            error=resultado.get('error'),
            sugerencias=resultado.get('sugerencias'),
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )

        if exito:
            logger.info(f"[{request_id}] Éxito: {resultado.get('detalles_operacion', {}).get('mensaje', '')}")
        else:
            logger.warning(f"[{request_id}] Error de negocio: {resultado.get('error', '')}")

        return resp

    except Exception as e:
        logger.error(f"[{request_id}] Error inesperado: {e}")
        logger.error(traceback.format_exc())
        return ChatbotResponse(
            exito=False,
            respuesta_chatbot="😵 Ocurrió un error inesperado al procesar la orden.",
            error=str(e)[:200],
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )

# ========== PRODUCTOS ==========
@app.get("/productos/", response_model=list[schemas.Producto])
def listar_productos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return crud.get_productos(db)

@app.get("/productos/{producto_id}", response_model=schemas.Producto)
def obtener_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    db_producto = crud.get_producto(db, producto_id)
    if not db_producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db_producto

# ========== HEALTH ==========
@app.get("/health", tags=["Health"])
def health_check():
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            db_status = "disconnected"
        finally:
            db.close()

        return {
            "status": "healthy" if db_status == "connected" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": db_status,
                "chatbot": "healthy"
            },
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )

# ========== INFO ==========
@app.get("/info", tags=["Info"])
def app_info():
    return {
        "name": "API Gestión de Inventarios",
        "version": "1.0.0",
        "description": "API REST para gestión de inventarios con chatbot PLN integrado",
        "endpoints": {
            "authentication": "/login",
            "chatbot": "/chatbot/inventario",
            "health": "/health",
            "docs": "/docs"
        }
    }

# Opcional: endpoint temporal para crear admin demo
@app.post("/crear-admin-demo")
def crear_admin_demo(db: Session = Depends(get_db)):
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        existing = db.query(models.Usuario).filter(models.Usuario.correo == "admin@demo.com").first()
        if existing:
            return {"message": "Usuario demo ya existe", "correo": "admin@demo.com"}

        admin_user = models.Usuario(
            nombre="Admin",
            apellido="Demo",
            correo="admin@demo.com",
            rol=getattr(models, "RolEnum", None).administrador if hasattr(models, 'RolEnum') else "administrador",
            password_hash=pwd_context.hash("demo123")
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        return {"message": "Usuario demo creado", "correo": "admin@demo.com", "password": "demo123"}
    except Exception as e:
        db.rollback()
        return {"error": f"Error creando usuario: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)