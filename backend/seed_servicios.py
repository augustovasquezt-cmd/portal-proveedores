"""Carga un ejemplo reutilizable de posición SAP con dos líneas de servicio y HES aceptada."""
from datetime import date
from decimal import Decimal

from database import SessionLocal, crear_tablas
from models import DocumentoBase, DocumentoBaseLinea, OrdenCompra, OrdenPosicion, Proveedor
from seed_helpers import demo_context


crear_tablas()

with SessionLocal.begin() as db:
    cliente,sociedad=demo_context(db)
    proveedor = db.query(Proveedor).filter(Proveedor.ruc == '20999999999').one()
    numero_pedido = 'DEMO-OC-SERV-0002'
    pedido = db.query(OrdenCompra).filter(OrdenCompra.numero == numero_pedido).first()
    if not pedido:
        pedido = OrdenCompra(
            numero=numero_pedido,
            proveedor_id=proveedor.id,
            cliente_id=cliente.id,
            sociedad_id=sociedad.id,
            monto_total=Decimal('3540.00'),
            estado='entregado',
            descripcion='[DEMO] Servicios de instalación y puesta en marcha',
        )
        db.add(pedido)
        db.flush()
        # Both service specification rows belong to PO item 00010; the package
        # and subline are preserved separately for future SAP adapters.
        db.add_all([
            OrdenPosicion(
                orden_id=pedido.id, numero='00010', tipo='servicio', material='',
                codigo_servicio='SRV-INST-01', paquete_servicio='0000123456',
                numero_servicio='0000000010', descripcion='Instalación de equipos',
                unidad='HUR', cantidad=Decimal('4'), precio_unitario=Decimal('250'), tasa_igv=18,
            ),
            OrdenPosicion(
                orden_id=pedido.id, numero='00010', tipo='servicio', material='',
                codigo_servicio='SRV-PUE-02', paquete_servicio='0000123456',
                numero_servicio='0000000020', descripcion='Pruebas y puesta en marcha',
                unidad='HUR', cantidad=Decimal('2'), precio_unitario=Decimal('500'), tasa_igv=18,
            ),
        ])
        db.flush()

    doc_numero = 'DEMO-HES-0002'
    if not db.query(DocumentoBase).filter(DocumentoBase.numero == doc_numero).first():
        doc = DocumentoBase(
            proveedor_id=proveedor.id, tipo='servicio', numero=doc_numero,
            cliente_id=cliente.id,
            estado='aceptado', fecha=date(2026, 9, 29),
        )
        db.add(doc)
        db.flush()
        rows = db.query(OrdenPosicion).filter(OrdenPosicion.orden_id == pedido.id).order_by(OrdenPosicion.numero_servicio).all()
        db.add_all([
            DocumentoBaseLinea(documento_id=doc.id, posicion_id=rows[0].id, numero='0000000010', cantidad=Decimal('2')),
            DocumentoBaseLinea(documento_id=doc.id, posicion_id=rows[1].id, numero='0000000020', cantidad=Decimal('1')),
        ])

print(f'Ejemplo de servicios listo: {numero_pedido} · paquete 0000123456 · HES {doc_numero}')
