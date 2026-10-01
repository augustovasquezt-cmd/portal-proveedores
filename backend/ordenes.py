from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from models import OrdenCompra, Factura, Proveedor, Sociedad
from auth import get_current_provider_user

router = APIRouter(prefix="/ordenes", tags=["ordenes"])


def resumen_facturacion(total, facturado, estado):
    total = Decimal(str(total))
    facturado = Decimal(str(facturado))
    saldo = max(total - facturado, Decimal("0"))
    if estado.lower() in {"cancelado", "cancelada", "anulado", "anulada"}:
        situacion = "cancelada"
    elif saldo == 0:
        situacion = "facturada"
    elif facturado > 0:
        situacion = "parcial"
    else:
        situacion = "pendiente"
    return {"monto_facturado": float(facturado), "saldo_por_facturar": float(saldo),
            "estado_facturacion": situacion}


@router.get("")
def listar_ordenes(current_user: dict = Depends(get_current_provider_user), db: Session = Depends(get_db)):
    proveedor = db.query(Proveedor).filter(Proveedor.ruc == current_user["ruc"]).first()
    if not proveedor:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    ordenes = db.query(OrdenCompra).filter(
        OrdenCompra.proveedor_id == proveedor.id, OrdenCompra.cliente_id == current_user['cliente_id'],
    ).order_by(OrdenCompra.creado_en.desc()).all()
    # Ambos conjuntos se limitan al proveedor autenticado.
    from saldos import importes_por_orden
    importes = importes_por_orden(db, proveedor.id, current_user['cliente_id'])
    society_ids = {o.sociedad_id for o in ordenes if o.sociedad_id}
    societies = {s.id: s for s in db.query(Sociedad).filter(Sociedad.id.in_(society_ids)).all()} if society_ids else {}
    return [{
        "id": o.id, "numero": o.numero, "monto_total": float(o.monto_total),
        "estado": o.estado, "descripcion": o.descripcion,
        "sociedad_id": o.sociedad_id,
        "sociedad_ruc": societies[o.sociedad_id].ruc if o.sociedad_id in societies else None,
        "creado_en": o.creado_en.isoformat() if o.creado_en else None,
        **resumen_facturacion(o.monto_total, importes.get(o.id, 0), o.estado or ""),
    } for o in ordenes]
