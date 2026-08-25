# schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

# ----- ENUMS -----
class RolUsuario(str, Enum):
    administrador = "administrador"
    operador = "operador"
    auditor = "auditor"

class TipoMovimiento(str, Enum):
    entrada = "entrada"
    salida = "salida"
    ajuste = "ajuste"


# ---------- Categoría ----------
class CategoriaBase(BaseModel):
    nombre_categoria: str
    descripcion: Optional[str] = None

class CategoriaCreate(CategoriaBase):
    pass

class Categoria(CategoriaBase):
    id_categoria: int

    class Config:
        from_attributes = True


# ---------- Marca ----------
class MarcaBase(BaseModel):
    nombre_marca: str

class MarcaCreate(MarcaBase):
    pass

class Marca(MarcaBase):
    id_marca: int

    class Config:
        from_attributes = True


# ---------- Usuario ----------
class UsuarioBase(BaseModel):
    nombre: str
    apellido: str
    correo: EmailStr
    rol: Optional[str] = "operador"

class UsuarioCreate(UsuarioBase):
    password: str

class Usuario(UsuarioBase):
    id_usuario: int

    class Config:
        from_attributes = True
        
class UsuarioResponse(UsuarioBase):
    id_usuario: int
    fecha_registro: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Producto ----------
class ProductoBase(BaseModel):
    nombre: str
    modelo: Optional[str] = None
    descripcion: Optional[str] = None
    id_categoria: Optional[int] = None
    id_marca: Optional[int] = None
    stock_actual: Optional[int] = 0
    stock_minimo: Optional[int] = 0

class ProductoCreate(ProductoBase):
    pass

class Producto(ProductoBase):
    id_producto: int
    fecha_registro: datetime

    class Config:
        from_attributes = True


# ---------- Movimiento de Inventario ----------
class MovimientoInventarioBase(BaseModel):
    id_producto: int
    id_usuario: int
    tipo_movimiento: str
    cantidad: int
    observaciones: Optional[str] = None

class MovimientoInventarioCreate(MovimientoInventarioBase):
    pass

class MovimientoInventario(MovimientoInventarioBase):
    id_movimiento: int
    fecha_movimiento: datetime

    class Config:
        from_attributes = True


# ---------- Reporte ----------
class ReporteBase(BaseModel):
    tipo_reporte: str
    detalle: Optional[dict] = None
    id_usuario: Optional[int] = None

class ReporteCreate(ReporteBase):
    pass

class Reporte(ReporteBase):
    id_reporte: int
    fecha_generacion: datetime

    class Config:
        from_attributes = True


class PLNRequest(BaseModel):
    texto: str   # Texto de entrada para analizar o transformar


class PLNResponse(BaseModel):
    resultado: str   # Resultado generado por el modelo de PLN
