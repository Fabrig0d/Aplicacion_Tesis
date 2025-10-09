from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
import models, schemas, crud
from database import SessionLocal, engine
from auth import authenticate_user, create_access_token, require_role
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

app = FastAPI(title="API Inventario (Demo Ligera)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ChatbotRequest(BaseModel):
    mensaje: str
    usuario_id: Optional[int] = None

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    token = create_access_token(data={"sub": user.correo})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/chatbot/inventario")
def chatbot(req: ChatbotRequest, current_user=Depends(require_role(["administrador","operador"]))):
    # Fallback ligero sin PLN pesado
    return {
        "exito": True,
        "respuesta_chatbot": f"✅ Demo: '{req.mensaje}' procesado para usuario {current_user.correo}",
        "confianza": 0.99,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/productos/")
def productos(db: Session = Depends(get_db), current_user=Depends(require_role(["administrador","operador"]))):
    return crud.get_productos(db)

@app.get("/health")
def health():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database": "disconnected", "error": str(e)}
    finally:
        db.close()