import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional
import requests
import models

logger = logging.getLogger(__name__)

class HuggingFacePLN:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.intent_model = "Falconsai/intent_classification"
        
    def clasificar_intencion(self, mensaje: str) -> Dict[str, Any]:
        """Detecta la intención del mensaje usando HF API o reglas directas."""
        # 1. Reglas directas rápidas para no depender de la API externa
        msg = mensaje.lower()
        if any(w in msg for w in ["agrega", "añade", "ingresa", "sumar", "entrada"]):
            return {"intencion": "add_inventory", "confianza": 0.9, "modelo": "reglas"}
        elif any(w in msg for w in ["elimina", "quita", "saca", "retira", "salida"]):
            return {"intencion": "remove_inventory", "confianza": 0.9, "modelo": "reglas"}
        elif any(w in msg for w in ["consulta", "stock", "cuanto", "disponible", "hay"]):
            return {"intencion": "check_inventory", "confianza": 0.9, "modelo": "reglas"}

        # 2. Intento con API HF con timeout corto (2 segundos)
        api_url = f"https://api-inference.huggingface.co/models/{self.intent_model}"
        try:
            response = requests.post(
                api_url,
                headers=self.headers,
                json={"inputs": mensaje},
                timeout=2
            )
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return {
                        "intencion": result[0].get("label", "unknown"),
                        "confianza": result[0].get("score", 0.0),
                        "modelo": self.intent_model
                    }
        except Exception:
            pass
            
        return {"intencion": "unknown", "confianza": 0.3, "modelo": "fallback"}

    def extraer_entidades(self, mensaje: str) -> Dict[str, Any]:
        """Extrae cantidad, producto y marca del mensaje."""
        numeros = re.findall(r'\d+', mensaje)
        cantidad = int(numeros[0]) if numeros else 1

        productos_conocidos = [
            "mouse", "raton", "ratón", "teclado", "keyboard", "monitor", "pantalla",
            "impresora", "printer", "laptop", "computadora", "tablet",
            "auriculares", "audifonos", "ssd", "hdd", "disco"
        ]

        marcas_conocidas = [
            "logitech", "hp", "dell", "samsung", "apple", "lenovo",
            "asus", "acer", "canon", "epson", "sony", "microsoft", "kingston"
        ]

        mensaje_lower = mensaje.lower()

        producto_detectado = next((p for p in productos_conocidos if p in mensaje_lower), None)
        marca_detectada = next((m for m in marcas_conocidas if m in mensaje_lower), None)

        return {
            "cantidad": cantidad,
            "producto": producto_detectado,
            "marca": marca_detectada,
            "texto_original": mensaje
        }

pln_hf = HuggingFacePLN()

def buscar_producto_en_bd(db, producto_nombre: Optional[str], marca: Optional[str]):
    """Busca el producto relacionando correctamente la tabla Marca."""
    query = db.query(models.Producto)
    
    if marca:
        query = query.outerjoin(models.Marca, models.Producto.id_marca == models.Marca.id_marca)
        query = query.filter(models.Marca.nombre_marca.ilike(f"%{marca}%"))
    
    if producto_nombre:
        query = query.filter(models.Producto.nombre.ilike(f"%{producto_nombre}%"))
    
    return query.first()

def procesar_mensaje_chatbot(mensaje: str, usuario_id: int, db) -> Dict[str, Any]:
    try:
        clasificacion = pln_hf.clasificar_intencion(mensaje)
        intencion = clasificacion["intencion"]
        confianza = clasificacion["confianza"]
        entidades = pln_hf.extraer_entidades(mensaje)

        if intencion == "add_inventory":
            return procesar_entrada_inventario(entidades, usuario_id, db, confianza)
        elif intencion == "remove_inventory":
            return procesar_salida_inventario(entidades, usuario_id, db, confianza)
        elif intencion == "check_inventory":
            return procesar_consulta_inventario(entidades, db, confianza)
        else:
            return {
                'exito': False,
                'respuesta_chatbot': f"🤔 No entendí la solicitud: '{mensaje}'\n\nEjemplos:\n• Agrega 10 mouse Logitech\n• Elimina 2 teclados\n• Consulta stock de monitores",
                'confianza': confianza,
                'orden_procesada': {'intencion': intencion, 'entidades': entidades}
            }
    except Exception as e:
        logger.exception("Error procesando mensaje chatbot")
        return {
            'exito': False,
            'respuesta_chatbot': f"Error: {str(e)[:80]}",
            'confianza': 0.0
        }

