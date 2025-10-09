from sqlalchemy.orm import Session
import crud
from database import SessionLocal
import pln as pln
from typing import Dict, Any, Optional
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatbotInventario:
    """
    Chatbot para gestión de inventario con procesamiento PLN y ejecución directa en BD
    """

    def __init__(self):
        self.contexto_usuario = {}

    def get_db_session(self):
        """Obtener sesión de base de datos"""
        return SessionLocal()

    def procesar_mensaje_inventario(self, mensaje: str, usuario_id: int = None) -> Dict[str, Any]:
        """
        Función principal del chatbot que procesa un mensaje y ejecuta en BD
        """

        db = self.get_db_session()

        try:
            # 1. Procesar mensaje con PLN mejorado
            logger.info(f"Procesando mensaje: '{mensaje}'")
            resultado_pln = pln.procesar_orden_inventario(mensaje)

            json_intermedio = resultado_pln['json_intermedio']
            orden_final = resultado_pln['resultado_final']
            confianza = json_intermedio.get('confianza', 0.0)

            logger.info(f"PLN resultado: {orden_final}, confianza: {confianza}")

            # 2. Validar confianza mínima
            if confianza < 0.3:
                return {
                    'exito': False,
                    'respuesta_chatbot': f"🤔 No entendí bien tu solicitud (confianza: {confianza:.1f}). ¿Puedes ser más específico?\n\nEjemplo: 'agrega 10 mouse logitech G203' o 'consulta stock de teclados HP'",
                    'confianza': confianza,
                    'sugerencias': [
                        "Especifica cantidad, producto y marca",
                        "Usa verbos como: agrega, quita, consulta, modifica",
                        "Ejemplo: 'elimina 5 impresoras Epson'"
                    ]
                }

            # 3. Validar información mínima
            tipo_mov = orden_final.get('tipo_movimiento')
            producto = orden_final.get('producto')
            marca = orden_final.get('marca')
            modelo = orden_final.get('modelo')
            cantidad = orden_final.get('cantidad')

            if tipo_mov == 'desconocido':
                return {
                    'exito': False,
                    'respuesta_chatbot': f"🚫 No reconozco esa acción. Puedes usar:\n\n✅ **Agregar**: 'agrega 20 mouse hp'\n✅ **Quitar**: 'elimina 5 teclados dell'\n✅ **Consultar**: 'stock de monitores samsung'\n✅ **Ajustar**: 'modifica laptops asus a 15'\n✅ **Reporte**: 'genera reporte de impresoras'",
                    'accion_detectada': json_intermedio.get('accion', 'ninguna'),
                    'confianza': confianza
                }

            # 4. Ejecutar operación según tipo de movimiento
            usuario_id = usuario_id or 1  # Default admin user
            resultado_bd = self._ejecutar_operacion_bd(orden_final, db, usuario_id)

            if resultado_bd['exito']:
                # Operación exitosa - respuesta amigable
                respuesta = self._generar_respuesta_exitosa(tipo_mov, producto, marca, modelo, cantidad, resultado_bd)
                return {
                    'exito': True,
                    'respuesta_chatbot': respuesta,
                    'orden_procesada': orden_final,
                    'confianza': confianza,
                    'detalles_operacion': resultado_bd
                }
            else:
                # Error en BD - respuesta con ayuda
                respuesta = self._generar_respuesta_error(tipo_mov, producto, marca, modelo, cantidad, resultado_bd)
                return {
                    'exito': False,
                    'respuesta_chatbot': respuesta,
                    'error': resultado_bd.get('error'),
                    'confianza': confianza,
                    'detalles_operacion': resultado_bd
                }

        except Exception as e:
            logger.error(f"Error en chatbot: {str(e)}")
            return {
                'exito': False,
                'respuesta_chatbot': f"😵 Algo salió mal procesando tu solicitud.\n\n**Error**: {str(e)}\n\nSi el problema persiste, contacta al administrador.",
                'error_tecnico': str(e),
                'confianza': 0.0
            }
        finally:
            db.close()

    def _ejecutar_operacion_bd(self, orden: Dict[str, Any], db: Session, usuario_id: int) -> Dict[str, Any]:
        """
        Ejecuta la operación en la base de datos según el tipo de movimiento
        """

        tipo_mov = orden.get("tipo_movimiento")
        producto = orden.get("producto")
        marca = orden.get("marca")
        modelo = orden.get("modelo")
        cantidad = orden.get("cantidad")

        try:
            if tipo_mov == "entrada" and cantidad and cantidad > 0:
                return self._ejecutar_entrada(db, producto, marca, modelo, cantidad, usuario_id)

            elif tipo_mov == "salida" and cantidad and cantidad > 0:
                return self._ejecutar_salida(db, producto, marca, modelo, cantidad, usuario_id)

            elif tipo_mov == "ajuste" and cantidad is not None:
                return self._ejecutar_ajuste(db, producto, marca, modelo, cantidad, usuario_id)

            elif tipo_mov == "consulta":
                return self._ejecutar_consulta(db, producto, marca, modelo)

            elif tipo_mov == "reporte":
                return self._ejecutar_reporte(db, producto, marca, modelo)

            else:
                return {
                    'exito': False,
                    'error': f"Operación no soportada: {tipo_mov}",
                    'mensaje': "Tipo de operación no reconocida"
                }

        except Exception as e:
            logger.error(f"Error ejecutando {tipo_mov}: {str(e)}")
            return {
                'exito': False,
                'error': str(e),
                'mensaje': f"Error ejecutando operación {tipo_mov}"
            }

    def _ejecutar_entrada(self, db: Session, producto: str, marca: str, modelo: str, cantidad: int, usuario_id: int) -> Dict[str, Any]:
        """Ejecutar entrada de inventario - PERSISTE EN BD"""
        try:
            logger.info(f"Ejecutando ENTRADA: {producto} {marca} {modelo}, cantidad: {cantidad}")

            # 1. Buscar o crear producto
            producto_bd = crud.buscar_o_crear_producto(db, producto, marca, modelo)
            logger.info(f"Producto obtenido: ID={producto_bd.id_producto}, stock actual={producto_bd.stock_actual}")

            # 2. Crear movimiento de entrada
            movimiento = crud.crear_movimiento_inventario(
                db,
                producto_id=producto_bd.id_producto,
                usuario_id=usuario_id,
                tipo_movimiento='entrada',
                cantidad=cantidad,
                observaciones=f'Agregado via chatbot: {cantidad} {producto} {marca} {modelo or ""}'.strip()
            )
            logger.info(f"Movimiento creado: ID={movimiento.id_movimiento}")

            # 3. Actualizar stock
            producto_actualizado = crud.actualizar_stock_producto(db, producto_bd.id_producto, cantidad, 'entrada')
            logger.info(f"Stock actualizado: {producto_actualizado.stock_actual}")

            return {
                'exito': True,
                'mensaje': f"Agregados {cantidad} {producto} {marca} {modelo or ''}".strip(),
                'producto_id': producto_bd.id_producto,
                'movimiento_id': movimiento.id_movimiento,
                'stock_anterior': producto_bd.stock_actual,
                'stock_nuevo': producto_actualizado.stock_actual
            }

        except Exception as e:
            logger.error(f"Error en entrada: {str(e)}")
            return {
                'exito': False,
                'error': str(e),
                'mensaje': "No se pudo agregar al inventario"
            }

    def _ejecutar_salida(self, db: Session, producto: str, marca: str, modelo: str, cantidad: int, usuario_id: int) -> Dict[str, Any]:
        """Ejecutar salida de inventario - PERSISTE EN BD"""
        try:
            logger.info(f"Ejecutando SALIDA: {producto} {marca} {modelo}, cantidad: {cantidad}")

            # 1. Buscar producto existente
            producto_bd = crud.buscar_producto_exacto(db, producto, marca, modelo)

            if not producto_bd:
                return {
                    'exito': False,
                    'error': 'Producto no encontrado',
                    'mensaje': f"No existe {producto} {marca} {modelo or ''} en el inventario".strip()
                }

            logger.info(f"Producto encontrado: ID={producto_bd.id_producto}, stock actual={producto_bd.stock_actual}")

            # 2. Verificar stock suficiente
            if producto_bd.stock_actual < cantidad:
                return {
                    'exito': False,
                    'error': 'Stock insuficiente',
                    'mensaje': f"Stock insuficiente. Disponible: {producto_bd.stock_actual}, solicitado: {cantidad}",
                    'stock_disponible': producto_bd.stock_actual,
                    'cantidad_solicitada': cantidad
                }

            # 3. Crear movimiento de salida
            movimiento = crud.crear_movimiento_inventario(
                db,
                producto_id=producto_bd.id_producto,
                usuario_id=usuario_id,
                tipo_movimiento='salida',
                cantidad=cantidad,
                observaciones=f'Retirado via chatbot: {cantidad} {producto} {marca} {modelo or ""}'.strip()
            )
            logger.info(f"Movimiento creado: ID={movimiento.id_movimiento}")

            # 4. Actualizar stock
            producto_actualizado = crud.actualizar_stock_producto(db, producto_bd.id_producto, cantidad, 'salida')
            logger.info(f"Stock actualizado: {producto_actualizado.stock_actual}")

            return {
                'exito': True,
                'mensaje': f"Retirados {cantidad} {producto} {marca} {modelo or ''}".strip(),
                'producto_id': producto_bd.id_producto,
                'movimiento_id': movimiento.id_movimiento,
                'stock_anterior': producto_bd.stock_actual,
                'stock_restante': producto_actualizado.stock_actual
            }

        except Exception as e:
            logger.error(f"Error en salida: {str(e)}")
            return {
                'exito': False,
                'error': str(e),
                'mensaje': "No se pudo retirar del inventario"
            }

    def _ejecutar_ajuste(self, db: Session, producto: str, marca: str, modelo: str, cantidad: int, usuario_id: int) -> Dict[str, Any]:
        """Ejecutar ajuste de stock - PERSISTE EN BD"""
        try:
            logger.info(f"Ejecutando AJUSTE: {producto} {marca} {modelo}, nueva cantidad: {cantidad}")

            # 1. Buscar o crear producto
            producto_bd = crud.buscar_o_crear_producto(db, producto, marca, modelo)

            stock_anterior = producto_bd.stock_actual
            diferencia = cantidad - stock_anterior

            logger.info(f"Producto: ID={producto_bd.id_producto}, stock anterior={stock_anterior}, diferencia={diferencia}")

            # 2. Crear movimiento de ajuste
            movimiento = crud.crear_movimiento_inventario(
                db,
                producto_id=producto_bd.id_producto,
                usuario_id=usuario_id,
                tipo_movimiento='ajuste',
                cantidad=abs(diferencia),
                observaciones=f'Ajuste via chatbot: {stock_anterior} → {cantidad} ({diferencia:+d})'
            )
            logger.info(f"Movimiento creado: ID={movimiento.id_movimiento}")

            # 3. Ajustar stock directamente
            producto_actualizado = crud.ajustar_stock_directo(db, producto_bd.id_producto, cantidad)
            logger.info(f"Stock ajustado: {producto_actualizado.stock_actual}")

            return {
                'exito': True,
                'mensaje': f"Stock de {producto} {marca} {modelo or ''} ajustado a {cantidad}".strip(),
                'producto_id': producto_bd.id_producto,
                'movimiento_id': movimiento.id_movimiento,
                'stock_anterior': stock_anterior,
                'stock_nuevo': cantidad,
                'diferencia': diferencia
            }

        except Exception as e:
            logger.error(f"Error en ajuste: {str(e)}")
            return {
                'exito': False,
                'error': str(e),
                'mensaje': "No se pudo ajustar el stock"
            }

    def _ejecutar_consulta(self, db: Session, producto: str, marca: str = None, modelo: str = None) -> Dict[str, Any]:
        """Ejecutar consulta de stock"""
        try:
            logger.info(f"Ejecutando CONSULTA: {producto} {marca or ''} {modelo or ''}")

            # Buscar productos que coincidan
            productos = crud.buscar_productos_similares(db, producto, marca, modelo)

            if not productos:
                return {
                    'exito': False,
                    'error': 'No encontrado',
                    'mensaje': f"No se encontraron productos que coincidan con: {producto} {marca or ''} {modelo or ''}".strip()
                }

            # Formatear información de stock
            info_stock = []
            stock_total = 0

            for prod in productos:
                # Obtener nombre de marca via relación
                marca_nombre = prod.marca.nombre_marca if hasattr(prod, 'marca') and prod.marca else 'Sin marca'
                info_stock.append({
                    'id_producto': prod.id_producto,
                    'producto': prod.nombre,
                    'marca': marca_nombre,
                    'modelo': prod.modelo or '',
                    'stock': prod.stock_actual,
                    'descripcion': f"{prod.nombre} {marca_nombre} {prod.modelo or ''} - {prod.stock_actual} unidades".strip()
                })
                stock_total += prod.stock_actual

            logger.info(f"Consulta exitosa: {len(productos)} productos, stock total: {stock_total}")

            return {
                'exito': True,
                'mensaje': f"Información de stock encontrada",
                'productos_encontrados': len(productos),
                'stock_total': stock_total,
                'detalle_productos': info_stock
            }

        except Exception as e:
            logger.error(f"Error en consulta: {str(e)}")
            return {
                'exito': False,
                'error': str(e),
                'mensaje': "No se pudo consultar el stock"
            }

    def _ejecutar_reporte(self, db: Session, producto: str = None, marca: str = None, modelo: str = None) -> Dict[str, Any]:
        """Ejecutar generación de reporte"""
        try:
            logger.info(f"Ejecutando REPORTE: {producto or 'todos'} {marca or ''} {modelo or ''}")

            # Generar reporte según filtros
            reporte_data = crud.generar_reporte_inventario(db, producto, marca, modelo)

            logger.info(f"Reporte generado: {reporte_data['total_productos']} productos")

            return {
                'exito': True,
                'mensaje': f"Reporte generado exitosamente",
                'reporte_id': reporte_data.get('id'),
                'total_productos': reporte_data.get('total_productos', 0),
                'valor_total': reporte_data.get('valor_total', 0),
                'filtros_aplicados': {
                    'producto': producto,
                    'marca': marca,
                    'modelo': modelo
                }
            }

        except Exception as e:
            logger.error(f"Error en reporte: {str(e)}")
            return {
                'exito': False,
                'error': str(e),
                'mensaje': "No se pudo generar el reporte"
            }

    def _generar_respuesta_exitosa(self, tipo_mov: str, producto: str, marca: str, modelo: str, cantidad: int, resultado_bd: Dict) -> str:
        """Generar respuesta amigable para operación exitosa"""

        producto_completo = f"{producto} {marca or ''} {modelo or ''}".strip()

        if tipo_mov == "entrada":
            stock_nuevo = resultado_bd.get('stock_nuevo', 'N/A')
            return f"✅ **¡Listo!** Agregué {cantidad} {producto_completo} al inventario.\n\n📦 **Stock actual**: {stock_nuevo} unidades"

        elif tipo_mov == "salida":
            stock_restante = resultado_bd.get('stock_restante', 'N/A')
            return f"✅ **¡Hecho!** Retiré {cantidad} {producto_completo} del inventario.\n\n📦 **Stock restante**: {stock_restante} unidades"

        elif tipo_mov == "ajuste":
            stock_anterior = resultado_bd.get('stock_anterior', 0)
            diferencia = resultado_bd.get('diferencia', 0)
            emoji_cambio = "📈" if diferencia > 0 else "📉" if diferencia < 0 else "🔄"
            return f"✅ **Stock ajustado** {emoji_cambio}\n\n🏷️ **Producto**: {producto_completo}\n📊 **Anterior**: {stock_anterior} → **Nuevo**: {cantidad}\n📈 **Cambio**: {diferencia:+d} unidades"

        elif tipo_mov == "consulta":
            productos_info = resultado_bd.get('detalle_productos', [])
            if len(productos_info) == 1:
                prod = productos_info[0]
                return f"📊 **Stock disponible**\n\n🏷️ **Producto**: {prod['descripcion']}"
            else:
                total = resultado_bd.get('stock_total', 0)
                count = len(productos_info)
                lista_productos = "\n".join([f"• {p['descripcion']}" for p in productos_info[:5]])
                mas_productos = f"\n• ... y {count-5} más" if count > 5 else ""
                return f"📊 **Stock encontrado** ({count} productos, {total} unidades total)\n\n{lista_productos}{mas_productos}"

        elif tipo_mov == "reporte":
            total_productos = resultado_bd.get('total_productos', 0)
            return f"📈 **¡Reporte generado!**\n\n📊 **Total productos**: {total_productos}\n🆔 **ID reporte**: {resultado_bd.get('reporte_id', 'N/A')}"

        else:
            return f"✅ Operación {tipo_mov} completada exitosamente para {producto_completo}"

    def _generar_respuesta_error(self, tipo_mov: str, producto: str, marca: str, modelo: str, cantidad: int, resultado_bd: Dict) -> str:
        """Generar respuesta amigable para errores"""

        error = resultado_bd.get('error', 'Error desconocido')
        mensaje = resultado_bd.get('mensaje', '')

        if 'stock insuficiente' in error.lower():
            stock_disponible = resultado_bd.get('stock_disponible', 0)
            cantidad_solicitada = resultado_bd.get('cantidad_solicitada', cantidad)
            return f"⚠️ **No hay suficiente stock**\n\n📦 **Disponible**: {stock_disponible} unidades\n🎯 **Solicitado**: {cantidad_solicitada} unidades\n\n💡 **Sugerencia**: Ajusta la cantidad o verifica el inventario"

        elif 'no encontrado' in error.lower():
            producto_completo = f"{producto} {marca or ''} {modelo or ''}".strip()
            return f"🔍 **Producto no encontrado**\n\n❌ No existe: {producto_completo}\n\n💡 **Sugerencias**:\n• Verifica la escritura\n• Usa 'consulta stock de {producto}' para ver productos similares\n• El producto se creará automáticamente al agregarlo"

        else:
            return f"❌ **Error**: {mensaje}\n\n**Detalle técnico**: {str(error)[:100]}\n\n🔧 Si el problema persiste, contacta al administrador del sistema"

