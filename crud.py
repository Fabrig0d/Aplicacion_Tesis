import schemas
from sqlalchemy.orm import Session
from sqlalchemy import and_
import models
from auth import get_password_hash
from typing import List, Optional

def buscar_o_crear_producto(db: Session, nombre: str, marca_nombre: str, modelo: str = None) -> models.Producto:
    """
    Busca un producto exacto o lo crea si no existe
    Funciona con FK a tabla Marca
    """
    modelo_val = modelo or ""

    # Buscar producto con JOIN a Marca
    producto = db.query(models.Producto)\
        .join(models.Marca, models.Producto.id_marca == models.Marca.id_marca)\
        .filter(
            and_(
                models.Producto.nombre == nombre,
                models.Producto.modelo == modelo_val,
                models.Marca.nombre_marca == marca_nombre  # Comparar en tabla Marca
            )
        ).first()

    if not producto:
        # Buscar o crear la marca primero
        marca = db.query(models.Marca).filter(models.Marca.nombre_marca == marca_nombre).first()
        if not marca:
            marca = models.Marca(nombre_marca=marca_nombre)
            db.add(marca)
            db.commit()
            db.refresh(marca)

        # Buscar categoría (mapear por nombre de producto)
        categoria_map = {
            'mouse': 1, 'teclado': 1, 'impresora': 1,  # Periféricos
            'monitor': 4,                               # Monitores  
            'laptop': 3,                                # Laptops
            'ssd': 5, 'hdd': 5                         # Almacenamiento
        }
        id_categoria = categoria_map.get(nombre.lower(), 1)  # Default: Periféricos

        # Crear nuevo producto
        producto = models.Producto(
            nombre=nombre,
            modelo=modelo_val,
            descripcion=f"{nombre} {marca_nombre} {modelo_val}".strip(),
            id_categoria=id_categoria,
            id_marca=marca.id_marca,  # Usar el ID de la marca
            stock_actual=0,
            stock_minimo=1
        )
        db.add(producto)
        db.commit()
        db.refresh(producto)

    return producto

def buscar_producto_exacto(db: Session, nombre: str, marca_nombre: str, modelo: str = None) -> Optional[models.Producto]:
    """
    Busca un producto exacto (no lo crea si no existe)
    """
    modelo_val = modelo or ""

    return db.query(models.Producto)\
        .join(models.Marca, models.Producto.id_marca == models.Marca.id_marca)\
        .filter(
            and_(
                models.Producto.nombre == nombre,
                models.Producto.modelo == modelo_val,
                models.Marca.nombre_marca == marca_nombre
            )
        ).first()

def buscar_productos_similares(db: Session, nombre: str, marca_nombre: str = None, modelo: str = None) -> List[models.Producto]:
    """
    Busca productos similares usando filtros flexibles
    """
    query = db.query(models.Producto).join(models.Marca, models.Producto.id_marca == models.Marca.id_marca)

    # Filtro por nombre (siempre requerido)
    query = query.filter(models.Producto.nombre.ilike(f"%{nombre}%"))

    # Filtros opcionales
    if marca_nombre:
        query = query.filter(models.Marca.nombre_marca.ilike(f"%{marca_nombre}%"))

    if modelo:
        query = query.filter(models.Producto.modelo.ilike(f"%{modelo}%"))

    return query.all()

def actualizar_stock_producto(db: Session, producto_id: int, cantidad: int, tipo_movimiento: str):
    """
    Actualiza el stock de un producto según el tipo de movimiento
    """
    producto = db.query(models.Producto).filter(models.Producto.id_producto == producto_id).first()

    if not producto:
        raise ValueError(f"Producto con ID {producto_id} no encontrado")

    if tipo_movimiento == 'entrada':
        producto.stock_actual += cantidad
    elif tipo_movimiento == 'salida':
        if producto.stock_actual < cantidad:
            raise ValueError(f"Stock insuficiente. Disponible: {producto.stock_actual}, solicitado: {cantidad}")
        producto.stock_actual -= cantidad
    else:
        raise ValueError(f"Tipo de movimiento inválido: {tipo_movimiento}")

    db.commit()
    db.refresh(producto)
    return producto

def ajustar_stock_directo(db: Session, producto_id: int, nuevo_stock: int):
    """
    Ajusta el stock directamente a una cantidad específica
    """
    producto = db.query(models.Producto).filter(models.Producto.id_producto == producto_id).first()

    if not producto:
        raise ValueError(f"Producto con ID {producto_id} no encontrado")

    producto.stock_actual = nuevo_stock
    db.commit()
    db.refresh(producto)
    return producto

def generar_reporte_inventario(db: Session, nombre_producto: str = None, marca_nombre: str = None, modelo: str = None):
    """
    Genera un reporte de inventario con filtros opcionales
    """
    query = db.query(models.Producto).join(models.Marca, models.Producto.id_marca == models.Marca.id_marca)

    if nombre_producto:
        query = query.filter(models.Producto.nombre.ilike(f"%{nombre_producto}%"))
    if marca_nombre:
        query = query.filter(models.Marca.nombre_marca.ilike(f"%{marca_nombre}%"))
    if modelo:
        query = query.filter(models.Producto.modelo.ilike(f"%{modelo}%"))

    productos = query.all()

    total_productos = len(productos)
    # Asumir precio_unitario como campo opcional en Producto
    valor_total = sum(p.stock_actual * getattr(p, 'precio_unitario', 0.0) for p in productos)

    return {
        'id': f'report_{total_productos}_products',
        'total_productos': total_productos,
        'valor_total': valor_total,
        'productos': productos
    }

# Función para crear movimiento (ajustar a tu esquema)
def crear_movimiento_inventario(db: Session, producto_id: int, usuario_id: int, tipo_movimiento: str, cantidad: int, observaciones: str = None):
    """
    Crea un movimiento de inventario
    """
    movimiento = models.MovimientoInventario(
        id_producto=producto_id,
        id_usuario=usuario_id,
        tipo_movimiento=tipo_movimiento,
        cantidad=cantidad,
        observaciones=observaciones or f"Movimiento {tipo_movimiento} via chatbot"
    )

    db.add(movimiento)
    db.commit()
    db.refresh(movimiento)
    return movimiento

def create_usuario(db: Session, usuario: schemas.UsuarioCreate):
    password_hash = get_password_hash(usuario.password)
    
    db_usuario = models.Usuario(
        correo=usuario.correo,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        rol=usuario.rol,
        telefono=usuario.telefono,
        password_hash=password_hash # Ajusta al nombre exacto de la columna en tu modelo models.Usuario
    )
    
    db.add(db_usuario)
    db.commit()
    db.refresh(db_usuario)
    return db_usuario

def get_usuario_by_correo(db: Session, correo: str):
    return db.query(models.Usuario).filter(models.Usuario.correo == correo).first()