def procesar_entrada_inventario(entidades: Dict, usuario_id: int, db, confianza: float):
    try:
        producto_bd = buscar_producto_en_bd(db, entidades["producto"], entidades["marca"])
        if not producto_bd:
            return {
                'exito': False,
                'respuesta_chatbot': f"❌ No se encontró el producto '{entidades['producto'] or ''} {entidades['marca'] or ''}'.",
            }

        cantidad = entidades["cantidad"]
        movimiento = models.MovimientoInventario(
            tipo_movimiento=models.TipoMovimientoEnum.entrada,
            id_producto=producto_bd.id_producto,
            cantidad=cantidad,
            id_usuario=usuario_id,
            fecha_movimiento=datetime.now(),
            observaciones=f"Entrada vía chatbot: {entidades['texto_original']}"
        )

        db.add(movimiento)
        producto_bd.stock_actual += cantidad
        db.commit()

        return {
            'exito': True,
            'respuesta_chatbot': f"✅ **Entrada registrada**\n\n📦 Producto: {producto_bd.nombre}\n🔢 Cantidad: +{cantidad}\n📊 Stock actual: {producto_bd.stock_actual}",
            'confianza': confianza,
            'orden_procesada': {'tipo': 'entrada', 'producto': producto_bd.nombre, 'cantidad': cantidad}
        }
    except Exception as e:
        db.rollback()
        return {'exito': False, 'respuesta_chatbot': f"😵 Error procesando entrada: {str(e)[:80]}"}

def procesar_salida_inventario(entidades: Dict, usuario_id: int, db, confianza: float):
    try:
        producto_bd = buscar_producto_en_bd(db, entidades["producto"], entidades["marca"])
        if not producto_bd:
            return {'exito': False, 'respuesta_chatbot': f"❌ No se encontró el producto '{entidades['producto'] or ''}'."}

        cantidad = entidades["cantidad"]
        if producto_bd.stock_actual < cantidad:
            return {'exito': False, 'respuesta_chatbot': f"⚠️ Stock insuficiente. Disponible: {producto_bd.stock_actual}"}

        movimiento = models.MovimientoInventario(
            tipo_movimiento=models.TipoMovimientoEnum.salida,
            id_producto=producto_bd.id_producto,
            cantidad=cantidad,
            id_usuario=usuario_id,
            fecha_movimiento=datetime.now(),
            observaciones=f"Salida vía chatbot: {entidades['texto_original']}"
        )

        db.add(movimiento)
        producto_bd.stock_actual -= cantidad
        db.commit()

        return {
            'exito': True,
            'respuesta_chatbot': f"✅ **Salida registrada**\n\n📦 Producto: {producto_bd.nombre}\n🔢 Retirados: -{cantidad}\n📊 Stock actual: {producto_bd.stock_actual}",
            'confianza': confianza,
            'orden_procesada': {'tipo': 'salida', 'producto': producto_bd.nombre, 'cantidad': cantidad}
        }
    except Exception as e:
        db.rollback()
        return {'exito': False, 'respuesta_chatbot': f"😵 Error procesando salida: {str(e)[:80]}"}

def procesar_consulta_inventario(entidades: Dict, db, confianza: float):
    try:
        if entidades["producto"]:
            producto_bd = buscar_producto_en_bd(db, entidades["producto"], entidades["marca"])
            if producto_bd:
                return {
                    'exito': True,
                    'respuesta_chatbot': f"📊 **{producto_bd.nombre}**\n• Stock disponible: {producto_bd.stock_actual} unidades\n• Mínimo requerido: {producto_bd.stock_minimo}",
                    'confianza': confianza
                }
            return {'exito': False, 'respuesta_chatbot': f"❌ No se encontró el producto en el inventario."}

        # Consulta general si no especificó producto
        productos = db.query(models.Producto).limit(5).all()
        if productos:
            lista = [f"• {p.nombre}: {p.stock_actual} un." for p in productos]
            return {'exito': True, 'respuesta_chatbot': "📊 **Stock general:**\n" + "\n".join(lista), 'confianza': 0.8}

        return {'exito': True, 'respuesta_chatbot': "No hay productos registrados en el sistema."}
    except Exception as e:
        return {'exito': False, 'respuesta_chatbot': f"😵 Error en consulta: {str(e)[:80]}"}