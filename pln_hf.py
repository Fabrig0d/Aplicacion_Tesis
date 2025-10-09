import requests
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class HuggingFacePLN:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
        # URLs de modelos específicos
        self.intent_model = "Falconsai/intent_classification"  # Clasificación de intenciones
        self.text_gen_model = "google/mt5-small"  # Para entender y generar
        
    def clasificar_intencion(self, mensaje: str) -> Dict[str, Any]:
        """Detecta la intención del mensaje usando HF API"""
        api_url = f"https://api-inference.huggingface.co/models/{self.intent_model}"
        
        try:
            response = requests.post(
                api_url,
                headers=self.headers,
                json={"inputs": mensaje},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return {
                        "intencion": result[0].get("label", "desconocido"),
                        "confianza": result[0].get("score", 0.0),
                        "modelo": self.intent_model
                    }
            else:
                logger.warning(f"HF API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error llamando HF API: {e}")
            
        # Fallback básico
        return self.detectar_intencion_fallback(mensaje)
    
    def detectar_intencion_fallback(self, mensaje: str) -> Dict[str, Any]:
        """Detección básica sin API externa"""
        msg = mensaje.lower()
        
        intenciones = {
            "add_inventory": ["agrega", "añade", "agregar", "ingresa", "meter"],
            "remove_inventory": ["elimina", "quita", "sacar", "retirar"],
            "check_inventory": ["consulta", "stock", "cuanto", "disponible", "hay", "verifica"],
            "modify_inventory": ["ajusta", "modifica", "cambia", "actualiza", "establece"],
            "generate_report": ["reporte", "informe", "genera", "mostrar", "listar"]
        }
        
        for intencion, palabras in intenciones.items():
            if any(palabra in msg for palabra in palabras):
                return {
                    "intencion": intencion,
                    "confianza": 0.7,
                    "modelo": "fallback_reglas"
                }
                
        return {"intencion": "unknown", "confianza": 0.3, "modelo": "fallback"}
    
    def extraer_entidades(self, mensaje: str) -> Dict[str, Any]:
        """Extrae cantidad, producto, marca del mensaje"""
        import re
        
        # Extraer números (cantidad)
        numeros = re.findall(r'\d+', mensaje)
        cantidad = int(numeros[0]) if numeros else 1
        
        # Productos comunes (expandir según tu inventario)
        productos_conocidos = [
            "mouse", "ratón", "teclado", "keyboard", "monitor", "pantalla",
            "impresora", "printer", "laptop", "computadora", "tablet",
            "auriculares", "headphones", "cámara", "webcam", "router"
        ]
        
        # Marcas comunes
        marcas_conocidas = [
            "logitech", "hp", "dell", "samsung", "apple", "lenovo",
            "asus", "acer", "canon", "epson", "sony", "microsoft"
        ]
        
        mensaje_lower = mensaje.lower()
        
        # Detectar producto
        producto_detectado = None
        for producto in productos_conocidos:
            if producto in mensaje_lower:
                producto_detectado = producto
                break
        
        # Detectar marca
        marca_detectada = None
        for marca in marcas_conocidas:
            if marca in mensaje_lower:
                marca_detectada = marca
                break
        
        return {
            "cantidad": cantidad,
            "producto": producto_detectado or "producto",
            "marca": marca_detectada,
            "texto_original": mensaje
        }

# Instancia global
pln_hf = HuggingFacePLN()

def procesar_mensaje_chatbot(mensaje: str, usuario_id: int, db) -> Dict[str, Any]:
    """
    Función principal que procesa mensajes usando HF API + lógica de BD
    """
    try:
        # 1. Clasificar intención con HF API
        clasificacion = pln_hf.clasificar_intencion(mensaje)
        intencion = clasificacion["intencion"]
        confianza = clasificacion["confianza"]
        
        # 2. Extraer entidades básicas
        entidades = pln_hf.extraer_entidades(mensaje)
        
        # 3. Mapear intenciones a acciones de BD
        if intencion == "add_inventory" or "add" in intencion or any(w in mensaje.lower() for w in ["agrega", "añade"]):
            return procesar_entrada_inventario(entidades, usuario_id, db, confianza)
            
        elif intencion == "remove_inventory" or "remove" in intencion or any(w in mensaje.lower() for w in ["elimina", "quita"]):
            return procesar_salida_inventario(entidades, usuario_id, db, confianza)
            
        elif intencion == "check_inventory" or "check" in intencion or any(w in mensaje.lower() for w in ["consulta", "stock"]):
            return procesar_consulta_inventario(entidades, db, confianza)
            
        else:
            return {
                'exito': False,
                'respuesta_chatbot': f"🤔 No entendí la solicitud: '{mensaje}'\n\nIntenta comandos como:\n• agrega 10 mouse logitech\n• consulta stock de teclados\n• elimina 5 impresoras HP",
                'confianza': confianza,
                'orden_procesada': {'intencion_detectada': intencion, 'entidades': entidades}
            }
            
    except Exception as e:
        logger.error(f"Error en procesar_mensaje_chatbot: {e}")
        return {
            'exito': False,
            'respuesta_chatbot': "😵 Error procesando el mensaje. Intenta de nuevo.",
            'error': str(e)
        }

def procesar_entrada_inventario(entidades: Dict, usuario_id: int, db, confianza: float):
    """Maneja entradas al inventario"""
    from datetime import datetime
    import models
    
    try:
        producto_nombre = entidades["producto"]
        cantidad = entidades["cantidad"]
        marca = entidades["marca"]
        
        # Buscar producto en BD
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
                'exito': False,
                'respuesta_chatbot': f"❌ No encontré '{producto_nombre} {marca or ''}' en el inventario.\n\nUsa /productos para ver la lista completa.",
            }
        
        # Crear movimiento de entrada
        movimiento = models.MovimientoInventario(
            tipo=models.TipoMovimientoEnum.entrada,
            id_producto=producto.id_producto,
            cantidad=cantidad,
            id_usuario=usuario_id,
            descripcion=f"Entrada via chatbot HF: {entidades['texto_original']}",
            fecha_movimiento=datetime.now()
        )
        
        db.add(movimiento)
        producto.stock_actual += cantidad
        db.commit()
        
        return {
            'exito': True,
            'respuesta_chatbot': f"✅ **Entrada registrada**\n\n📦 Producto: {producto.nombre} {producto.marca or ''}\n🔢 Cantidad agregada: {cantidad}\n📊 Stock actual: {producto.stock_actual}",
            'confianza': confianza,
            'orden_procesada': {
                'tipo': 'entrada',
                'producto': producto.nombre,
                'cantidad': cantidad,
                'id_producto': producto.id_producto
            },
            'detalles_operacion': {
                'mensaje': f'Movimiento creado (ID: {movimiento.id_movimiento})',
                'bd_operacion': True,
                'stock_actualizado': producto.stock_actual
            }
        }
        
    except Exception as e:
        db.rollback()
        return {
            'exito': False,
            'respuesta_chatbot': f"😵 Error procesando entrada: {str(e)[:50]}",
            'error': str(e)
        }

def procesar_salida_inventario(entidades: Dict, usuario_id: int, db, confianza: float):
    """Maneja salidas del inventario"""
    # Similar lógica a entrada pero restando stock y validando disponibilidad
    # ... (implementación similar a procesar_entrada_inventario)
    pass

def procesar_consulta_inventario(entidades: Dict, db, confianza: float):
    """Maneja consultas de stock"""
    # Lógica para consultar productos
    # ... (implementación similar)
    pass