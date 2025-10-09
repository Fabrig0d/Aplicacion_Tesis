from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from jose import jwt, JWTError

# Configuración de JWT
SECRET_KEY = "F@br1zi0xd"  # 🔒 cámbiala por algo más seguro
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Seguridad para contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Funciones auxiliares
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(db: Session, correo: str, password: str):
    user = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
    if not user or not verify_password(password, user.password_hash):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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
    user = db.query(models.Usuario).filter(models.Usuario.correo == correo).first()
    if user is None:
        raise credentials_exception
    return user

def require_role(required_roles: list[str]):
    """
    Verifica que el usuario actual tenga alguno de los roles requeridos.
    - Soporta roles como Enum o string.
    - Normaliza a minúsculas.
    - Soporta alias: 'usuario' ≈ 'operador', 'admin' ≈ 'administrador'
    """
    alias_map = {
        "admin": "administrador",
        "administrador": "administrador",
        "usuario": "operador",
        "operador": "operador",
        "auditor": "auditor",
    }

    normalized_required = set(
        alias_map.get(str(r).lower().strip(), str(r).lower().strip())
        for r in required_roles
    )

    def to_role_str(role_obj) -> str:
        # Acepta Enum ('RolEnum.administrador'), strings y otros tipos
        try:
            # Si es Enum, usa .value si existe
            value = getattr(role_obj, "value", role_obj)
            return str(value).lower().strip()
        except Exception:
            return str(role_obj).lower().strip()

    def role_checker(current_user: models.Usuario = Depends(get_current_user)):
        raw_role = current_user.rol
        user_role_str = to_role_str(raw_role)
        normalized_user_role = alias_map.get(user_role_str, user_role_str)

        # Debug opcional:
        # print(f"[AUTH] raw='{raw_role}' parsed='{user_role_str}' norm='{normalized_user_role}' req={normalized_required}")

        if normalized_user_role not in normalized_required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta acción"
            )
        return current_user

    return role_checker
