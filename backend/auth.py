from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
import os

from database import get_db
from models import Cliente, Proveedor, ProveedorCliente, UsuarioInterno

SECRET_KEY = os.getenv("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("Define SECRET_KEY en el .env con un secreto aleatorio de al menos 32 caracteres.")
ALGORITHM = "HS256"
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
except ValueError as exc:
    raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES debe ser un número entero.") from exc
if not 5 <= ACCESS_TOKEN_EXPIRE_MINUTES <= 1440:
    raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES debe estar entre 5 y 1440.")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")

class LoginRequest(BaseModel):
    ruc: Optional[str] = None
    usuario: Optional[str] = None
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    rol: str = "proveedor"
    proveedor: Optional[dict] = None
    usuario: Optional[dict] = None
    debe_cambiar_password: bool = False
    cliente_id: Optional[str] = None
    clientes: list[dict] = Field(default_factory=list)
    requiere_seleccion_cliente: bool = False

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc).replace(tzinfo=None) + expires_delta
    else:
        expire = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decodificar_token(credentials: Optional[HTTPAuthorizationCredentials]) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token Bearer requerido")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        ruc: str = payload.get("ruc")
        role = payload.get("rol", "proveedor" if ruc else None)
        if role not in {"proveedor", "cuentas_por_pagar", "administrador", "administrador_ivs"} or (role == "proveedor" and ruc is None):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado o inválido")
    return {"ruc": ruc, "rol": role, "usuario_id": payload.get("usuario_id"), "nombre": payload.get("nombre"), "usuario": payload.get("usuario"), "cliente_id": payload.get("cliente_id"), "debe_cambiar_password": bool(payload.get("debe_cambiar_password", False))}


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme), db: Session = Depends(get_db)) -> dict:
    identity = decodificar_token(credentials)
    if identity['rol'] == 'proveedor':
        account = db.query(Proveedor).filter(Proveedor.ruc == identity['ruc'], Proveedor.activo.is_(True)).first()
    else:
        account = db.query(UsuarioInterno).filter(
            UsuarioInterno.id == identity['usuario_id'], UsuarioInterno.activo.is_(True),
            UsuarioInterno.rol == identity['rol'],
        ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La cuenta está desactivada o ya no existe")
    if account.cambio_password_requerido:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Debes cambiar tu contraseña antes de continuar")
    if identity['rol'] == 'proveedor':
        tenant_id = identity.get('cliente_id')
        if tenant_id:
            membership = db.query(ProveedorCliente).join(Cliente, Cliente.id == ProveedorCliente.cliente_id).filter(
                ProveedorCliente.proveedor_id == account.id, ProveedorCliente.cliente_id == tenant_id,
                ProveedorCliente.activo.is_(True), Cliente.activo.is_(True),
            ).first()
            if not membership:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="El acceso de proveedor a este cliente ya no está activo")
    elif identity['rol'] != 'administrador_ivs':
        identity['cliente_id'] = account.cliente_id
        if not account.cliente_id or not db.query(Cliente.id).filter(Cliente.id == account.cliente_id, Cliente.activo.is_(True)).first():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La cuenta no pertenece a un cliente activo")
    return identity

async def get_current_tenant_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get('rol') == 'administrador_ivs':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Esta operación requiere una cuenta de cliente o proveedor.')
    if not current_user.get('cliente_id'):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Selecciona el cliente para continuar.')
    return current_user

async def get_current_provider_user(current_user: dict = Depends(get_current_tenant_user)) -> dict:
    if current_user.get('rol') != 'proveedor':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Se requiere una cuenta de proveedor.')
    return current_user

async def get_current_ap_user(current_user: dict = Depends(get_current_tenant_user), db: Session = Depends(get_db)) -> dict:
    if current_user.get("rol") != "cuentas_por_pagar":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere el perfil de cuentas por pagar")
    account = db.query(UsuarioInterno).filter(UsuarioInterno.id == current_user.get("usuario_id"), UsuarioInterno.activo.is_(True), UsuarioInterno.rol == "cuentas_por_pagar").first()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La cuenta interna está desactivada o ya no existe")
    return current_user


