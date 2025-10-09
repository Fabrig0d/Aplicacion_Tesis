from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime, timedelta
import os
from fastapi.responses import JSONResponse
import models, schemas, crud
from auth import authenticate_user, create_access_token, require_role
from database import engine, get_db_session

# App
app = FastAPI(title="API Inventario PLN", version="2.0.0")

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

# Schemas
class ChatbotRequest(BaseModel):
    mensaje: str

class ChatbotResponse(BaseModel):
    exito: bool
    respuesta_chatbot: str
    confianza: Optional[float] = None
    orden_procesada: Optional[Dict[str, Any]] = None
    timestamp: str

# Root
@app.get("/")
def root():
    return {"message": "API Inventario PLN", "version": "2.0.0"}

# ========== LOGIN ==========
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        with get_db_session() as db:
            user = authenticate_user(db, form_data.username, form_data.password)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciales incorrectas",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            token = create_access_token(data={"sub": user.correo})
            return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        # Nunca devolver 500 silencioso; mejor 400 con detalle acotado
        raise HTTPException(status_code=400, detail=f"Error en login")

# ========== USUARIOS ==========
@app.get("/usuarios/me")
def read_users_me(current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    """No necesita DB adicional ya que current_user viene de auth"""
    return {
        "id": current_user.id_usuario,
        "correo": current_user.correo,
        "nombre": current_user.nombre,
        "apellido": current_user.apellido,
        "rol": getattr(current_user.rol, "value", str(current_user.rol)),
        "telefono": getattr(current_user, 'telefono', None),
        "fecha_registro": getattr(current_user, 'fecha_registro', datetime.now()).isoformat() if hasattr(current_user, 'fecha_registro') else None,
    }

# ========== CHATBOT PRINCIPAL ==========
@app.post("/chatbot/inventario", response_model=ChatbotResponse)
def chatbot_endpoint(
    request: ChatbotRequest,
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """Chatbot con sesión única y context manager"""
    try:
        with get_db_session() as db:
            # Intentar PLN completo
            try:
                from pln_hf import procesar_mensaje_chatbot
                resultado = procesar_mensaje_chatbot(request.mensaje, current_user.id_usuario, db)
            except ImportError:
                # Fallback sin PLN
                resultado = procesar_fallback(request.mensaje, current_user, db)

            return ChatbotResponse(
                exito=resultado.get('exito', False),
                respuesta_chatbot=resultado.get('respuesta_chatbot', 'Sin respuesta'),
                confianza=resultado.get('confianza', 0.0),
                orden_procesada=resultado.get('orden_procesada'),
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Error chatbot: {e}")
        return ChatbotResponse(
            exito=False,
            respuesta_chatbot="Error procesando solicitud",
            timestamp=datetime.now().isoformat()
        )

def procesar_fallback(mensaje: str, user, db: Session):
    """Fallback que ya recibe la sesión como parámetro"""
    msg = mensaje.lower()
    
    # Detectar intención
    if any(w in msg for w in ["agrega", "añade"]):
        tipo = "entrada"
    elif any(w in msg for w in ["elimina", "quita", "saca"]):
        tipo = "salida"
    elif any(w in msg for w in ["consulta", "stock", "cuanto"]):
        tipo = "consulta"
    else:
        return {
            'exito': False,
            'respuesta_chatbot': "No entendí el comando. Usa: agrega, elimina, consulta"
        }

    # Extraer cantidad
    import re
    nums = re.findall(r'\d+', mensaje)
    cantidad = int(nums[0]) if nums else 1

    # Detectar producto básico
    productos = ["mouse", "teclado", "monitor", "impresora"]
    producto = None
    for p in productos:
        if p in msg:
            producto = p
            break

    if tipo == "entrada" and producto:
        prod_bd = db.query(models.Producto).filter(
            models.Producto.nombre.ilike(f"%{producto}%")
        ).first()
        
        if not prod_bd:
            return {
                'exito': False,
                'respuesta_chatbot': f"Producto {producto} no encontrado"
            }

        mov = models.MovimientoInventario(
            tipo_movimiento=models.TipoMovimientoEnum.entrada,
            id_producto=prod_bd.id_producto,
            cantidad=cantidad,
            id_usuario=user.id_usuario,
            fecha_movimiento=datetime.now()
        )
        db.add(mov)
        prod_bd.stock_actual += cantidad
        # No hacemos commit aquí, el context manager se encarga

        return {
            'exito': True,
            'respuesta_chatbot': f"✅ Agregados {cantidad} {prod_bd.nombre}. Stock: {prod_bd.stock_actual}",
            'confianza': 0.8,
            'orden_procesada': {'tipo': 'entrada', 'producto': prod_bd.nombre, 'cantidad': cantidad}
        }

    elif tipo == "salida" and producto:
        prod_bd = db.query(models.Producto).filter(
            models.Producto.nombre.ilike(f"%{producto}%")
        ).first()
        
        if not prod_bd:
            return {'exito': False, 'respuesta_chatbot': f"Producto {producto} no encontrado"}
        
        if prod_bd.stock_actual < cantidad:
            return {
                'exito': False,
                'respuesta_chatbot': f"Stock insuficiente. Disponible: {prod_bd.stock_actual}"
            }

        mov = models.MovimientoInventario(
            tipo_movimiento=models.TipoMovimientoEnum.salida,
            id_producto=prod_bd.id_producto,
            cantidad=cantidad,
            id_usuario=user.id_usuario,
            fecha_movimiento=datetime.now()
        )
        db.add(mov)
        prod_bd.stock_actual -= cantidad

        return {
            'exito': True,
            'respuesta_chatbot': f"✅ Retirados {cantidad} {prod_bd.nombre}. Stock: {prod_bd.stock_actual}",
            'confianza': 0.8,
            'orden_procesada': {'tipo': 'salida', 'producto': prod_bd.nombre, 'cantidad': cantidad}
        }

    elif tipo == "consulta":
        if producto:
            prod_bd = db.query(models.Producto).filter(
                models.Producto.nombre.ilike(f"%{producto}%")
            ).first()
            
            if prod_bd:
                return {
                    'exito': True,
                    'respuesta_chatbot': f"📊 {prod_bd.nombre}: {prod_bd.stock_actual} unidades",
                    'confianza': 0.9
                }
            else:
                return {'exito': False, 'respuesta_chatbot': f"Producto {producto} no encontrado"}
        else:
            productos = db.query(models.Producto).limit(5).all()
            if productos:
                lista = [f"• {p.nombre}: {p.stock_actual}" for p in productos]
                return {
                    'exito': True,
                    'respuesta_chatbot': "📊 Stock:\n" + "\n".join(lista),
                    'confianza': 0.9
                }
            else:
                return {'exito': True, 'respuesta_chatbot': "No hay productos registrados"}

    return {'exito': False, 'respuesta_chatbot': "No pude procesar la solicitud"}

# ========== DASHBOARD DATA ==========
@app.get("/dashboard/stats", tags=["Dashboard"])
def dashboard_stats(current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    """Dashboard stats con una sola sesión"""
    with get_db_session() as db:
        total_productos = db.query(models.Producto).count()
        
        productos_stock_bajo = db.query(models.Producto).filter(
            models.Producto.stock_actual <= models.Producto.stock_minimo
        ).count()
        
        total_stock = db.query(func.sum(models.Producto.stock_actual)).scalar() or 0
        
        desde_fecha = datetime.now() - timedelta(days=7)
        movimientos_recientes = db.query(models.MovimientoInventario).filter(
            models.MovimientoInventario.fecha_movimiento >= desde_fecha
        ).count()
        
        productos_activos = db.query(
            models.Producto.nombre,
            models.Producto.marca,
            func.count(models.MovimientoInventario.id_movimiento).label("movimientos")
        ).join(models.MovimientoInventario).group_by(
            models.Producto.id_producto
        ).order_by(func.count(models.MovimientoInventario.id_movimiento).desc()).limit(5).all()
        
        productos_activos_list = [
            {
                "nombre": f"{p.nombre} {p.marca or ''}".strip(),
                "movimientos": p.movimientos
            } for p in productos_activos
        ]
        
        return {
            "total_productos": total_productos,
            "productos_stock_bajo": productos_stock_bajo,
            "total_stock": total_stock,
            "movimientos_recientes": movimientos_recientes,
            "productos_activos": productos_activos_list,
            "timestamp": datetime.now().isoformat()
        }

@app.get("/dashboard/movimientos-recientes", tags=["Dashboard"])
def movimientos_recientes(
    limit: int = Query(10, ge=1, le=50),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """Movimientos recientes con una sola sesión"""
    with get_db_session() as db:
        movimientos = db.query(models.MovimientoInventario).join(
            models.Producto
        ).join(models.Usuario).order_by(
            models.MovimientoInventario.fecha_movimiento.desc()
        ).limit(limit).all()
        
        result = []
        for m in movimientos:
            result.append({
                "id": m.id_movimiento,
                "tipo": m.tipo_movimiento.value if hasattr(m.tipo_movimiento, 'value') else str(m.tipo_movimiento),
                "producto": f"{m.producto.nombre} {m.producto.marca or ''}".strip(),
                "cantidad": m.cantidad,
                "usuario": f"{m.usuario.nombre} {m.usuario.apellido}",
                "fecha": m.fecha_movimiento.isoformat(),
                "descripcion": m.descripcion or ""
            })
        
        return result

# ========== PRODUCTOS CON BÚSQUEDA ==========
@app.get("/productos/search", tags=["Productos"])
def buscar_productos(
    q: str = Query("", min_length=0, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    """Búsqueda de productos con una sola sesión"""
    with get_db_session() as db:
        query = db.query(models.Producto)
        
        if q.strip():
            search_term = f"%{q.strip()}%"
            query = query.filter(
                models.Producto.nombre.ilike(search_term) |
                models.Producto.marca.ilike(search_term) |
                models.Producto.modelo.ilike(search_term) |
                models.Producto.descripcion.ilike(search_term)
            )
        
        total = query.count()
        productos = query.offset(offset).limit(limit).all()
        
        result = []
        for p in productos:
            estado_stock = "bajo" if p.stock_actual <= p.stock_minimo else "normal"
            result.append({
                "id": p.id_producto,
                "nombre": p.nombre,
                "marca": p.marca or "",
                "modelo": p.modelo or "",
                "descripcion": p.descripcion or "",
                "stock_actual": p.stock_actual,
                "stock_minimo": p.stock_minimo,
                "estado_stock": estado_stock,
                "precio": float(p.precio) if p.precio else 0.0,
                "categoria": p.categoria.nombre if hasattr(p, 'categoria') and p.categoria else "",
                "fecha_actualizacion": p.fecha_actualizacion.isoformat() if hasattr(p, 'fecha_actualizacion') and p.fecha_actualizacion else None
            })
        
        return {
            "productos": result,
            "total": total,
            "page": offset // limit,
            "per_page": limit,
            "query": q
        }

# ========== PRODUCTOS LEGACY ==========
@app.get("/productos/")
def listar_productos(current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    with get_db_session() as db:
        return crud.get_productos(db)

@app.post("/productos/")
def crear_producto(
    producto: schemas.ProductoCreate,
    current_user: models.Usuario = Depends(require_role(["administrador"]))
):
    with get_db_session() as db:
        return crud.create_producto(db, producto)

@app.get("/movimientos/")
def listar_movimientos(current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))):
    with get_db_session() as db:
        return crud.get_movimientos(db, skip=0, limit=50)

# ========== HEALTH ==========
@app.get("/health", tags=["Health"])
def health_check():
    """Health check con información de pool"""
    try:
        from database import test_connection, get_db_info
        
        db_connected = test_connection()
        db_info = get_db_info() if db_connected else {"status": "disconnected"}
        
        # Test query con context manager
        try:
            with get_db_session() as db:
                productos_count = db.query(models.Producto).count()
            query_test = "✅ OK"
        except Exception as e:
            productos_count = "error"
            query_test = f"❌ {str(e)[:50]}"
        
        overall_status = "healthy" if db_connected and query_test.startswith("✅") else "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "services": {
                "database": {
                    "connection": "✅ connected" if db_connected else "❌ disconnected",
                    "info": db_info,
                    "query_test": query_test,
                    "productos_count": productos_count,
                    "pool_info": {
                        "size": engine.pool.size(),
                        "checked_out": engine.pool.checkedout(),
                        "overflow": engine.pool.overflow(),
                        "checked_in": engine.pool.checkedin()
                    }
                },
                "api": "✅ running"
            }
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

# ========== DEBUG ENDPOINTS (usar con precaución) ==========
@app.get("/debug/database", tags=["Debug"])
def debug_database():
    try:
        from database import get_db_info, test_connection
        
        connection_ok = test_connection()
        db_info = get_db_info()
        
        database_url = os.getenv("DATABASE_URL", "No configurada")
        url_preview = database_url[:30] + "..." if len(database_url) > 30 else database_url
        
        return {
            "connection_status": "✅ Conectado" if connection_ok else "❌ Error",
            "database_info": db_info,
            "environment": {
                "DATABASE_URL_configured": database_url != "No configurada",
                "DATABASE_URL_preview": url_preview,
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "connection_status": "❌ Error crítico",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ========== ADMIN DEMO ==========
@app.post("/crear-admin-demo")
def crear_admin():
    with get_db_session() as db:
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

            existing = db.query(models.Usuario).filter(
                models.Usuario.correo == "admin@demo.com"
            ).first()
            
            if existing:
                return {"message": "Usuario existe", "correo": "admin@demo.com"}

            admin = models.Usuario(
                nombre="Admin",
                apellido="Demo", 
                correo="admin@demo.com",
                rol=models.RolEnum.administrador if hasattr(models, 'RolEnum') else "administrador",
                password_hash=pwd_context.hash("demo123")
            )

            db.add(admin)
            return {"message": "Usuario creado", "correo": "admin@demo.com", "password": "demo123"}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)