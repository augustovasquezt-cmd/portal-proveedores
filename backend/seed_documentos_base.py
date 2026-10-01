from datetime import date
from decimal import Decimal
from database import SessionLocal, crear_tablas
from models import Proveedor,OrdenCompra,OrdenPosicion,DocumentoBase,DocumentoBaseLinea
from seed_helpers import demo_context
crear_tablas()
with SessionLocal.begin() as db:
    cliente,sociedad=demo_context(db)
    p=db.query(Proveedor).filter(Proveedor.ruc=='20999999999').one()
    order=db.query(OrdenCompra).filter(OrdenCompra.numero=='DEMO-OC-POS-0001').one()
    pos=db.query(OrdenPosicion).filter(OrdenPosicion.orden_id==order.id,OrdenPosicion.numero=='00010').one()
    service=db.query(OrdenCompra).filter(OrdenCompra.numero=='DEMO-OC-SERV-0001').first()
    if not service:
        service=OrdenCompra(numero='DEMO-OC-SERV-0001',proveedor_id=p.id,cliente_id=cliente.id,sociedad_id=sociedad.id,monto_total=1888,estado='entregado',descripcion='[DEMO] Servicio de mantenimiento')
        db.add(service);db.flush()
        db.add(OrdenPosicion(orden_id=service.id,numero='00010',tipo='servicio',material='',codigo_servicio='SERV-100',paquete_servicio='0000123001',numero_servicio='0000000010',descripcion='Horas de mantenimiento',unidad='HUR',cantidad=8,precio_unitario=200,tasa_igv=18));db.flush()
    sp=db.query(OrdenPosicion).filter(OrdenPosicion.orden_id==service.id).one()
    sp.tipo='servicio';sp.codigo_servicio=sp.codigo_servicio or sp.material or 'SERV-100';sp.paquete_servicio=sp.paquete_servicio or '0000123001';sp.numero_servicio=sp.numero_servicio or '0000000010';sp.material=''
    for tipo,num,estado,position,qty in [('mercancia','DEMO-EM-0001','recibido',pos,4),('mercancia','DEMO-EM-0002','recibido',pos,6),('guia','DEMO-GR-0001','despachado',pos,6),('servicio','DEMO-HES-0001','aceptado',sp,5)]:
        if db.query(DocumentoBase).filter(DocumentoBase.numero==num).first():continue
        d=DocumentoBase(proveedor_id=p.id,cliente_id=cliente.id,tipo=tipo,numero=num,estado=estado,fecha=date(2026,9,28));db.add(d);db.flush()
        db.add(DocumentoBaseLinea(documento_id=d.id,posicion_id=position.id,numero='1',cantidad=qty))
    print('Ejemplos listos: DEMO-EM-0001, DEMO-EM-0002, DEMO-HES-0001 y DEMO-GR-0001')