async def get_current_admin_user(current_user: dict = Depends(get_current_tenant_user), db: Session = Depends(get_db)) -> dict:
    if current_user.get("rol") != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere el perfil de administrador de la empresa")
    account = db.query(UsuarioInterno).filter(
        UsuarioInterno.id == current_user.get("usuario_id"), UsuarioInterno.activo.is_(True), UsuarioInterno.rol == "administrador",
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La cuenta administrativa está desactivada o ya no existe")
    return current_user

async def get_current_ivs_admin_user(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if current_user.get('rol') != 'administrador_ivs':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Se requiere una cuenta de administración IVS.')
    account = db.query(UsuarioInterno).filter(
        UsuarioInterno.id == current_user.get('usuario_id'), UsuarioInterno.activo.is_(True),
        UsuarioInterno.rol == 'administrador_ivs', UsuarioInterno.cliente_id.is_(None),
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='La cuenta de IVS está desactivada o ya no existe.')
    return current_user

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        if request.usuario:
            if request.ruc:
                raise HTTPException(status_code=422, detail="Envía RUC o usuario corporativo, no ambos")
            internal = db.query(UsuarioInterno).filter(UsuarioInterno.usuario == request.usuario.strip().lower(), UsuarioInterno.activo.is_(True)).first()
            if not internal or internal.rol not in {"cuentas_por_pagar", "administrador", "administrador_ivs"} or not verify_password(request.password, internal.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")
            if internal.rol != 'administrador_ivs' and (not internal.cliente_id or not db.query(Cliente.id).filter(Cliente.id == internal.cliente_id, Cliente.activo.is_(True)).first()):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La cuenta no pertenece a un cliente activo")
            claims = {"rol": internal.rol, "usuario_id": internal.id, "usuario": internal.usuario, "nombre": internal.nombre, "cliente_id": internal.cliente_id, "debe_cambiar_password": internal.cambio_password_requerido}
            access_token = create_access_token(data=claims, expires_delta=access_token_expires)
            return {"access_token": access_token, "token_type": "bearer", "rol": internal.rol, "cliente_id": internal.cliente_id, "debe_cambiar_password": internal.cambio_password_requerido, "usuario": {"id": internal.id, "usuario": internal.usuario, "nombre": internal.nombre, "rol": internal.rol, "cliente_id": internal.cliente_id}}
        if not request.ruc or request.usuario:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == request.ruc).first()
        if not proveedor or not proveedor.activo or not verify_password(request.password, proveedor.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")
        memberships = db.query(ProveedorCliente, Cliente).join(Cliente, Cliente.id == ProveedorCliente.cliente_id).filter(
            ProveedorCliente.proveedor_id == proveedor.id, ProveedorCliente.activo.is_(True), Cliente.activo.is_(True),
        ).order_by(Cliente.nombre.asc()).all()
        if not memberships:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tu RUC aún no tiene acceso a un cliente del portal.")
        clients = [{'id': membership.cliente_id, 'codigo': client.codigo, 'nombre': client.nombre} for membership, client in memberships]
        selected_tenant = clients[0]['id'] if len(clients) == 1 else None
        claims = {"ruc": proveedor.ruc, "rol": "proveedor", "cliente_id": selected_tenant, "debe_cambiar_password": proveedor.cambio_password_requerido}
        access_token = create_access_token(data=claims, expires_delta=access_token_expires)
        return {"access_token": access_token, "token_type": "bearer", "rol": "proveedor", "cliente_id": selected_tenant, "clientes": clients, "requiere_seleccion_cliente": len(clients) > 1, "debe_cambiar_password": proveedor.cambio_password_requerido, "proveedor": {"id": proveedor.id, "ruc": proveedor.ruc, "razon_social": proveedor.razon_social, "email": proveedor.email}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo completar el inicio de sesión") from e

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"mensaje": "Sesión cerrada exitosamente"}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        if current_user.get("rol") in {"cuentas_por_pagar", "administrador", "administrador_ivs"}:
            internal = db.query(UsuarioInterno).filter(UsuarioInterno.id == current_user.get("usuario_id"), UsuarioInterno.activo.is_(True)).first()
            if not internal:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario interno no encontrado")
            return {"id": internal.id, "usuario": internal.usuario, "nombre": internal.nombre, "rol": internal.rol, "cliente_id": internal.cliente_id}
        ruc = current_user.get("ruc")
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == ruc).first()
        if not proveedor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")
        memberships = db.query(ProveedorCliente, Cliente).join(Cliente, Cliente.id == ProveedorCliente.cliente_id).filter(ProveedorCliente.proveedor_id == proveedor.id, ProveedorCliente.activo.is_(True), Cliente.activo.is_(True)).all()
        return {"id": proveedor.id, "ruc": proveedor.ruc, "razon_social": proveedor.razon_social, "cliente_id": current_user.get('cliente_id'), "clientes": [{'id': membership.cliente_id, 'codigo': client.codigo, 'nombre': client.nombre} for membership, client in memberships]}
    except HTTPException:
        raise
    except Exception as e:
        # Keep internal exception details in server logs, never in API responses.
        import logging
        logging.getLogger(__name__).exception("No se pudo obtener el usuario autenticado")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo obtener el usuario autenticado") from e


@router.post('/seleccionar-cliente', summary='Seleccionar cliente para proveedor con varias membresías')
async def seleccionar_cliente(cliente_id: str, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme), db: Session = Depends(get_db)):
    identity = decodificar_token(credentials)
    if identity.get('rol') != 'proveedor':
        raise HTTPException(status_code=403, detail='Solo el proveedor puede seleccionar un cliente.')
    supplier = db.query(Proveedor).filter(Proveedor.ruc == identity['ruc'], Proveedor.activo.is_(True)).first()
    if not supplier:
        raise HTTPException(status_code=401, detail='La cuenta de proveedor está desactivada o ya no existe.')
    membership = db.query(ProveedorCliente).join(Cliente, Cliente.id == ProveedorCliente.cliente_id).filter(
        ProveedorCliente.proveedor_id == supplier.id, ProveedorCliente.cliente_id == cliente_id,
        ProveedorCliente.activo.is_(True), Cliente.activo.is_(True),
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail='No tienes acceso a ese cliente.')
    token = create_access_token(data={'ruc': supplier.ruc, 'rol': 'proveedor', 'cliente_id': cliente_id, 'debe_cambiar_password': supplier.cambio_password_requerido}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {'access_token': token, 'token_type': 'bearer', 'rol': 'proveedor', 'cliente_id': cliente_id, 'debe_cambiar_password': supplier.cambio_password_requerido}


class CambioPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


@router.post('/cambiar-password', summary='Cambiar contraseña propia')
async def cambiar_password(request: CambioPasswordRequest, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme), db: Session = Depends(get_db)):
    identity = decodificar_token(credentials)
    if len(request.password_nueva) < 12:
        raise HTTPException(status_code=422, detail='La nueva contraseña debe tener al menos 12 caracteres')
    if request.password_actual == request.password_nueva:
        raise HTTPException(status_code=422, detail='La nueva contraseña debe ser diferente a la actual')
    if identity['rol'] == 'proveedor':
        account = db.query(Proveedor).filter(Proveedor.ruc == identity['ruc'], Proveedor.activo.is_(True)).first()
    else:
        account = db.query(UsuarioInterno).filter(UsuarioInterno.id == identity['usuario_id'], UsuarioInterno.activo.is_(True), UsuarioInterno.rol == identity['rol']).first()
    if not account or not verify_password(request.password_actual, account.password_hash):
        raise HTTPException(status_code=401, detail='La contraseña actual es incorrecta')
    account.password_hash = get_password_hash(request.password_nueva)
    account.cambio_password_requerido = False
    db.commit()
    claims = dict(ruc=account.ruc, rol='proveedor', cliente_id=identity.get('cliente_id'), debe_cambiar_password=False) if identity['rol'] == 'proveedor' else dict(rol=account.rol, usuario_id=account.id, usuario=account.usuario, nombre=account.nombre, cliente_id=account.cliente_id, debe_cambiar_password=False)
    token = create_access_token(data=claims, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {'access_token': token, 'token_type': 'bearer', 'rol': identity['rol'], 'debe_cambiar_password': False}
