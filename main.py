from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import models, schemas, crud
from auth import authenticate_user, create_access_token, get_db
from database import SessionLocal, engine
from auth import require_role
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from datetime import datetime
import traceback

# Crear tablas
models.Base.metadata.create_all(bind=engine)

# Crear app
app = FastAPI(
    title="API Gestión de Inventarios",
    description="API REST para gestión de inventarios con chatbot PLN integrado",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Para pruebas - restringir en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
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
    orden_procesada: Optional[Dict[str, Any]] = None
    detalles_operacion: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    sugerencias: Optional[list] = None
    timestamp: str = None
    request_id: Optional[str] = None

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
def read_users_me(current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    return {
        "id": current_user.id_usuario,
        "correo": current_user.correo,
        "rol": current_user.rol
    }

# ========== CHATBOT PRINCIPAL ==========
@app.post("/chatbot/inventario", response_model=ChatbotResponse, tags=["Chatbot"])
def chatbot_inventario_endpoint(
    request: ChatbotRequest,
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """
    Endpoint principal del chatbot para procesar órdenes de inventario
    
    **Ejemplos de mensajes soportados:**
    - "agrega 50 mouse logitech G203" 
    - "elimina 10 teclados razer blackwidow"
    - "consulta stock de impresoras epson"
    - "ajusta monitor samsung a 25"
    - "genera reporte de laptops dell"
    """
    
    request_id = f"req_{int(datetime.now().timestamp())}"
    
    try:
        logger.info(f"Chatbot request [{request_id}]: '{request.mensaje}' - User: {current_user.correo}")
        
        # Procesar mensaje con chatbot
        try:
            from chatbot import procesar_mensaje_chatbot
            resultado = procesar_mensaje_chatbot(request.mensaje, current_user.id_usuario)
        except ImportError:
            # Fallback si no existe el módulo chatbot completo
            resultado = {
                'exito': True,
                'respuesta_chatbot': f"✅ Mensaje recibido: '{request.mensaje}'\n\n🤖 Chatbot en desarrollo. Conexión exitosa con backend.",
                'confianza': 1.0,
                'orden_procesada': {'mensaje': request.mensaje}
            }
        
        # Log resultado
        if resultado['exito']:
            logger.info(f"Chatbot success [{request_id}]: {resultado.get('detalles_operacion', {}).get('mensaje', 'Operación exitosa')}")
        else:
            logger.warning(f"Chatbot failed [{request_id}]: {resultado.get('error', 'Error desconocido')}")
        
        return ChatbotResponse(
            exito=resultado['exito'],
            respuesta_chatbot=resultado['respuesta_chatbot'],
            confianza=resultado.get('confianza'),
            orden_procesada=resultado.get('orden_procesada'),
            detalles_operacion=resultado.get('detalles_operacion'),
            error=resultado.get('error'),
            sugerencias=resultado.get('sugerencias'),
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )
        
    except Exception as e:
        logger.error(f"Chatbot error [{request_id}]: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return ChatbotResponse(
            exito=False,
            respuesta_chatbot="😵 Ocurrió un error inesperado. Por favor intenta de nuevo en un momento.",
            error=f"Error interno: {str(e)[:100]}",
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )

# ========== PRODUCTOS ==========
@app.get("/productos/", response_model=list[schemas.Producto])
def listar_productos(db: Session = Depends(get_db),
                    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    return crud.get_productos(db)

@app.get("/productos/{producto_id}", response_model=schemas.Producto)
def obtener_producto(producto_id: int, db: Session = Depends(get_db),
                    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    db_producto = crud.get_producto(db, producto_id)
    if not db_producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db_producto

# ========== HEALTH CHECK ==========
@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint de salud del sistema"""
    try:
        # Verificar conexión a BD
        db = SessionLocal()
        try:
            db.execute("SELECT 1")
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            db_status = "disconnected"
        finally:
            db.close()
        
        # Verificar PLN (opcional)
        pln_status = "healthy"
        try:
            import pln as pln_module
            test_result = pln_module.procesar_orden_inventario("test")
            if not test_result:
                pln_status = "error"
        except Exception as e:
            logger.error(f"PLN health check failed: {str(e)}")
            pln_status = "error"
        
        overall_status = "healthy" if db_status == "connected" else "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "services": {
                "database": db_status,
                "pln": pln_status,
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
    """Información general de la API"""
    return {
        "name": "API Gestión de Inventarios",
        "version": "1.0.0",
        "description": "API REST para gestión de inventarios con chatbot PLN integrado",
        "endpoints": {
            "authentication": "/login",
            "chatbot": "/chatbot/inventario",
            "health": "/health",
            "docs": "/docs"
        },
        "features": [
            "Autenticación JWT",
            "Chatbot PLN en español",
            "CRUD completo de inventarios",
            "Manejo automático de plurales y sinónimos",
            "Reportes automáticos"
        ]
    }
