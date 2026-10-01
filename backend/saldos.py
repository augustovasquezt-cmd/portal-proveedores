from decimal import Decimal
from sqlalchemy import func
from models import Factura, FacturaAsignacion, OrdenPosicion
EXCLUIDOS=['anulada','anulado','rechazada','rechazado','cancelada','cancelado']
def importes_por_orden(db,proveedor_id,cliente_id=None):
    filtro=(Factura.proveedor_id==proveedor_id,func.lower(func.trim(func.coalesce(Factura.estado,''))).notin_(EXCLUIDOS))
    if cliente_id:
        filtro=filtro+(Factura.cliente_id==cliente_id,)
    importes=dict(db.query(OrdenPosicion.orden_id,func.sum(FacturaAsignacion.total)).join(FacturaAsignacion,FacturaAsignacion.posicion_id==OrdenPosicion.id).join(Factura,Factura.id==FacturaAsignacion.factura_id).filter(*filtro).group_by(OrdenPosicion.orden_id).all())
    historicos=db.query(Factura.orden_compra_id,func.sum(Factura.monto_total)).filter(*filtro,~db.query(FacturaAsignacion.id).filter(FacturaAsignacion.factura_id==Factura.id).exists()).group_by(Factura.orden_compra_id).all()
    for oid,total in historicos:importes[oid]=importes.get(oid,Decimal(0))+total
    return importes
