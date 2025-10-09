from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import logging
from datetime import datetime
import traceback

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
            from chatbot import procesar_mensaje_chatbot
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
@app.get("/health")
def health():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database": "error", "error": str(e)}

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