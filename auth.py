from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database import get_db_session
import models

# ================== CONFIG JWT ==================
# Cambiar en producción: usa variable de entorno
SECRET_KEY = "F@br1zi0xd"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# ================== SECURITY ==================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ================== HELPERS ==================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def authenticate_user(db: Session, correo: str, password: str):
    """
    Autentica por correo y password.
    Devuelve el usuario o False si no coincide.
    """
    user = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
    if not user or not verify_password(password, user.password_hash):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un token JWT con expiración.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ================== CURRENT USER ==================
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        correo: str = payload.get("sub")
        if correo is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Cargar y aplanar ANTES de cerrar la sesión
    with get_db_session() as db:
        user = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
        if user is None:
            raise credentials_exception

        # Campos primitivos; evita lazy loads tras cerrar sesión
        current_user = {
            "id_usuario": user.id_usuario,
            "correo": user.correo,
            "nombre": user.nombre,
            "apellido": user.apellido,
            "rol": getattr(user.rol, "value", str(user.rol)),  # Enum -> str
            "telefono": getattr(user, 'telefono', None),
            "fecha_registro": getattr(user, 'fecha_registro', None),
        }
        return current_user

# ================== ROLE CHECKER ==================
def require_role(required_roles: List[str]):
    alias_map = {
        "admin": "administrador",
        "administrador": "administrador",
        "usuario": "operador",
        "operador": "operador",
        "auditor": "auditor",
    }
    normalized_required = {
        alias_map.get(str(r).lower().strip(), str(r).lower().strip())
        for r in required_roles
    }

    def to_role_str(role_obj) -> str:
        try:
            value = getattr(role_obj, "value", role_obj)
            return str(value).lower().strip()
        except Exception:
            return str(role_obj).lower().strip()

    def role_checker(current_user = Depends(get_current_user)):
        # current_user puede ser dict o modelo
        raw_role = current_user.get("rol") if isinstance(current_user, dict) else getattr(current_user, "rol", "")
        user_role_str = to_role_str(raw_role)
        normalized_user_role = alias_map.get(user_role_str, user_role_str)
        if normalized_user_role not in normalized_required:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos")
        return current_user

    return role_checker