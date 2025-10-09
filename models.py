# models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.sql import func
from database import Base
import enum

# ----- ENUMS -----
class RolUsuario(enum.Enum):
    administrador = "administrador"
    operador = "operador"
    auditor = "auditor"


class RolEnum(enum.Enum):
    administrador = "administrador"
    operador = "operador"
    auditor = "auditor"


class TipoMovimientoEnum(enum.Enum):
    entrada = "entrada"
    salida = "salida"
    ajuste = "ajuste"


# ---------- Categoría ----------
class Categoria(Base):
    __tablename__ = "categoria"

    id_categoria = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre_categoria = Column(String(100), nullable=False)
    descripcion = Column(String(200))

    productos = relationship("Producto", back_populates="categoria")


# ---------- Marca ----------
class Marca(Base):
    __tablename__ = "marca"

    id_marca = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre_marca = Column(String(100), nullable=False)

    productos = relationship("Producto", back_populates="marca")


# ---------- Usuario ----------
class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    rol = Column(Enum(RolEnum), default=RolEnum.operador)
    correo = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    movimientos = relationship("MovimientoInventario", back_populates="usuario")
    reportes = relationship("Reporte", back_populates="usuario")


# ---------- Producto ----------
class Producto(Base):
    __tablename__ = "producto"

    id_producto = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    modelo = Column(String(100))
    descripcion = Column(String(200))
    id_categoria = Column(Integer, ForeignKey("categoria.id_categoria"))
    id_marca = Column(Integer, ForeignKey("marca.id_marca"))
    stock_actual = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=0)
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())

    categoria = relationship("Categoria", back_populates="productos")
    marca = relationship("Marca", back_populates="productos")
    movimientos = relationship("MovimientoInventario", back_populates="producto")


# ---------- Movimiento de Inventario ----------
class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"

    id_movimiento = Column(Integer, primary_key=True, index=True, autoincrement=True)
    id_producto = Column(Integer, ForeignKey("producto.id_producto"), nullable=False)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False)
    tipo_movimiento = Column(Enum(TipoMovimientoEnum), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_movimiento = Column(DateTime(timezone=True), server_default=func.now())
    observaciones = Column(Text)

    producto = relationship("Producto", back_populates="movimientos")
    usuario = relationship("Usuario", back_populates="movimientos")


# ---------- Reporte ----------
class Reporte(Base):
    __tablename__ = "reporte"

    id_reporte = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tipo_reporte = Column(String(100), nullable=False)
    fecha_generacion = Column(DateTime(timezone=True), server_default=func.now())
    detalle = Column(JSON)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"))

    usuario = relationship("Usuario", back_populates="reportes")