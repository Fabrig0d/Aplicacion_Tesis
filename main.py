from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime
import os
from fastapi.responses import JSONResponse

# Módulos locales
import models, schemas, crud
from auth import authenticate_user, create_access_token, require_role
from database import SessionLocal, engine, Base

# Crear tablas
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas")
except Exception as e:
    print(f"⚠️ Error tablas: {e}")

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

# DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    token = create_access_token(data={"sub": user.correo})
    return {"access_token": token, "token_type": "bearer"}

# ========== CHATBOT PRINCIPAL ==========
@app.post("/chatbot/inventario", response_model=ChatbotResponse)
def chatbot_endpoint(
    request: ChatbotRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    try:
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
    """Procesamiento básico sin PLN pero con BD real"""
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

    try:
        if tipo == "entrada" and producto:
            # Buscar producto en BD
            prod_bd = db.query(models.Producto).filter(
                models.Producto.nombre.ilike(f"%{producto}%")
            ).first()
            
            if not prod_bd:
                return {
                    'exito': False,
                    'respuesta_chatbot': f"Producto {producto} no encontrado"
                }

            # Crear movimiento
            mov = models.MovimientoInventario(
                tipo=models.TipoMovimientoEnum.entrada,
                id_producto=prod_bd.id_producto,
                cantidad=cantidad,
                id_usuario=user.id_usuario,
                fecha_movimiento=datetime.now()
            )
            db.add(mov)
            
            # Actualizar stock
            prod_bd.stock_actual += cantidad
            db.commit()

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
                tipo=models.TipoMovimientoEnum.salida,
                id_producto=prod_bd.id_producto,
                cantidad=cantidad,
                id_usuario=user.id_usuario,
                fecha_movimiento=datetime.now()
            )
            db.add(mov)
            
            prod_bd.stock_actual -= cantidad
            db.commit()

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
                # Consulta general
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

    except Exception as e:
        db.rollback()
        return {'exito': False, 'respuesta_chatbot': f"Error: {str(e)[:50]}"}
    
# ========== ENDPOINTS DE DEBUG BD ==========
@app.get("/debug/database", tags=["Debug"])
def debug_database():
    """Información detallada de la conexión a BD"""
    try:
        from database import get_db_info, test_connection
        
        # Probar conexión
        connection_ok = test_connection()
        
        # Obtener info
        db_info = get_db_info()
        
        # Variables de entorno (sin mostrar credenciales completas)
        database_url = os.getenv("DATABASE_URL", "No configurada")
        url_preview = database_url[:30] + "..." if len(database_url) > 30 else database_url
        
        return {
            "connection_status": "✅ Conectado" if connection_ok else "❌ Error",
            "database_info": db_info,
            "environment": {
                "DATABASE_URL_configured": database_url != "No configurada",
                "DATABASE_URL_preview": url_preview,
                "render_external_hostname": os.getenv("RENDER_EXTERNAL_HOSTNAME", "No configurado"),
                "render_service_name": os.getenv("RENDER_SERVICE_NAME", "No configurado")
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error en debug database: {e}")
        return {
            "connection_status": "❌ Error crítico",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/debug/test-insert", tags=["Debug"])
def debug_test_insert(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador"]))
):
    """Prueba insertar un movimiento de prueba para verificar BD"""
    try:
        # Verificar que exista al menos un producto
        producto = db.query(models.Producto).first()
        if not producto:
            return {
                "error": "No hay productos en la BD para hacer la prueba",
                "suggestion": "Crea al menos un producto primero"
            }
        
        # Crear movimiento de prueba
        test_movimiento = models.MovimientoInventario(
            tipo=models.TipoMovimientoEnum.entrada,
            id_producto=producto.id_producto,
            cantidad=1,
            id_usuario=current_user.id_usuario,
            descripcion="🧪 Prueba de conexión BD desde API",
            fecha_movimiento=datetime.now()
        )
        
        db.add(test_movimiento)
        db.commit()
        db.refresh(test_movimiento)
        
        # Actualizar stock
        producto.stock_actual += 1
        db.commit()
        
        return {
            "success": "✅ Inserción exitosa",
            "movimiento_id": test_movimiento.id_movimiento,
            "producto_actualizado": {
                "id": producto.id_producto,
                "nombre": producto.nombre,
                "stock_actual": producto.stock_actual
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error en test insert: {e}")
        return {
            "error": f"❌ Fallo inserción: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/debug/productos-count", tags=["Debug"])
def debug_productos_count(db: Session = Depends(get_db)):
    """Cuenta productos en la BD para verificar datos"""
    try:
        total_productos = db.query(models.Producto).count()
        productos_con_stock = db.query(models.Producto).filter(models.Producto.stock_actual > 0).count()
        
        # Obtener algunos productos de ejemplo
        productos_ejemplo = db.query(models.Producto).limit(3).all()
        ejemplo_lista = []
        for p in productos_ejemplo:
            ejemplo_lista.append({
                "id": p.id_producto,
                "nombre": p.nombre,
                "marca": p.marca,
                "stock": p.stock_actual
            })
        
        return {
            "total_productos": total_productos,
            "productos_con_stock": productos_con_stock,
            "productos_ejemplo": ejemplo_lista,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error en productos count: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# ========== PRODUCTOS ==========
@app.get("/productos/")
def listar_productos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return crud.get_productos(db)

@app.post("/productos/")
def crear_producto(
    producto: schemas.ProductoCreate,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador"]))
):
    return crud.create_producto(db, producto)

# ========== MOVIMIENTOS ==========
@app.get("/movimientos/")
def listar_movimientos(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(require_role(["administrador", "operador"]))
):
    return crud.get_movimientos(db, skip=0, limit=50)

# ========== HEALTH ==========
@app.get("/health", tags=["Health"])
def health_check():
    """Health check mejorado con detalles de BD"""
    try:
        from database import test_connection, get_db_info
        
        # Test conexión
        db_connected = test_connection()
        db_info = get_db_info() if db_connected else {"status": "disconnected"}
        
        # Test básico de query
        try:
            db = SessionLocal()
            productos_count = db.query(models.Producto).count()
            db.close()
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
                    "productos_count": productos_count
                },
                "api": "✅ running"
            },
            "environment": {
                "service": os.getenv("RENDER_SERVICE_NAME", "unknown"),
                "region": os.getenv("RENDER_EXTERNAL_HOSTNAME", "unknown")
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

# ========== ADMIN DEMO ==========
@app.post("/crear-admin-demo")
def crear_admin(db: Session = Depends(get_db)):
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
        db.commit()

        return {"message": "Usuario creado", "correo": "admin@demo.com", "password": "demo123"}
        
    except Exception as e:
        db.rollback()
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)