# Instancia global del chatbot
chatbot = ChatbotInventario()

# Función simplificada para usar en endpoints
def procesar_mensaje_chatbot(mensaje: str, usuario_id: int = None) -> Dict[str, Any]:
    """
    Función principal para procesar mensajes del chatbot

    Usage:
        resultado = procesar_mensaje_chatbot("agrega 10 mouse logitech G203", usuario_id=1)
        print(resultado['respuesta_chatbot'])  # Respuesta para mostrar al usuario
    """
    return chatbot.procesar_mensaje_inventario(mensaje, usuario_id)

# ---------------------- EJEMPLOS DE USO ----------------------
if __name__ == "__main__":
    # Ejemplos de mensajes de chatbot
    mensajes_prueba = [
        "agrega 50 mouse logitech G203",
        "elimina 10 teclados razer blackwidow V3",
        "consulta stock de impresoras epson",
        "ajusta monitores asus TUF V27 a 25",
        "genera reporte de laptops dell",
    ]

    print("=== PRUEBAS DEL CHATBOT DE INVENTARIO (PERSISTE EN BD) ===\n")

    for mensaje in mensajes_prueba:
        print(f"👤 Usuario: {mensaje}")
        resultado = procesar_mensaje_chatbot(mensaje, usuario_id=1)
        print(f"🤖 Chatbot: {resultado['respuesta_chatbot']}")
        print(f"✅ Éxito: {resultado['exito']}")
        if 'detalles_operacion' in resultado and resultado['detalles_operacion'].get('movimiento_id'):
            print(f"🔄 Movimiento BD: {resultado['detalles_operacion']['movimiento_id']}")
        print("-" * 80)