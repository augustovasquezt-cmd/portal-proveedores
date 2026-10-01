"""Tenant and society authorization helpers for business APIs."""
from fastapi import HTTPException
from models import Cliente, Sociedad, UsuarioSociedad, Proveedor, ProveedorCliente, ProveedorSociedad


def tenant_activo(db, user):
    cliente_id = user.get('cliente_id')
    tenant = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.activo.is_(True)).first()
    if not tenant:
        raise HTTPException(status_code=403, detail='El cliente seleccionado no está activo.')
    return tenant


def sociedades_usuario(db, user):
    tenant = tenant_activo(db, user)
    query = db.query(Sociedad).filter(Sociedad.cliente_id == tenant.id, Sociedad.activo.is_(True))
    if user.get('rol') == 'proveedor':
        supplier = db.query(Proveedor).filter(Proveedor.ruc == user.get('ruc'), Proveedor.activo.is_(True)).first()
        membership = db.query(ProveedorCliente).filter(
            ProveedorCliente.proveedor_id == supplier.id if supplier else False,
            ProveedorCliente.cliente_id == tenant.id, ProveedorCliente.activo.is_(True),
        ).first()
        if not membership:
            return []
        return query.join(ProveedorSociedad, ProveedorSociedad.sociedad_id == Sociedad.id).filter(
            ProveedorSociedad.cliente_id == tenant.id,
            ProveedorSociedad.proveedor_cliente_id == membership.id,
        ).order_by(Sociedad.razon_social.asc()).all()
    if user.get('rol') == 'administrador':
        return query.order_by(Sociedad.razon_social.asc()).all()
    return query.join(UsuarioSociedad, UsuarioSociedad.sociedad_id == Sociedad.id).filter(
        UsuarioSociedad.cliente_id == tenant.id,
        UsuarioSociedad.usuario_id == user.get('usuario_id'),
    ).order_by(Sociedad.razon_social.asc()).all()


def sociedad_autorizada(db, user, sociedad_id):
    society = next((item for item in sociedades_usuario(db, user) if item.id == sociedad_id), None)
    if not society:
        raise HTTPException(status_code=403, detail='No tienes acceso a la sociedad receptora seleccionada.')
    return society


def ids_sociedades_usuario(db, user):
    return [society.id for society in sociedades_usuario(db, user)]
