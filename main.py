from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from datetime import datetime, timedelta
import traceback
import json

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
    title="API Gestión de Inventarios PLN",
    description="API REST completa para gestión de inventarios con chatbot PLN avanzado y PyTorch",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambiar en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging completo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Dependencias
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
    sugerencias: Optional[List[str]] = None
    timestamp: str
    request_id: Optional[str] = None

class OrdenRequest(BaseModel):
    texto: str
    ejecutar_en_bd: Optional[bool] = True
    modo_debug: Optional[bool] = False

class OrdenResponse(BaseModel):
    orden_original: str
    analisis_detallado: Dict[str, Any]
    orden_procesada: Dict[str, Any]
    mensaje: str
    confianza: float
    metodo_usado: str
    ejecutado_en_bd: bool = False
    error: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None

# Root
@app.get("/")
def root():
    return {
        "message": "API Inventario PLN - Versión Completa",
        "version": "2.0.0",
        "features": [
            "Chatbot PLN con PyTorch",
            "Guardado automático en BD", 
            "Análisis avanzado de intenciones",
            "Manejo de sinónimos y plurales",
            "CRUD completo de inventarios"
        ],
        "endpoints": ["/docs", "/health", "/login", "/chatbot/inventario", "/pln/orden", "/productos"]
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
    logger.info(f"Login exitoso: {user.correo}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/usuarios/me")
def read_users_me(
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return {
        "id": current_user.id_usuario,
        "correo": current_user.correo,
        "nombre": current_user.nombre,
        "apellido": current_user.apellido,
        "rol": getattr(current_user.rol, "value", str(current_user.rol)),
    }

# ========== CHATBOT PRINCIPAL CON PLN ==========
@app.post("/chatbot/inventario", response_model=ChatbotResponse, tags=["Chatbot"])
def chatbot_inventario_endpoint(
    request: ChatbotRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """
    🤖 Chatbot PLN avanzado que procesa órdenes en lenguaje natural,
    las analiza con PyTorch/transformers, y ejecuta operaciones en BD.
    
    **Ejemplos soportados:**
    - "agrega 50 mouse logitech G203 al inventario" 
    - "elimina 10 teclados razer blackwidow del stock"
    - "consulta cuántos monitores samsung tenemos"
    - "ajusta las impresoras epson L3250 a 25 unidades"
    - "genera un reporte de todos los productos HP"
    - "cuál es el stock actual de tablets apple"
    """
    request_id = f"req_{int(datetime.now().timestamp())}"
    start_time = datetime.now()
    
    logger.info(f"🤖 [{request_id}] Iniciando procesamiento PLN")
    logger.info(f"   Usuario: {current_user.correo} ({current_user.rol})")
    logger.info(f"   Mensaje: '{request.mensaje}'")

    try:
        # Cargar módulo PLN con manejo de errores
        try:
            logger.info(f"📚 [{request_id}] Cargando módulos PLN...")
            from chatbot_inventario_final import procesar_mensaje_chatbot
            pln_disponible = True
            logger.info(f"✅ [{request_id}] Módulo chatbot_inventario_final cargado")
        except ImportError as e:
            logger.warning(f"⚠️ [{request_id}] chatbot_inventario_final no disponible: {e}")
            try:
                from chatbot import procesar_mensaje_chatbot
                pln_disponible = True
                logger.info(f"✅ [{request_id}] Módulo chatbot alternativo cargado")
            except ImportError as e2:
                logger.error(f"❌ [{request_id}] No se pudo cargar ningún módulo chatbot: {e2}")
                pln_disponible = False

        # Procesar con PLN si está disponible
        if pln_disponible:
            logger.info(f"🧠 [{request_id}] Procesando con PLN avanzado...")
            resultado = procesar_mensaje_chatbot(
                mensaje=request.mensaje,
                usuario_id=current_user.id_usuario,
                db=db  # Pasar sesión de BD para operaciones directas
            )
        else:
            # Fallback inteligente sin PLN
            logger.info(f"🔄 [{request_id}] Usando fallback inteligente...")
            resultado = procesar_mensaje_fallback(request.mensaje, current_user, db)

        # Validar estructura del resultado
        if not isinstance(resultado, dict):
            raise ValueError("El procesador debe retornar un dict")
        
        # Calcular tiempo de procesamiento
        process_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"⏱️ [{request_id}] Procesamiento completado en {process_time:.2f}s")

        # Construir respuesta
        exito = bool(resultado.get('exito', False))
        resp = ChatbotResponse(
            exito=exito,
            respuesta_chatbot=resultado.get('respuesta_chatbot', 'Sin respuesta del chatbot'),
            confianza=resultado.get('confianza', 0.0),
            orden_procesada=resultado.get('orden_procesada'),
            detalles_operacion=resultado.get('detalles_operacion'),
            error=resultado.get('error'),
            sugerencias=resultado.get('sugerencias'),
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )

        # Log del resultado
        if exito:
            operacion = resultado.get('detalles_operacion', {})
            logger.info(f"✅ [{request_id}] Éxito: {operacion.get('mensaje', 'Operación completada')}")
            if operacion.get('bd_operacion'):
                logger.info(f"💾 [{request_id}] BD actualizada: {operacion.get('bd_detalle', '')}")
        else:
            error_msg = resultado.get('error', 'Error no especificado')
            logger.warning(f"❌ [{request_id}] Error: {error_msg}")

        return resp

    except Exception as e:
        process_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"💥 [{request_id}] Error crítico después de {process_time:.2f}s: {e}")
        logger.error(f"   Traceback: {traceback.format_exc()}")
        
        return ChatbotResponse(
            exito=False,
            respuesta_chatbot="😵 Ocurrió un error inesperado al procesar tu solicitud. El equipo técnico ha sido notificado.",
            error=f"Error interno: {str(e)[:200]}",
            timestamp=datetime.now().isoformat(),
            request_id=request_id
        )

def procesar_mensaje_fallback(mensaje: str, current_user, db: Session) -> Dict[str, Any]:
    """
    Fallback inteligente sin PLN pesado pero con lógica de BD real
    """
    mensaje_lower = mensaje.lower().strip()
    
    # Detectar intención y extraer información básica
    intenciones = {
        "entrada": ["agrega", "añade", "agregar", "añadir", "ingresa", "meter"],
        "salida": ["elimina", "quita", "sacar", "retirar", "eliminar", "quitar"],
        "consulta": ["consulta", "stock", "cuanto", "disponible", "hay", "tenemos", "check"],
        "ajuste": ["ajusta", "modifica", "cambia", "actualiza", "establece", "poner"],
        "reporte": ["reporte", "informe", "genera", "mostrar", "listar", "ver"]
    }
    
    tipo_detectado = "desconocido"
    for tipo, palabras in intenciones.items():
        if any(palabra in mensaje_lower for palabra in palabras):
            tipo_detectado = tipo
            break
    
    # Extraer números (cantidad)
    import re
    numeros = re.findall(r'\d+', mensaje)
    cantidad = int(numeros[0]) if numeros else 1
    
    # Simular detección de productos (básico)
    palabras = mensaje_lower.split()
    productos_comunes = ["mouse", "teclado", "monitor", "impresora", "laptop", "tablet", "auricular"]
    producto_detectado = None
    for palabra in palabras:
        for prod in productos_comunes:
            if prod in palabra or palabra in prod:
                producto_detectado = prod
                break
        if producto_detectado:
            break
    
    if not producto_detectado:
        producto_detectado = "producto"
    
    try:
        # Intentar operación real en BD según el tipo
        if tipo_detectado == "entrada":
            # Buscar o crear producto
            producto_bd = db.query(models.Producto).filter(
                models.Producto.nombre.ilike(f"%{producto_detectado}%")
            ).first()
            
            if not producto_bd:
                return {
                    'exito': False,
                    'respuesta_chatbot': f"❌ No encontré el producto '{producto_detectado}' en el sistema. Agrega el producto primero.",
                    'error': f"Producto {producto_detectado} no existe",
                    'sugerencias': ["Verifica el nombre del producto", "Usa /productos para ver la lista completa"]
                }
            
            # Crear movimiento de entrada
            nuevo_movimiento = models.MovimientoInventario(
                tipo=models.TipoMovimientoEnum.entrada,
                id_producto=producto_bd.id_producto,
                cantidad=cantidad,
                id_usuario=current_user.id_usuario,
                descripcion=f"Entrada vía chatbot: {mensaje}",
                fecha_movimiento=datetime.now()
            )
            
            db.add(nuevo_movimiento)
            db.commit()
            db.refresh(nuevo_movimiento)
            
            # Actualizar stock del producto
            producto_bd.stock_actual += cantidad
            db.commit()
            
            return {
                'exito': True,
                'respuesta_chatbot': f"✅ Se agregaron {cantidad} unidades de {producto_bd.nombre} {producto_bd.marca} al inventario.\n\n📊 Stock actual: {producto_bd.stock_actual} unidades",
                'confianza': 0.8,
                'orden_procesada': {
                    'tipo': 'entrada',
                    'producto': producto_bd.nombre,
                    'cantidad': cantidad,
                    'id_producto': producto_bd.id_producto
                },
                'detalles_operacion': {
                    'mensaje': f'Movimiento de entrada creado (ID: {nuevo_movimiento.id_movimiento})',
                    'bd_operacion': True,
                    'bd_detalle': f'Stock actualizado: {producto_bd.stock_actual}',
                    'id_movimiento': nuevo_movimiento.id_movimiento
                }
            }
            
        elif tipo_detectado == "salida":
            # Similar lógica para salidas
            producto_bd = db.query(models.Producto).filter(
                models.Producto.nombre.ilike(f"%{producto_detectado}%")
            ).first()
            
            if not producto_bd:
                return {
                    'exito': False,
                    'respuesta_chatbot': f"❌ No encontré el producto '{producto_detectado}' en el sistema.",
                    'error': f"Producto {producto_detectado} no existe"
                }
            
            if producto_bd.stock_actual < cantidad:
                return {
                    'exito': False,
                    'respuesta_chatbot': f"❌ Stock insuficiente de {producto_bd.nombre}.\n\n📊 Stock actual: {producto_bd.stock_actual}\n🔢 Solicitado: {cantidad}",
                    'error': "Stock insuficiente"
                }
            
            # Crear movimiento de salida
            nuevo_movimiento = models.MovimientoInventario(
                tipo=models.TipoMovimientoEnum.salida,
                id_producto=producto_bd.id_producto,
                cantidad=cantidad,
                id_usuario=current_user.id_usuario,
                descripcion=f"Salida vía chatbot: {mensaje}",
                fecha_movimiento=datetime.now()
            )
            
            db.add(nuevo_movimiento)
            db.commit()
            
            # Actualizar stock
            producto_bd.stock_actual -= cantidad
            db.commit()
            
            return {
                'exito': True,
                'respuesta_chatbot': f"✅ Se retiraron {cantidad} unidades de {producto_bd.nombre} {producto_bd.marca} del inventario.\n\n📊 Stock restante: {producto_bd.stock_actual} unidades",
                'confianza': 0.8,
                'orden_procesada': {
                    'tipo': 'salida',
                    'producto': producto_bd.nombre,
                    'cantidad': cantidad,
                    'id_producto': producto_bd.id_producto
                },
                'detalles_operacion': {
                    'mensaje': f'Movimiento de salida creado (ID: {nuevo_movimiento.id_movimiento})',
                    'bd_operacion': True,
                    'bd_detalle': f'Stock actualizado: {producto_bd.stock_actual}'
                }
            }
            
        elif tipo_detectado == "consulta":
            # Consultar stock
            if producto_detectado == "producto":
                # Listar todos los productos
                productos = db.query(models.Producto).limit(10).all()
                if not productos:
                    return {
                        'exito': True,
                        'respuesta_chatbot': "📭 No hay productos registrados en el sistema.",
                        'confianza': 0.9
                    }
                
                lista_productos = []
                for p in productos:
                    estado = "🔴 Stock bajo" if p.stock_actual <= p.stock_minimo else "✅ Stock normal"
                    lista_productos.append(f"• {p.nombre} {p.marca or ''} ({p.modelo or ''}): {p.stock_actual} unidades {estado}")
                
                return {
                    'exito': True,
                    'respuesta_chatbot': f"📊 **Stock general de productos:**\n\n" + "\n".join(lista_productos[:8]) + ("\n\n... y más productos en /productos" if len(productos) > 8 else ""),
                    'confianza': 0.95,
                    'orden_procesada': {'tipo': 'consulta_general'},
                    'detalles_operacion': {'mensaje': f'Consultados {len(productos)} productos'}
                }
            else:
                # Consultar producto específico
                productos = db.query(models.Producto).filter(
                    models.Producto.nombre.ilike(f"%{producto_detectado}%")
                ).all()
                
                if not productos:
                    return {
                        'exito': False,
                        'respuesta_chatbot': f"❌ No encontré productos que coincidan con '{producto_detectado}'.",
                        'error': "Producto no encontrado"
                    }
                
                if len(productos) == 1:
                    p = productos[0]
                    estado = "🔴 Stock bajo" if p.stock_actual <= p.stock_minimo else "✅ Stock normal"
                    return {
                        'exito': True,
                        'respuesta_chatbot': f"📊 **Stock de {p.nombre} {p.marca or ''}:**\n\n🔢 Cantidad actual: {p.stock_actual} unidades\n📉 Stock mínimo: {p.stock_minimo} unidades\n{estado}",
                        'confianza': 0.9,
                        'orden_procesada': {'tipo': 'consulta', 'producto': p.nombre, 'id_producto': p.id_producto}
                    }
                else:
                    lista = [f"• {p.nombre} {p.marca or ''}: {p.stock_actual} unidades" for p in productos[:5]]
                    return {
                        'exito': True,
                        'respuesta_chatbot': f"📊 **Encontré {len(productos)} productos con '{producto_detectado}':**\n\n" + "\n".join(lista),
                        'confianza': 0.85
                    }
        
        else:
            return {
                'exito': False,
                'respuesta_chatbot': f"🤔 No entendí qué quieres hacer con: '{mensaje}'\n\n💡 **Ejemplos de comandos:**\n• agrega 10 mouse logitech\n• elimina 5 teclados HP\n• consulta stock de monitores\n• ajusta impresoras a 25",
                'error': "Intención no reconocida",
                'sugerencias': [
                    "Usa verbos como: agrega, elimina, consulta",
                    "Especifica cantidad y producto",
                    "Ejemplo: 'agrega 5 mouse logitech'"
                ]
            }
            
    except Exception as e:
        db.rollback()
        logger.error(f"Error en fallback BD: {e}")
        return {
            'exito': False,
            'respuesta_chatbot': f"😵 Error al procesar la operación en la base de datos: {str(e)[:100]}",
            'error': f"Error BD: {str(e)}"
        }

# ========== ENDPOINT PLN AVANZADO ==========
@app.post("/pln/orden", response_model=OrdenResponse, tags=["PLN"])
def procesar_orden_pln_avanzada(
    request: OrdenRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """
    🧠 Procesamiento PLN avanzado con análisis detallado.
    
    Usa modelos de PyTorch/transformers para análisis completo:
    - Detección de intenciones con alta precisión
    - Extracción de entidades (productos, cantidades, marcas)  
    - Manejo de sinónimos y plurales
    - Ejecución directa en BD
    """
    start_time = datetime.now()
    
    try:
        # Cargar módulo PLN
        try:
            import pln
            resultado_completo = pln.procesar_orden_inventario(request.texto)
            analisis = resultado_completo.get('json_intermedio', {})
            orden = resultado_completo.get('resultado_final', {})
            metodo = "PLN_completo_pytorch"
        except ImportError:
            logger.warning("Módulo PLN no disponible, usando análisis básico")
            analisis = {"confianza": 0.6, "metodo": "basico", "error": "PLN no disponible"}
            orden = {"tipo_movimiento": "desconocido"}
            metodo = "basico_fallback"
        except Exception as e:
            logger.error(f"Error en módulo PLN: {e}")
            analisis = {"confianza": 0.3, "error": str(e)}
            orden = {"tipo_movimiento": "error"}
            metodo = "error_pln"
        
        # Ejecutar en BD si se solicita
        ejecutado_en_bd = False
        mensaje_resultado = "Análisis completado"
        error_bd = None
        debug_info = {}
        
        if request.ejecutar_en_bd and orden.get('tipo_movimiento') != 'desconocido':
            try:
                resultado_bd = ejecutar_orden_avanzada(orden, db, current_user)
                ejecutado_en_bd = resultado_bd['exito']
                if ejecutado_en_bd:
                    mensaje_resultado = resultado_bd['mensaje']
                else:
                    error_bd = resultado_bd['error']
                    mensaje_resultado = f"Error en BD: {error_bd}"
                
                if request.modo_debug:
                    debug_info = resultado_bd.get('debug', {})
                    
            except Exception as e:
                error_bd = str(e)
                mensaje_resultado = f"Error ejecutando en BD: {error_bd}"
                logger.error(f"Error BD en PLN: {e}")
        
        process_time = (datetime.now() - start_time).total_seconds()
        
        return OrdenResponse(
            orden_original=request.texto,
            analisis_detallado=analisis,
            orden_procesada=orden,
            mensaje=mensaje_resultado,
            confianza=analisis.get('confianza', 0.0),
            metodo_usado=metodo,
            ejecutado_en_bd=ejecutado_en_bd,
            error=error_bd,
            debug_info=debug_info if request.modo_debug else None
        )
        
    except Exception as e:
        logger.error(f"Error en endpoint PLN: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando orden PLN: {str(e)}")

def ejecutar_orden_avanzada(orden: Dict[str, Any], db: Session, usuario) -> Dict[str, Any]:
    """Ejecuta orden con más validaciones y logging"""
    tipo = orden.get("tipo_movimiento")
    producto_nombre = orden.get("producto")
    cantidad = orden.get("cantidad", 0)
    marca = orden.get("marca")
    
    debug_info = {"orden_recibida": orden, "validaciones": []}
    
    try:
        if not producto_nombre:
            return {
                "exito": False, 
                "error": "Producto no especificado",
                "debug": debug_info
            }
        
        # Buscar producto
        query = db.query(models.Producto)
        if marca:
            producto = query.filter(
                models.Producto.nombre.ilike(f"%{producto_nombre}%"),
                models.Producto.marca.ilike(f"%{marca}%")
            ).first()
        else:
            producto = query.filter(
                models.Producto.nombre.ilike(f"%{producto_nombre}%")
            ).first()
        
        if not producto:
            return {
                "exito": False,
                "error": f"Producto '{producto_nombre}' {marca or ''} no encontrado",
                "debug": debug_info
            }
        
        debug_info["producto_encontrado"] = {
            "id": producto.id_producto,
            "nombre": producto.nombre,
            "stock_actual": producto.stock_actual
        }
        
        # Ejecutar según tipo
        if tipo == "entrada":
            movimiento = models.MovimientoInventario(
                tipo=models.TipoMovimientoEnum.entrada,
                id_producto=producto.id_producto,
                cantidad=cantidad,
                id_usuario=usuario.id_usuario,
                descripcion=f"Entrada PLN: {orden.get('descripcion', '')}",
                fecha_movimiento=datetime.now()
            )
            db.add(movimiento)
            
            producto.stock_actual += cantidad
            db.commit()
            
            return {
                "exito": True,
                "mensaje": f"✅ Entrada registrada: +{cantidad} {producto.nombre}. Stock: {producto.stock_actual}",
                "debug": debug_info
            }
            
        elif tipo == "salida":
            if producto.stock_actual < cantidad:
                return {
                    "exito": False,
                    "error": f"Stock insuficiente. Disponible: {producto.stock_actual}, Solicitado: {cantidad}",
                    "debug": debug_info
                }
            
            movimiento = models.MovimientoInventario(
                tipo=models.TipoMovimientoEnum.salida,
                id_producto=producto.id_producto,
                cantidad=cantidad,
                id_usuario=usuario.id_usuario,
                descripcion=f"Salida PLN: {orden.get('descripcion', '')}",
                fecha_movimiento=datetime.now()
            )
            db.add(movimiento)
            
            producto.stock_actual -= cantidad
            db.commit()
            
            return {
                "exito": True,
                "mensaje": f"✅ Salida registrada: -{cantidad} {producto.nombre}. Stock: {producto.stock_actual}",
                "debug": debug_info
            }
            
        else:
            return {
                "exito": False,
                "error": f"Tipo de movimiento no soportado: {tipo}",
                "debug": debug_info
            }
            
    except Exception as e:
        db.rollback()
        return {
            "exito": False,
            "error": f"Error en operación: {str(e)}",
            "debug": debug_info
        }

# ========== ENDPOINTS CRUD ==========
@app.get("/productos/", response_model=List[schemas.Producto])
def listar_productos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None, max_length=100),
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """Lista productos con paginación y búsqueda"""
    query = db.query(models.Producto)
    
    if search:
        query = query.filter(
            models.Producto.nombre.ilike(f"%{search}%") |
            models.Producto.marca.ilike(f"%{search}%") |
            models.Producto.modelo.ilike(f"%{search}%")
        )
    
    productos = query.offset(skip).limit(limit).all()
    return productos

@app.post("/productos/", response_model=schemas.Producto)
def crear_producto(
    producto: schemas.ProductoCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador"]))
):
    """Crear nuevo producto (solo administradores)"""
    return crud.create_producto(db, producto)

@app.get("/movimientos/", response_model=List[schemas.MovimientoInventario])
def listar_movimientos(
    skip: int = 0,
    limit: int = 100,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """Lista movimientos de inventario recientes"""
    return crud.get_movimientos(db=db, skip=skip, limit=limit)

@app.get("/categorias/", response_model=List[schemas.Categoria])
def listar_categorias(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return crud.get_categorias(db)

@app.get("/marcas/", response_model=List[schemas.Marca])
def listar_marcas(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return crud.get_marcas(db)

# ========== HEALTH & MONITORING ==========
@app.get("/health", tags=["Health"])
def health_check():
    """Health check completo con verificación de servicios"""
    start_time = datetime.now()
    
    try:
        # DB Check
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "connected"
            db_info = {"connection": "ok"}
        except Exception as e:
            db_status = "disconnected" 
            db_info = {"error": str(e)}
        finally:
            db.close()
        
        # PLN Check
        pln_status = "healthy"
        pln_info = {}
        try:
            import torch
            pln_info["torch_version"] = torch.__version__
            pln_info["torch_available"] = True
            
            try:
                import transformers
                pln_info["transformers_version"] = transformers.__version__
                pln_status = "healthy"
            except ImportError:
                pln_status = "limited"
                pln_info["transformers_available"] = False
                
        except ImportError:
            pln_status = "unavailable"
            pln_info["torch_available"] = False
        
        # Performance
        check_time = (datetime.now() - start_time).total_seconds()
        performance = {
            "check_duration_seconds": round(check_time, 3),
            "status": "fast" if check_time < 1 else "slow"
        }
        
        overall_status = "healthy" if db_status == "connected" else "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "services": {
                "database": {"status": db_status, "details": db_info},
                "pln": {"status": pln_status, "details": pln_info},
                "chatbot": {"status": "healthy"}
            },
            "performance": performance
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )

@app.get("/chatbot/ayuda", tags=["Chatbot"])
def chatbot_ayuda():
    """Guía completa de uso del chatbot"""
    return {
        "titulo": "🤖 Chatbot PLN de Inventarios - Guía Completa",
        "version": "2.0.0",
        "capacidades": [
            "Análisis avanzado con PyTorch/Transformers",
            "Detección automática de intenciones",
            "Manejo de sinónimos y plurales",
            "Ejecución directa en base de datos",
            "Validaciones de stock automáticas"
        ],
        "ejemplos": {
            "entradas": [
                "agrega 50 mouse logitech G203 al inventario",
                "añade 20 teclados mecánicos Corsair K95",
                "ingresa 15 monitores Samsung 24 pulgadas"
            ],
            "salidas": [
                "elimina 5 impresoras Epson L3150 del stock", 
                "retira 10 tablets Apple iPad del inventario",
                "quita 3 laptops HP Pavilion"
            ],
            "consultas": [
                "consulta el stock de mouse logitech",
                "cuántas impresoras Epson tenemos disponibles",
                "verifica el inventario de productos HP"
            ],
            "ajustes": [
                "ajusta las laptops Dell a 25 unidades",
                "modifica el stock de teclados HP a 40",
                "establece los auriculares Sony en 60"
            ]
        },
        "consejos": [
            "Sé específico con marcas y modelos",
            "Incluye cantidades numéricas", 
            "Usa verbos claros (agrega, elimina, consulta)",
            "El sistema maneja plurales automáticamente"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Iniciando API de Inventarios con PLN completo...")
    uvicorn.run(app, host="0.0.0.0", port=8000)