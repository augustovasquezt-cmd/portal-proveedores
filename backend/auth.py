from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
from database import get_db
from models import Proveedor

router = APIRouter(prefix="/auth", tags=["autenticacion"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "portal-proveedores-secret-2026"
ALGORITHM = "HS256"

class LoginRequest(BaseModel):
    ruc: str
    password: str

class RegisterRequest(BaseModel):
    ruc: str
    razon_social: str
    email: str
    password: str

def crear_token(data: dict):
    expira = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode({**data, "exp": expira}, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    proveedor = db.query(Proveedor).filter(Proveedor.ruc == req.ruc).first()
    if not proveedor or not pwd_context.verify(req.password, proveedor.password_hash):
        raise HTTPException(status_code=401, detail="RUC o contrasena incorrectos")
    token = crear_token({"sub": proveedor.id, "ruc": proveedor.ruc})
    return {"token": token, "ruc": proveedor.ruc, "razon_social": proveedor.razon_social}

@router.post("/registro")
def registro(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(Proveedor).filter(Proveedor.ruc == req.ruc).first():
        raise HTTPException(status_code=400, detail="RUC ya registrado")
    proveedor = Proveedor(
        ruc=req.ruc,
        razon_social=req.razon_social,
        email=req.email,
        password_hash=pwd_context.hash(req.password)
    )
    db.add(proveedor)
    db.commit()
    db.refresh(proveedor)
    return {"mensaje": "Proveedor registrado", "id": proveedor.id}