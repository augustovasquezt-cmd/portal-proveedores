"""Administración acotada al cliente seleccionado."""
import json
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from auth import get_current_admin_user, get_password_hash
from database import get_db
from models import (Cliente, Proveedor, ProveedorCliente, ProveedorSociedad,
                    RegistroAuditoria, Sociedad, UsuarioInterno, UsuarioSociedad)

router = APIRouter(prefix='/administracion', tags=['administración'])


class CrearUsuarioInterno(BaseModel):
    model_config = ConfigDict(extra='forbid')
    usuario: EmailStr
    nombre: str = Field(min_length=2, max_length=200)
    sociedades_ids: list[str] = Field(min_length=1)


class CrearProveedor(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ruc: str = Field(pattern=r'^\d{11}$')
    razon_social: str = Field(min_length=2, max_length=200)
    email: EmailStr
    sociedades_ids: list[str] = Field(min_length=1)


class EstadoCuenta(BaseModel):
    model_config = ConfigDict(extra='forbid')
    activo: bool


class AsignacionSociedades(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sociedades_ids: list[str] = Field(min_length=1)


def _auditar(db, actor, accion, tipo, target_id, details=None):
    db.add(RegistroAuditoria(
        id=str(uuid4()), actor_usuario_id=actor['usuario_id'], actor_usuario=actor['usuario'],
        cliente_id=actor.get('cliente_id'), accion=accion, tipo_objetivo=tipo, objetivo_id=target_id,
        detalles=json.dumps(details or {}, ensure_ascii=False),
    ))


def _temporal():
    return secrets.token_urlsafe(18)


def _tenant(admin, db):
    tenant = db.query(Cliente).filter(Cliente.id == admin['cliente_id'], Cliente.activo.is_(True)).first()
    if not tenant:
        raise HTTPException(status_code=403, detail='El cliente no está activo.')
    return tenant


def _sociedades(db, tenant, ids):
    ids = list(dict.fromkeys(ids))
    rows = db.query(Sociedad).filter(Sociedad.cliente_id == tenant.id, Sociedad.activo.is_(True), Sociedad.id.in_(ids)).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=422, detail='Selecciona únicamente sociedades habilitadas por IVS para este cliente.')
    return rows


@router.get('/cuotas', summary='Consultar cupos y asignaciones del cliente')
def cuotas(admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    return {
        'cliente': {'id': tenant.id, 'nombre': tenant.nombre},
        'administradores': {'usados': db.query(UsuarioInterno).filter(UsuarioInterno.cliente_id == tenant.id, UsuarioInterno.rol == 'administrador', UsuarioInterno.activo.is_(True)).count(), 'maximo': tenant.max_administradores},
        'cuentas_por_pagar': {'usados': db.query(UsuarioInterno).filter(UsuarioInterno.cliente_id == tenant.id, UsuarioInterno.rol == 'cuentas_por_pagar', UsuarioInterno.activo.is_(True)).count(), 'maximo': tenant.max_cuentas_por_pagar},
        'proveedores': {'usados': db.query(ProveedorCliente).filter(ProveedorCliente.cliente_id == tenant.id, ProveedorCliente.activo.is_(True)).count(), 'maximo': tenant.max_proveedores},
        'sociedades': {'usados': db.query(Sociedad).filter(Sociedad.cliente_id == tenant.id, Sociedad.activo.is_(True)).count(), 'maximo': tenant.max_sociedades},
    }


@router.get('/sociedades', summary='Listar sociedades habilitadas por IVS')
def listar_sociedades(admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    return [{'id': s.id, 'ruc': s.ruc, 'razon_social': s.razon_social, 'codigo_sap': s.codigo_sap} for s in db.query(Sociedad).filter(Sociedad.cliente_id == tenant.id, Sociedad.activo.is_(True)).order_by(Sociedad.razon_social).all()]


@router.get('/usuarios', summary='Listar cuentas de este cliente')
def listar_usuarios(admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    internos = db.query(UsuarioInterno).filter(UsuarioInterno.cliente_id == tenant.id, UsuarioInterno.rol == 'cuentas_por_pagar').order_by(UsuarioInterno.nombre.asc()).all()
    memberships = db.query(ProveedorCliente, Proveedor).join(Proveedor, Proveedor.id == ProveedorCliente.proveedor_id).filter(ProveedorCliente.cliente_id == tenant.id).order_by(Proveedor.razon_social.asc()).all()
    return {
        'usuarios_internos': [{'id': u.id, 'usuario': u.usuario, 'nombre': u.nombre, 'rol': u.rol, 'activo': bool(u.activo), 'debe_cambiar_password': bool(u.cambio_password_requerido), 'administrable': True, 'sociedades_ids': [x.sociedad_id for x in db.query(UsuarioSociedad).filter_by(cliente_id=tenant.id, usuario_id=u.id).all()]} for u in internos],
        'proveedores': [{'id': m.id, 'proveedor_id': p.id, 'ruc': p.ruc, 'razon_social': p.razon_social, 'email': p.email, 'estado': p.estado, 'activo': bool(m.activo), 'debe_cambiar_password': bool(p.cambio_password_requerido), 'sociedades_ids': [x.sociedad_id for x in db.query(ProveedorSociedad).filter_by(cliente_id=tenant.id, proveedor_cliente_id=m.id).all()]} for m, p in memberships],
    }


@router.post('/usuarios/cuentas-por-pagar', status_code=201)
def crear_usuario_interno(payload: CrearUsuarioInterno, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    _sociedades(db, tenant, payload.sociedades_ids)
    if db.query(UsuarioInterno).filter(UsuarioInterno.usuario == str(payload.usuario).strip().lower()).first() or db.query(Proveedor).filter(Proveedor.email == str(payload.usuario).strip().lower()).first():
        raise HTTPException(status_code=409, detail='El correo ya está asociado a una cuenta.')
    if db.query(UsuarioInterno).filter(UsuarioInterno.cliente_id == tenant.id, UsuarioInterno.rol == 'cuentas_por_pagar', UsuarioInterno.activo.is_(True)).count() >= tenant.max_cuentas_por_pagar:
        raise HTTPException(status_code=409, detail='Se alcanzó el máximo de cuentas por pagar configurado por IVS.')
    temporary = _temporal()
    account = UsuarioInterno(id=str(uuid4()), usuario=str(payload.usuario).strip().lower(), nombre=payload.nombre.strip(), rol='cuentas_por_pagar', cliente_id=tenant.id, password_hash=get_password_hash(temporary), activo=True, cambio_password_requerido=True)
    db.add(account); db.flush()
    for society in _sociedades(db, tenant, payload.sociedades_ids):
        db.add(UsuarioSociedad(cliente_id=tenant.id, usuario_id=account.id, sociedad_id=society.id))
    _auditar(db, admin, 'usuario_interno_creado', 'usuario_interno', account.id, {'usuario': account.usuario, 'rol': account.rol})
    db.commit()
    return {'id': account.id, 'usuario': account.usuario, 'nombre': account.nombre, 'rol': account.rol, 'activo': True, 'password_temporal': temporary, 'mensaje': 'Copia esta contraseña temporal ahora; no volverá a mostrarse.'}


@router.post('/usuarios/proveedores', status_code=201)
def crear_proveedor(payload: CrearProveedor, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db); societies = _sociedades(db, tenant, payload.sociedades_ids)
    ruc, email = payload.ruc.strip(), str(payload.email).strip().lower()
    membership = db.query(ProveedorCliente).join(Proveedor).filter(ProveedorCliente.cliente_id == tenant.id, Proveedor.ruc == ruc).first()
    if membership:
        raise HTTPException(status_code=409, detail='Este RUC ya está habilitado para el cliente.')
    if db.query(ProveedorCliente).filter(ProveedorCliente.cliente_id == tenant.id, ProveedorCliente.activo.is_(True)).count() >= tenant.max_proveedores:
        raise HTTPException(status_code=409, detail='Se alcanzó el máximo de proveedores configurado por IVS.')
    supplier = db.query(Proveedor).filter(Proveedor.ruc == ruc).first()
    if supplier:
        if db.query(UsuarioInterno).filter(UsuarioInterno.usuario == email).first() or (db.query(Proveedor).filter(Proveedor.email == email, Proveedor.id != supplier.id).first()):
            raise HTTPException(status_code=409, detail='El correo ya está asociado a otra cuenta.')
        # A shared RUC retains one credential across all client memberships.
        if supplier.email != email:
            raise HTTPException(status_code=409, detail='El RUC ya tiene una cuenta global. Usa el correo asociado a esa cuenta.')
        temporary = None
    else:
        if db.query(UsuarioInterno).filter(UsuarioInterno.usuario == email).first() or db.query(Proveedor).filter(Proveedor.email == email).first():
            raise HTTPException(status_code=409, detail='El correo ya está asociado a otra cuenta.')
        temporary = _temporal()
        supplier = Proveedor(id=str(uuid4()), ruc=ruc, razon_social=payload.razon_social.strip(), email=email, password_hash=get_password_hash(temporary), estado='activo', activo=True, cambio_password_requerido=True)
        db.add(supplier); db.flush()
    link = ProveedorCliente(id=str(uuid4()), proveedor_id=supplier.id, cliente_id=tenant.id, activo=True)
    db.add(link); db.flush()
    for society in societies:
        db.add(ProveedorSociedad(cliente_id=tenant.id, proveedor_cliente_id=link.id, sociedad_id=society.id))
    _auditar(db, admin, 'proveedor_habilitado', 'proveedor_cliente', link.id, {'ruc': ruc, 'sociedades': [s.ruc for s in societies]})
    db.commit()
    return {'id': link.id, 'proveedor_id': supplier.id, 'ruc': supplier.ruc, 'razon_social': supplier.razon_social, 'email': supplier.email, 'activo': True, 'password_temporal': temporary, 'mensaje': 'Copia esta contraseña temporal ahora; no volverá a mostrarse.' if temporary else 'El proveedor conserva su cuenta y contraseña existentes.'}


@router.patch('/usuarios/internos/{account_id}')
def cambiar_estado_interno(account_id: str, payload: EstadoCuenta, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    account = db.query(UsuarioInterno).filter(UsuarioInterno.id == account_id, UsuarioInterno.cliente_id == tenant.id, UsuarioInterno.rol == 'cuentas_por_pagar').first()
    if not account: raise HTTPException(status_code=404, detail='Cuenta de cuentas por pagar no encontrada.')
    if payload.activo and not account.activo and db.query(UsuarioInterno).filter(UsuarioInterno.cliente_id == tenant.id, UsuarioInterno.rol == 'cuentas_por_pagar', UsuarioInterno.activo.is_(True)).count() >= tenant.max_cuentas_por_pagar:
        raise HTTPException(status_code=409, detail='Se alcanzó el máximo de cuentas por pagar configurado por IVS.')
    account.activo = payload.activo; _auditar(db, admin, 'usuario_interno_estado_cambiado', 'usuario_interno', account.id, {'activo': payload.activo}); db.commit()
    return {'id': account.id, 'usuario': account.usuario, 'rol': account.rol, 'activo': bool(account.activo)}


@router.put('/usuarios/internos/{account_id}/sociedades')
def asignar_sociedades_interno(account_id: str, payload: AsignacionSociedades, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    account = db.query(UsuarioInterno).filter_by(id=account_id, cliente_id=tenant.id, rol='cuentas_por_pagar').first()
    if not account: raise HTTPException(status_code=404, detail='Cuenta de cuentas por pagar no encontrada.')
    societies = _sociedades(db, tenant, payload.sociedades_ids)
    db.query(UsuarioSociedad).filter_by(cliente_id=tenant.id, usuario_id=account.id).delete(synchronize_session=False)
    for society in societies: db.add(UsuarioSociedad(cliente_id=tenant.id, usuario_id=account.id, sociedad_id=society.id))
    _auditar(db, admin, 'sociedades_usuario_actualizadas', 'usuario_interno', account.id, {'sociedades_ids': [s.id for s in societies]})
    db.commit()
    return {'id': account.id, 'sociedades_ids': [s.id for s in societies]}


@router.patch('/usuarios/proveedores/{provider_id}')
def cambiar_estado_proveedor(provider_id: str, payload: EstadoCuenta, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    link = db.query(ProveedorCliente).filter(ProveedorCliente.id == provider_id, ProveedorCliente.cliente_id == tenant.id).first()
    if not link: raise HTTPException(status_code=404, detail='Proveedor no encontrado en este cliente.')
    if payload.activo and not link.activo and db.query(ProveedorCliente).filter(ProveedorCliente.cliente_id == tenant.id, ProveedorCliente.activo.is_(True)).count() >= tenant.max_proveedores:
        raise HTTPException(status_code=409, detail='Se alcanzó el máximo de proveedores configurado por IVS.')
    link.activo = payload.activo; _auditar(db, admin, 'proveedor_cliente_estado_cambiado', 'proveedor_cliente', link.id, {'activo': payload.activo}); db.commit()
    return {'id': link.id, 'proveedor_id': link.proveedor_id, 'activo': bool(link.activo)}


@router.put('/usuarios/proveedores/{provider_id}/sociedades')
def asignar_sociedades_proveedor(provider_id: str, payload: AsignacionSociedades, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    tenant = _tenant(admin, db)
    link = db.query(ProveedorCliente).filter_by(id=provider_id, cliente_id=tenant.id).first()
    if not link: raise HTTPException(status_code=404, detail='Proveedor no encontrado en este cliente.')
    societies = _sociedades(db, tenant, payload.sociedades_ids)
    db.query(ProveedorSociedad).filter_by(cliente_id=tenant.id, proveedor_cliente_id=link.id).delete(synchronize_session=False)
    for society in societies: db.add(ProveedorSociedad(cliente_id=tenant.id, proveedor_cliente_id=link.id, sociedad_id=society.id))
    _auditar(db, admin, 'sociedades_proveedor_actualizadas', 'proveedor_cliente', link.id, {'sociedades_ids': [s.id for s in societies]})
    db.commit()
    return {'id': link.id, 'sociedades_ids': [s.id for s in societies]}


@router.post('/usuarios/internos/{account_id}/restablecer-password')
def restablecer_password_interno(account_id: str, admin: dict = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    account = db.query(UsuarioInterno).filter(UsuarioInterno.id == account_id, UsuarioInterno.cliente_id == admin['cliente_id'], UsuarioInterno.rol == 'cuentas_por_pagar').first()
    if not account: raise HTTPException(status_code=404, detail='Cuenta de cuentas por pagar no encontrada.')
    temporary = _temporal(); account.password_hash = get_password_hash(temporary); account.cambio_password_requerido = True
    _auditar(db, admin, 'password_interno_restablecido', 'usuario_interno', account.id); db.commit()
    return {'id': account.id, 'usuario': account.usuario, 'password_temporal': temporary, 'mensaje': 'Copia esta contraseña temporal ahora; no volverá a mostrarse.'}
