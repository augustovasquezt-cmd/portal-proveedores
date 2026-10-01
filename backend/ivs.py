"""Provisionamiento de tenants, cupos y sociedades bajo control de IVS."""
import json
import hashlib
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from auth import get_current_ivs_admin_user, get_password_hash
from database import get_db
from models import Cliente, RegistroAuditoria, Sociedad, UsuarioInterno

router = APIRouter(prefix='/ivs/clientes', tags=['administración IVS'])


class ClienteEntrada(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codigo: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{2,59}$')
    nombre: str = Field(min_length=2, max_length=200)
    ruc_principal: str = Field(pattern=r'^\d{11}$')
    razon_social_principal: str = Field(min_length=2, max_length=200)
    codigo_sap_principal: str | None = Field(default=None, max_length=20)
    max_administradores: int = Field(default=1, ge=1, le=100)
    max_cuentas_por_pagar: int = Field(default=5, ge=0, le=10000)
    max_proveedores: int = Field(default=50, ge=0, le=100000)
    max_sociedades: int = Field(default=10, ge=1, le=1000)

    @field_validator('codigo', mode='before')
    @classmethod
    def normalizar_codigo(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Cuotas(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_administradores: int = Field(ge=1, le=100)
    max_cuentas_por_pagar: int = Field(ge=0, le=10000)
    max_proveedores: int = Field(ge=0, le=100000)
    max_sociedades: int = Field(ge=1, le=1000)


class ClienteActualizacion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    codigo: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{2,59}$')
    nombre: str = Field(min_length=2, max_length=200)

    @field_validator('codigo', mode='before')
    @classmethod
    def normalizar_codigo(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class SociedadEntrada(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ruc: str = Field(pattern=r'^\d{11}$')
    razon_social: str = Field(min_length=2, max_length=200)
    codigo_sap: str | None = Field(default=None, max_length=20)


class EstadoSociedad(BaseModel):
    model_config = ConfigDict(extra='forbid')
    activo: bool


class AdministradorEntrada(BaseModel):
    model_config = ConfigDict(extra='forbid')
    usuario: EmailStr
    nombre: str = Field(min_length=2, max_length=200)


def _audit(db, actor, cliente_id, action, target_type, target_id, details=None):
    db.add(RegistroAuditoria(id=str(uuid4()), actor_usuario_id=actor['usuario_id'], actor_usuario=actor['usuario'], cliente_id=cliente_id, accion=action, tipo_objetivo=target_type, objetivo_id=target_id, detalles=json.dumps(details or {}, ensure_ascii=False)))


def _client(db, client_id):
    row = db.query(Cliente).filter(Cliente.id == client_id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Cliente no encontrado.')
    return row


def _serialize(db, client):
    values = {}
    for role, key in [('administrador', 'administradores'), ('cuentas_por_pagar', 'cuentas_por_pagar')]:
        values[key] = db.query(UsuarioInterno).filter(UsuarioInterno.cliente_id == client.id, UsuarioInterno.rol == role, UsuarioInterno.activo.is_(True)).count()
    from models import ProveedorCliente
    values['proveedores'] = db.query(ProveedorCliente).filter(ProveedorCliente.cliente_id == client.id, ProveedorCliente.activo.is_(True)).count()
    values['sociedades'] = db.query(Sociedad).filter(Sociedad.cliente_id == client.id, Sociedad.activo.is_(True)).count()
    principal = db.query(Sociedad).filter(Sociedad.cliente_id == client.id, Sociedad.es_principal.is_(True)).first()
    return {'id': client.id, 'codigo': client.codigo, 'nombre': client.nombre, 'activo': bool(client.activo), 'sociedad_principal': {'id': principal.id, 'ruc': principal.ruc, 'razon_social': principal.razon_social} if principal else None, 'cupos': {'administradores': {'usados': values['administradores'], 'maximo': client.max_administradores}, 'cuentas_por_pagar': {'usados': values['cuentas_por_pagar'], 'maximo': client.max_cuentas_por_pagar}, 'proveedores': {'usados': values['proveedores'], 'maximo': client.max_proveedores}, 'sociedades': {'usados': values['sociedades'], 'maximo': client.max_sociedades}}}


@router.get('')
def listar(_ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    return [_serialize(db, c) for c in db.query(Cliente).order_by(Cliente.nombre).all()]


@router.post('', status_code=201)
def crear(payload: ClienteEntrada, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    if db.query(Cliente.id).filter(Cliente.codigo == payload.codigo).first():
        raise HTTPException(status_code=409, detail='El código de cliente ya existe.')
    row = Cliente(id=str(uuid4()), codigo=payload.codigo, nombre=payload.nombre.strip(), activo=True, **payload.model_dump(exclude={'codigo', 'nombre', 'ruc_principal', 'razon_social_principal', 'codigo_sap_principal'}))
    db.add(row); db.flush()
    principal = Sociedad(id=str(uuid4()), cliente_id=row.id, ruc=payload.ruc_principal, razon_social=payload.razon_social_principal.strip(), codigo_sap=payload.codigo_sap_principal, es_principal=True, activo=True)
    db.add(principal)
    _audit(db, ivs, row.id, 'cliente_creado', 'cliente', row.id, {'codigo': row.codigo, 'nombre': row.nombre, 'sociedad_principal': {'ruc': principal.ruc, 'razon_social': principal.razon_social}})
    db.commit(); db.refresh(row)
    return _serialize(db, row)


@router.patch('/{cliente_id}')
def actualizar_cliente(cliente_id: str, payload: ClienteActualizacion, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id)
    duplicate = db.query(Cliente.id).filter(Cliente.codigo == payload.codigo, Cliente.id != row.id).first()
    if duplicate:
        raise HTTPException(status_code=409, detail='El código de cliente ya está registrado.')
    row.codigo = payload.codigo
    row.nombre = payload.nombre.strip()
    _audit(db, ivs, row.id, 'cliente_actualizado', 'cliente', row.id, payload.model_dump())
    db.commit()
    return _serialize(db, row)


@router.patch('/{cliente_id}/cupos')
def actualizar_cupos(cliente_id: str, payload: Cuotas, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id)
    current = _serialize(db, row)['cupos']
    for key, value in payload.model_dump().items():
        name = key.removeprefix('max_')
        used = current[name]['usados']
        if value < used:
            raise HTTPException(status_code=409, detail=f'El cupo de {name} no puede ser menor al uso activo ({used}).')
        setattr(row, key, value)
    _audit(db, ivs, row.id, 'cupos_actualizados', 'cliente', row.id, payload.model_dump()); db.commit()
    return _serialize(db, row)


@router.post('/{cliente_id}/sociedades', status_code=201)
def crear_sociedad(cliente_id: str, payload: SociedadEntrada, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id)
    if db.query(Sociedad.id).filter(Sociedad.cliente_id == row.id, Sociedad.ruc == payload.ruc).first():
        raise HTTPException(status_code=409, detail='La sociedad ya está registrada para este cliente.')
    if db.query(Sociedad.id).filter(Sociedad.cliente_id == row.id, Sociedad.activo.is_(True)).count() >= row.max_sociedades:
        raise HTTPException(status_code=409, detail='Se alcanzó el cupo de sociedades asignado por IVS.')
    society = Sociedad(id=str(uuid4()), cliente_id=row.id, ruc=payload.ruc, razon_social=payload.razon_social.strip(), codigo_sap=payload.codigo_sap, activo=True)
    db.add(society); db.flush(); _audit(db, ivs, row.id, 'sociedad_creada', 'sociedad', society.id, {'ruc': society.ruc}); db.commit()
    return {'id': society.id, 'ruc': society.ruc, 'razon_social': society.razon_social, 'codigo_sap': society.codigo_sap, 'es_principal': False, 'activo': True}


@router.get('/{cliente_id}/sociedades')
def listar_sociedades(cliente_id: str, _ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id)
    return [{'id': s.id, 'ruc': s.ruc, 'razon_social': s.razon_social, 'codigo_sap': s.codigo_sap, 'es_principal': bool(s.es_principal), 'activo': bool(s.activo)} for s in db.query(Sociedad).filter(Sociedad.cliente_id == row.id).order_by(Sociedad.es_principal.desc(), Sociedad.razon_social).all()]


@router.patch('/{cliente_id}/sociedades/{sociedad_id}')
def estado_sociedad(cliente_id: str, sociedad_id: str, payload: EstadoSociedad, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id)
    society = db.query(Sociedad).filter(Sociedad.id == sociedad_id, Sociedad.cliente_id == row.id).first()
    if not society:
        raise HTTPException(status_code=404, detail='Sociedad no encontrada para este cliente.')
    if society.es_principal and not payload.activo:
        raise HTTPException(status_code=409, detail='No se puede desactivar el RUC principal del cliente.')
    if payload.activo and not society.activo and db.query(Sociedad.id).filter(Sociedad.cliente_id == row.id, Sociedad.activo.is_(True)).count() >= row.max_sociedades:
        raise HTTPException(status_code=409, detail='Se alcanzó el cupo de sociedades asignado por IVS.')
    society.activo = payload.activo
    _audit(db, ivs, row.id, 'estado_sociedad_cambiado', 'sociedad', society.id, {'activo': payload.activo})
    db.commit()
    return {'id': society.id, 'ruc': society.ruc, 'activo': bool(society.activo)}


@router.post('/{cliente_id}/administradores', status_code=201)
def crear_administrador(cliente_id: str, payload: AdministradorEntrada, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id); username = str(payload.usuario).strip().lower()
    if db.query(UsuarioInterno.id).filter(UsuarioInterno.usuario == username).first():
        raise HTTPException(status_code=409, detail='El correo ya tiene una cuenta interna.')
    if db.query(UsuarioInterno.id).filter(UsuarioInterno.cliente_id == row.id, UsuarioInterno.rol == 'administrador', UsuarioInterno.activo.is_(True)).count() >= row.max_administradores:
        raise HTTPException(status_code=409, detail='Se alcanzó el cupo de administradores asignado por IVS.')
    temporary = secrets.token_urlsafe(18)
    account = UsuarioInterno(id=str(uuid4()), usuario=username, nombre=payload.nombre.strip(), rol='administrador', cliente_id=row.id, password_hash=get_password_hash(temporary), activo=True, cambio_password_requerido=True)
    db.add(account); _audit(db, ivs, row.id, 'administrador_creado', 'usuario_interno', account.id, {'usuario': username}); db.commit()
    return {'id': account.id, 'usuario': username, 'nombre': account.nombre, 'rol': account.rol, 'password_temporal': temporary, 'mensaje': 'Copia esta contraseña temporal ahora; no volverá a mostrarse.'}


@router.post('/{cliente_id}/credenciales-sap', summary='Rotar credencial de integración ERP; se revela una sola vez')
def rotar_credencial(cliente_id: str, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id)
    secret = secrets.token_urlsafe(36)
    row.sap_api_key_hash = hashlib.sha256(secret.encode('utf-8')).hexdigest()
    _audit(db, ivs, row.id, 'credencial_sap_rotada', 'cliente', row.id)
    db.commit()
    return {'cliente_id': row.id, 'token': secret, 'mensaje': 'Guárdalo en el gestor de secretos del cliente. No volverá a mostrarse.'}


@router.patch('/{cliente_id}/estado')
def estado_cliente(cliente_id: str, activo: bool, ivs: dict = Depends(get_current_ivs_admin_user), db: Session = Depends(get_db)):
    row = _client(db, cliente_id); row.activo = activo; _audit(db, ivs, row.id, 'estado_cliente_cambiado', 'cliente', row.id, {'activo': activo}); db.commit()
    return {'id': row.id, 'activo': bool(row.activo)}
