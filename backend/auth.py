from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional
import os

from database import get_db
from models import Proveedor

SECRET_KEY = os.getenv("SECRET_KEY", "tu-clave-secreta-aqui")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    ruc: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    proveedor: dict

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    token = parts[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        ruc: str = payload.get("ruc")
        if ruc is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado o inválido")
    return {"ruc": ruc}

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == request.ruc).first()
        if not proveedor:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="RUC o contraseña incorrectos")
        if not verify_password(request.password, proveedor.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="RUC o contraseña incorrectos")
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data={"ruc": proveedor.ruc}, expires_delta=access_token_expires)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "proveedor": {"id": proveedor.id, "ruc": proveedor.ruc, "razon_social": proveedor.razon_social, "email": proveedor.email}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"mensaje": "Sesión cerrada exitosamente"}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        ruc = current_user.get("ruc")
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == ruc).first()
        if not proveedor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")
        return {"id": proveedor.id, "ruc": proveedor.ruc, "razon_social": proveedor.razon_social}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
