from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import OrdenCompra
from auth import get_current_user

router = APIRouter(prefix="/ordenes", tags=["ordenes"])

@router.get("")
def listar_ordenes(
    proveedor_id: str = Depends( get_current_user),
    db: Session = Depends(get_db)
):
    ordenes = db.query(OrdenCompra).filter(
        OrdenCompra.proveedor_id == proveedor_id
    ).order_by(OrdenCompra.creado_en.desc()).all()

    return [
        {
            "id": o.id,
            "numero": o.numero,
            "monto_total": float(o.monto_total),
            "estado": o.estado,
            "descripcion": o.descripcion,
            "creado_en": o.creado_en.isoformat() if o.creado_en else None,
        }
        for o in ordenes
    ]
