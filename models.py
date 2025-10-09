from sqlalchemy import Column, Integer, String, Enum as SAEnum, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class RolEnum(enum.Enum):
    administrador = "administrador"
    operador = "operador"
    auditor = "auditor"

class TipoMovimientoEnum(enum.Enum):
    entrada = "entrada"
    salida = "salida"
    ajuste = "ajuste"

class Categoria(Base):
    __tablename__ = "categoria"
    id_categoria = Column(Integer, primary_key=True, index=True)
    nombre_categoria = Column(String(100), nullable=False)
    descripcion = Column(String(200), nullable=True)

    productos = relationship("Producto", back_populates="categoria")

class Marca(Base):
    __tablename__ = "marca"
    id_marca = Column(Integer, primary_key=True, index=True)
    nombre_marca = Column(String(100), nullable=False, unique=True)

    productos = relationship("Producto", back_populates="marca")

class Producto(Base):
    __tablename__ = "producto"
    id_producto = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    modelo = Column(String(100), nullable=True)
    descripcion = Column(String(200), nullable=True)
    id_categoria = Column(Integer, ForeignKey("categoria.id_categoria"), nullable=True)
    id_marca = Column(Integer, ForeignKey("marca.id_marca"), nullable=True)
    stock_actual = Column(Integer, default=0)
    stock_minimo = Column(Integer, default=0)
    fecha_registro = Column(DateTime, default=datetime.utcnow)

    categoria = relationship("Categoria", back_populates="productos")
    marca = relationship("Marca", back_populates="productos")

    movimientos = relationship(
        "MovimientoInventario",
        back_populates="producto",
        foreign_keys="MovimientoInventario.id_producto",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class Usuario(Base):
    __tablename__ = "usuario"
    id_usuario = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    rol = Column(SAEnum(RolEnum), default=RolEnum.operador)
    correo = Column(String(150), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)

    movimientos = relationship(
        "MovimientoInventario",
        back_populates="usuario",
        foreign_keys="MovimientoInventario.id_usuario",
    )

class MovimientoInventario(Base):
    __tablename__ = "movimiento_inventario"
    id_movimiento = Column(Integer, primary_key=True, index=True, autoincrement=True)
    id_producto = Column(Integer, ForeignKey("producto.id_producto", ondelete="RESTRICT"), nullable=False)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario", ondelete="RESTRICT"), nullable=False)
    tipo_movimiento = Column(SAEnum(TipoMovimientoEnum), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_movimiento = Column(DateTime, default=datetime.utcnow)
    observaciones = Column(Text, nullable=True)  # en BD es 'observaciones'

    producto = relationship(
        "Producto",
        back_populates="movimientos",
        foreign_keys=[id_producto],
    )
    usuario = relationship(
        "Usuario",
        back_populates="movimientos",
        foreign_keys=[id_usuario],
    )