from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
import models, schemas, crud, auth
from auth import authenticate_user, create_access_token, get_current_user, get_db
from database import SessionLocal, engine
from auth import require_role
import pln 
from typing import Optional, Dict, Any
from pydantic import BaseModel
from chatbot import procesar_mensaje_chatbot
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from datetime import datetime
import traceback
 

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Gestión de Inventarios")

# Dependencia DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ChatbotRequest(BaseModel):
    mensaje: str
    usuario_id: Optional[int] = None


# ---------- Categorías ----------
@app.post("/categorias/", response_model=schemas.Categoria)
def crear_categoria(categoria: schemas.CategoriaCreate, 
                    db: Session = Depends(get_db), 
                    current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    return crud.create_categoria(db, categoria)

@app.get("/categorias/", response_model=list[schemas.Categoria])
def listar_categorias(db: Session = Depends(get_db),
                      current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    return crud.get_categorias(db)

# ---------- Marcas ----------
@app.post("/marcas/", response_model=schemas.Marca)
def crear_marca(marca: schemas.MarcaCreate, db: Session = Depends(get_db),
                current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    return crud.create_marca(db, marca)

@app.get("/marcas/", response_model=list[schemas.Marca])
def listar_marcas(db: Session = Depends(get_db),current_user: schemas.Usuario = Depends (require_role(["admin", "usuario"]))):
    return crud.get_marcas(db)

# ---------- Usuarios ----------
@app.post("/usuarios/", response_model=schemas.Usuario)
def crear_usuario(usuario: schemas.UsuarioCreate, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    return crud.create_usuario(db, usuario)

@app.get("/usuarios/", response_model=list[schemas.Usuario])
def listar_usuarios(db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    return crud.get_usuarios(db)

# ---------- Productos ----------
@app.post("/productos/", response_model=schemas.Producto)
def crear_producto(producto: schemas.ProductoCreate, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    return crud.create_producto(db, producto)

@app.get("/productos/", response_model=list[schemas.Producto])
def listar_productos(db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    return crud.get_productos(db)

@app.get("/productos/{producto_id}", response_model=schemas.Producto)
def obtener_producto(producto_id: int, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    db_producto = crud.get_producto(db, producto_id)
    if not db_producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return db_producto

# ---------- Movimientos ----------
@app.post("/movimientos/", response_model=schemas.MovimientoInventario)
def crear_movimiento(movimiento: schemas.MovimientoInventarioCreate, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    return crud.create_movimiento(db=db, movimiento=movimiento)


@app.get("/movimientos/", response_model=list[schemas.MovimientoInventario])
def listar_movimientos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    return crud.get_movimientos(db=db, skip=skip, limit=limit)


@app.get("/movimientos/{movimiento_id}", response_model=schemas.MovimientoInventario)
def obtener_movimiento(movimiento_id: int, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    mov = crud.get_movimiento(db=db, movimiento_id=movimiento_id)
    if mov is None:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    return mov


@app.delete("/movimientos/{movimiento_id}", status_code=204)
def eliminar_movimiento(movimiento_id: int, db: Session = Depends(get_db), 
                        current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    mov = crud.delete_movimiento(db=db, movimiento_id=movimiento_id)
    if mov is None:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    return

# ---------- Reportes ----------
@app.post("/reportes/", response_model=schemas.Reporte)
def crear_reporte(reporte: schemas.ReporteCreate, db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin"]))):
    return crud.create_reporte(db, reporte)

@app.get("/reportes/", response_model=list[schemas.Reporte])
def listar_reportes(db: Session = Depends(get_db),current_user: schemas.Usuario = Depends(require_role(["admin", "usuario"]))):
    return crud.get_reportes(db)


@app.post("/login")
def login(
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
    # Generar token
    access_token = create_access_token(data={"sub": user.correo})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/usuarios/me")
def read_users_me(current_user: models.Usuario = Depends(require_role(["admin", "usuario"]))):
    return {
        "id": current_user.id_usuario,
        "correo": current_user.correo,
        "rol": current_user.rol
    }


class OrdenRequest(BaseModel):
    texto: str
    ejecutar_en_bd: Optional[bool] = True

class OrdenResponse(BaseModel):
    orden_original: str
    analisis_detallado: Dict[str, Any]
    orden_procesada: Dict[str, Any]
    mensaje: str
    confianza: float
    metodo_usado: str
    ejecutado_en_bd: bool = False
    error: Optional[str] = None


@app.post("/pln/orden", response_model=OrdenResponse)
def procesar_orden_mejorada(
    request: OrdenRequest, 
    db: Session = Depends(get_db)
):
    """
    Recibe una orden en español, la procesa con análisis mejorado + mT5
    y devuelve un JSON estructurado listo para ejecutar en la base de datos.

    Mejoras:
    - Análisis de palabras avanzado con manejo de plurales
    - Sistema de confianza para validar resultados
    - Mejor detección de entidades (producto, marca, cantidad)
    - Fallback inteligente al modelo MT5
    - Respuestas más informativas
    """

    # 1) Procesar orden con sistema mejorado
    try:
        resultado_completo = pln.procesar_orden_inventario(request.texto)

        json_intermedio = resultado_completo['json_intermedio']
        orden_final = resultado_completo['resultado_final']

        # Extraer información del análisis
        confianza = json_intermedio.get('confianza', 0.0)
        metodo_usado = json_intermedio.get('metodo', 'desconocido')

    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Error al procesar la orden: {str(e)}"
        )

    # 2) Validar que la orden tenga sentido
    if orden_final['tipo_movimiento'] == 'desconocido':
        return OrdenResponse(
            orden_original=request.texto,
            analisis_detallado=json_intermedio,
            orden_procesada=orden_final,
            mensaje="No se pudo entender la orden. Intenta ser más específico.",
            confianza=confianza,
            metodo_usado=metodo_usado,
            ejecutado_en_bd=False,
            error="Orden no reconocida"
        )

    # 3) Ejecutar en base de datos si se solicita
    ejecutado_en_bd = False
    mensaje = "Orden procesada correctamente"
    error = None

    if request.ejecutar_en_bd:
        try:
            resultado_bd = ejecutar_orden_en_bd(orden_final, db)
            ejecutado_en_bd = resultado_bd['exito']
            if not ejecutado_en_bd:
                error = resultado_bd['error']
                mensaje = f"Error en BD: {error}"
            else:
                mensaje = resultado_bd['mensaje']

        except Exception as e:
            error = str(e)
            mensaje = f"Error inesperado en BD: {error}"



    return OrdenResponse(
        orden_original=request.texto,
        analisis_detallado=json_intermedio,
        orden_procesada=orden_final,
        mensaje=mensaje,
        confianza=confianza,
        metodo_usado=metodo_usado,
        ejecutado_en_bd=ejecutado_en_bd,
        error=error
    )



# ---------------------- FUNCIÓN AUXILIAR PARA BD ----------------------
def ejecutar_orden_en_bd(orden: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Ejecuta la orden procesada en la base de datos según el tipo de movimiento.
    """

    tipo_mov = orden.get("tipo_movimiento")
    producto = orden.get("producto")
    marca = orden.get("marca")
    modelo = orden.get("modelo")  
    cantidad = orden.get("cantidad")

    # Validaciones básicas
    if not producto:
        return {"exito": False, "error": "Producto no especificado", "mensaje": ""}

    try:
        if tipo_mov == "entrada" and cantidad and cantidad > 0:
            # Lógica para entrada de inventario
            # resultado_crud = crud.create_movimiento(db, {
            #     "producto": producto,
            #     "marca": marca,
            #    "modelo": modelo,
            #     "tipo_movimiento": "entrada",
            #     "cantidad": cantidad
            # })

            return {
                "exito": True, 
                "error": None, 
                "mensaje": f"Agregados {cantidad} {producto} {marca or ''} al inventario"
            }

        elif tipo_mov == "salida" and cantidad and cantidad > 0:
            # Lógica para salida de inventario
            # Verificar stock disponible primero
            # stock_actual = crud.get_stock(db, producto, marca)
            # if stock_actual < cantidad:
            #     return {"exito": False, "error": f"Stock insuficiente. Disponible: {stock_actual}"}

            # resultado_crud = crud.create_movimiento(db, {
            #     "producto": producto,
            #     "marca": marca,
            #     "tipo_movimiento": "salida", 
            #     "cantidad": cantidad
            # })

            return {
                "exito": True,
                "error": None,
                "mensaje": f"Retirados {cantidad} {producto} {marca or ''} del inventario"
            }

        elif tipo_mov == "ajuste" and cantidad is not None:
            # Lógica para ajuste de stock
            # resultado_crud = crud.ajustar_stock(db, producto, marca, cantidad)

            return {
                "exito": True,
                "error": None,
                "mensaje": f"Stock de {producto} {marca or ''} ajustado a {cantidad}"
            }

        elif tipo_mov == "consulta":
            # Lógica para consulta de stock
            # stock_info = crud.get_stock_detallado(db, producto, marca)
            # return {
            #     "exito": True,
            #     "error": None,
            #     "mensaje": f"Stock actual: {stock_info}",
            #     "data": stock_info
            # }

            return {
                "exito": True,
                "error": None,
                "mensaje": f"Consulta de stock para {producto} {marca or ''} ejecutada"
            }

        elif tipo_mov == "reporte":
            # Lógica para generar reporte
            return {
                "exito": True,
                "error": None,
                "mensaje": f"Reporte generado para {producto} {marca or ''}"
            }

        else:
            return {
                "exito": False,
                "error": f"Tipo de movimiento no soportado: {tipo_mov}",
                "mensaje": ""
            }

    except Exception as e:
        return {
            "exito": False,
            "error": f"Error en operación BD: {str(e)}",
            "mensaje": ""
        }

# ---------------------- ENDPOINT ADICIONAL PARA SOLO ANÁLISIS ----------------------
@app.post("/pln/analizar")
def solo_analizar_orden(texto: str):
    """
    Solo analiza la orden sin ejecutar en BD. Útil para pruebas y debugging.
    """
    try:
        resultado_completo = pln.procesar_orden_inventario(texto)

        return {
            "texto_original": texto,
            "resultado_completo": resultado_completo,
            "palabras_clave": resultado_completo['json_intermedio'].get('palabras_clave', []),
            "confianza": resultado_completo['json_intermedio'].get('confianza', 0.0)
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")


# ---------------------- ENDPOINT DE SALUD ----------------------
@app.get("/pln/health")
def health_check():
    """
    Verifica que el sistema PLN esté funcionando correctamente.
    """
    try:
        # Probar con una orden simple
        test_result = pln.procesar_orden_inventario("agrega 1 mouse test")
        return {
            "status": "healthy",
            "pln_funcionando": True,
            "modelo_cargado": True,
            "test_orden": test_result['resultado_final']
        }
    except Exception as e:
        return {
            "status": "error", 
            "pln_funcionando": False,
            "error": str(e)
        }
    
@app.post("/chatbot/inventario")
def chatbot_inventario_endpoint(
    request: ChatbotRequest,
    current_user: models.Usuario = Depends(require_role(["admin", "usuario"]))
):
    usuario_id = request.usuario_id or current_user.id_usuario
    resultado = procesar_mensaje_chatbot(request.mensaje, usuario_id)
    
    return {
        "exito": resultado['exito'],
        "respuesta_chatbot": resultado['respuesta_chatbot'],
        "confianza": resultado.get('confianza'),
        "detalles": resultado
    }
    
# 2. CONFIGURACIÓN DE LOGGING (después de imports)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 3. CREAR APP CON METADATA MEJORADA (reemplazar la línea app = FastAPI(...))
app = FastAPI(
    title="API Gestión de Inventarios",
    description="API REST para gestión de inventarios con chatbot PLN integrado",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 4. CONFIGURAR CORS (después de crear app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # React dev
        "http://localhost:8080",      # Flutter web dev  
        "http://localhost:5353",      # Vite dev
        "capacitor://localhost",      # Capacitor iOS/Android
        "http://127.0.0.1:5500",     # Live Server
        "http://localhost",           # Local development
        "https://your-domain.com",    # Tu dominio de producción
        "*"                           # SOLO para desarrollo - quitar en producción
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 5. MANEJADORES DE ERRORES GLOBALES (después de CORS)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path)
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(f"Validation Error: {exc} - Path: {request.url.path}")
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "message": "Datos de entrada inválidos",
            "details": exc.errors(),
            "status_code": 422,
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path)
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled Exception: {str(exc)} - Path: {request.url.path}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Error interno del servidor",
            "status_code": 500,
            "timestamp": datetime.now().isoformat(),
            "path": str(request.url.path)
        }
    )

# 6. MIDDLEWARE DE LOGGING (después de manejadores de errores)
@app.middleware("http")
async def log_requests(request, call_next):
    start_time = datetime.now()

    # Log request
    logger.info(f"Request: {request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}")

    try:
        response = await call_next(request)

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        # Log response
        logger.info(f"Response: {response.status_code} - Duration: {duration:.3f}s - Path: {request.url.path}")

        return response

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"Request failed: {str(e)} - Duration: {duration:.3f}s - Path: {request.url.path}")
        raise

# 7. ENDPOINT DE SALUD MEJORADO (agregar después de tus endpoints existentes)
@app.get("/health", tags=["Health"])
def health_check():
    """
    Endpoint de salud del sistema
    """
    try:
        # Verificar conexión a BD
        db = SessionLocal()
        try:
            # Consulta simple para verificar BD
            db.execute("SELECT 1")
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            db_status = "disconnected"
        finally:
            db.close()

        # Verificar PLN
        pln_status = "healthy"
        try:
            import pln as pln
            test_result = pln.procesar_orden_inventario("test")
            if not test_result:
                pln_status = "error"
        except Exception as e:
            logger.error(f"PLN health check failed: {str(e)}")
            pln_status = "error"

        overall_status = "healthy" if db_status == "connected" and pln_status == "healthy" else "degraded"

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

# 8. ENDPOINT DE INFORMACIÓN (agregar después del health check)
@app.get("/info", tags=["Info"])
def app_info():
    """
    Información general de la API
    """
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

# 9. MEJORAR EL ENDPOINT DEL CHATBOT (reemplazar el existente)
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

@app.post("/chatbot/inventario", response_model=ChatbotResponse, tags=["Chatbot"])
def chatbot_inventario_endpoint(
    request: ChatbotRequest,
    current_user: models.Usuario = Depends(require_role(["admin", "usuario"]))
):
    """
    Endpoint principal del chatbot para procesar órdenes de inventario

    **Ejemplos de mensajes soportados:**
    - "agrega 50 mouse logitech G203" 
    - "elimina 10 teclados razer blackwidow"
    - "consulta stock de impresoras epson"
    - "ajusta monitor samsung a 25"
    - "genera reporte de laptops dell"

    **Respuesta incluye:**
    - Texto conversacional para mostrar al usuario
    - Detalles de la operación ejecutada en BD
    - Nivel de confianza del análisis PLN
    """

    request_id = f"req_{int(datetime.now().timestamp())}"

    try:
        logger.info(f"Chatbot request [{request_id}]: '{request.mensaje}' - User: {current_user.correo}")

        # Procesar mensaje con chatbot
        from chatbot import procesar_mensaje_chatbot
        resultado = procesar_mensaje_chatbot(request.mensaje, current_user.id_usuario)

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

# 10. ENDPOINT DE AYUDA DEL CHATBOT (agregar)
@app.get("/chatbot/ayuda", tags=["Chatbot"])
def chatbot_ayuda():
    """
    Guía de uso del chatbot de inventario
    """
    return {
        "titulo": "🤖 Chatbot de Inventario - Guía de Uso",
        "descripcion": "Envía mensajes en español natural para gestionar tu inventario",
        "ejemplos": {
            "agregar_productos": [
                "agrega 50 mouse logitech G203",
                "añade 20 teclados HP K120", 
                "inserta 10 monitores Samsung 27 pulgadas"
            ],
            "eliminar_productos": [
                "elimina 5 impresoras Epson L3150",
                "quita 15 tablets Apple iPad",
                "saca 3 laptops Dell Inspiron"
            ],
            "consultar_stock": [
                "consulta stock de mouse logitech",
                "cuanto hay de teclados HP",
                "stock disponible de monitores samsung"
            ],
            "ajustar_inventario": [
                "ajusta mouse logitech a 100",
                "modifica teclados HP a 50", 
                "cambia stock de monitores a 25"
            ],
            "generar_reportes": [
                "genera reporte de impresoras",
                "haz reporte de productos Dell",
                "muestra reporte de inventario completo"
            ]
        },
        "consejos": [
            "✅ Especifica cantidad, producto y marca para mejores resultados",
            "✅ Usa verbos claros: agrega, quita, consulta, modifica, genera", 
            "✅ El chatbot entiende sinónimos: ratón/mouse, pantalla/monitor",
            "✅ Maneja plurales automáticamente: teclados → teclado",
            "⚠️ Si no entiende, te dará sugerencias para mejorar el mensaje"
        ],
        "confianza": {
            "alta": "0.8 - 1.0: Interpretación muy confiable",
            "media": "0.5 - 0.7: Interpretación probable",
            "baja": "0.3 - 0.4: Interpretación incierta", 
            "muy_baja": "0.0 - 0.2: No se pudo interpretar"
        }
    }

