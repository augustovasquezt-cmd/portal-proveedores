from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_provider_user
from facturas import proveedor_actual, fail
from models import DocumentoBase, DocumentoBaseLinea, FacturaOrigen, FacturaAsignacion, Factura, OrdenPosicion, OrdenCompra
ESTADOS={'mercancia':'recibido','servicio':'aceptado','guia':'despachado'}
EXCLUIDOS=['anulada','anulado','rechazada','rechazado','cancelada','cancelado']
router=APIRouter(prefix='/documentos-base',tags=['documentos de referencia'])

def pendiente(db,linea):
    usado=db.query(func.coalesce(func.sum(FacturaAsignacion.cantidad),0)).join(FacturaOrigen,FacturaOrigen.asignacion_id==FacturaAsignacion.id).join(Factura,Factura.id==FacturaAsignacion.factura_id).filter(FacturaOrigen.documento_linea_id==linea.id,func.lower(func.trim(Factura.estado)).notin_(EXCLUIDOS)).scalar()
    return max(linea.cantidad-usado,Decimal(0))

@router.get('')
def listar(tipo:str,user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    from posiciones import posiciones
    from saldos import importes_por_orden
    if tipo not in ESTADOS: fail('Tipo de documento inválido.')
    proveedor=proveedor_actual(db,user)
    importes=importes_por_orden(db,proveedor.id,user['cliente_id'])
    docs=db.query(DocumentoBase).filter(DocumentoBase.proveedor_id==proveedor.id,DocumentoBase.cliente_id==user['cliente_id'],DocumentoBase.tipo==tipo,DocumentoBase.estado==ESTADOS[tipo]).order_by(DocumentoBase.fecha.desc(),DocumentoBase.numero).all()
    cache={};resultado=[]
    for doc in docs:
        filas=[]
        for l,p,o in db.query(DocumentoBaseLinea,OrdenPosicion,OrdenCompra).join(OrdenPosicion,OrdenPosicion.id==DocumentoBaseLinea.posicion_id).join(OrdenCompra,OrdenCompra.id==OrdenPosicion.orden_id).filter(DocumentoBaseLinea.documento_id==doc.id,OrdenCompra.proveedor_id==proveedor.id,OrdenCompra.cliente_id==user['cliente_id']).all():
            if o.estado.lower() in EXCLUIDOS: continue
            if o.id not in cache:cache[o.id]=posiciones(db,o)
            state=cache[o.id]
            if state['bloqueo']:continue
            item=next(x for x in state['posiciones'] if x['id']==p.id)
            disponible=min(pendiente(db,l),Decimal(str(item['cantidad_pendiente'])))
            if disponible<=0:continue
            filas.append({**item,'id':l.id,'posicion_id':p.id,'documento_linea_id':l.id,'documento':doc.numero,'documento_posicion':l.numero,'orden_id':o.id,'pedido':o.numero,'saldo_pedido':float(max(o.monto_total-importes.get(o.id,0),0)),'cantidad_pendiente':float(disponible),'cantidad_documento':float(l.cantidad)})
        if filas:resultado.append(dict(id=doc.id,numero=doc.numero,tipo=doc.tipo,estado=doc.estado,fecha=doc.fecha.isoformat(),posiciones=filas))
    return resultado

def validar_origenes(db,asignaciones,proveedor_id,cliente_id=None):
    cantidades={};origenes={}
    for a in asignaciones:
        lid=a.get('documento_linea_id')
        if not lid: continue
        if not isinstance(lid,str):fail('Referencia de documento inválida.')
        query=db.query(DocumentoBaseLinea,DocumentoBase).join(DocumentoBase,DocumentoBase.id==DocumentoBaseLinea.documento_id).filter(DocumentoBaseLinea.id==lid,DocumentoBase.proveedor_id==proveedor_id)
        if cliente_id: query=query.filter(DocumentoBase.cliente_id==cliente_id)
        row=query.first()
        if not row:fail('Documento no encontrado para el proveedor.',404)
        l,d=row
        if d.tipo not in ESTADOS or d.estado!=ESTADOS[d.tipo]:fail('El documento no está recibido, aceptado o despachado.')
        if l.posicion_id!=a.get('posicion_id'):fail('La línea del documento no corresponde a la posición.')
        posicion=db.get(OrdenPosicion,l.posicion_id)
        if posicion.tipo=='servicio' and d.tipo!='servicio':fail('Las posiciones de servicio requieren una hoja de entrada de servicios aceptada.')
        if d.tipo=='servicio' and posicion.tipo!='servicio':fail('La hoja de entrada de servicios no corresponde a una posición de servicio del pedido.')
        from posiciones import number
        cantidades[lid]=cantidades.get(lid,Decimal(0))+number(a.get('cantidad'))
        if cantidades[lid]>pendiente(db,l):fail('La cantidad supera el pendiente del documento '+d.numero)
        origenes[lid]=d.tipo
    if origenes and (len(origenes)!=len({a.get('documento_linea_id') for a in asignaciones}) or any(not a.get('documento_linea_id') for a in asignaciones)):fail('No mezcles posiciones sin referencia con documentos en el mismo registro.')
    if len(set(origenes.values()))>1:fail('Selecciona documentos de la misma base de facturación.')
