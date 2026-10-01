"""Carga ejemplos identificados como DEMO sin modificar registros existentes."""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid5, NAMESPACE_URL
from collections import Counter
from database import SessionLocal
from models import Proveedor, OrdenCompra, Factura
from ordenes import listar_ordenes
from seed_helpers import demo_context

RUC = '20999999999'
EJEMPLOS = [
    ('Tuberías y conexiones PVC', '3540', 'entregado', 2, None),
    ('Herramientas para mantenimiento', '5900', 'por_recepcionar', 5, None),
    ('Equipos de protección personal', '2360', 'entregado', 8, None),
    ('Material eléctrico y luminarias', '8260', 'en_proceso', 12, '3540'),
    ('Pinturas y accesorios', '4720', 'entregado', 18, '2360'),
    ('Pernos y fijaciones industriales', '1180', 'entregado', 25, '1180'),
    ('Bombas de agua', '7080', 'entregado', 35, '7080'),
    ('Reposición de herramientas', '2950', 'cancelado', 45, None),
    ('Suministros de limpieza industrial', '1770', 'entregado', 55, None),
    ('Válvulas de seguridad', '4130', 'por_recepcionar', 65, None),
]

def identificador(tipo, indice):
    return str(uuid5(NAMESPACE_URL, f'portal-proveedores/demo/{RUC}/{tipo}/{indice}'))


def main():
    with SessionLocal.begin() as db:
        cliente, sociedad = demo_context(db)
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == RUC).one_or_none()
        if proveedor is None or proveedor.razon_social != 'Ferretería La Torre SAC':
            raise RuntimeError('No se encontró el proveedor de ejemplo esperado. No se modificaron datos.')
        nuevas = 0
        for i, (descripcion, total, estado, dias, facturado) in enumerate(EJEMPLOS, 1):
            numero = f'DEMO-OC-2026-{i:04d}'
            oid = identificador('orden', i)
            existente = db.query(OrdenCompra).filter(OrdenCompra.numero == numero).one_or_none()
            if existente:
                if existente.id != oid or existente.proveedor_id != proveedor.id:
                    raise RuntimeError('Colisión con una orden existente; transacción cancelada.')
                continue
            fecha = datetime(2026, 9, 28, 10) - timedelta(days=dias)
            db.add(OrdenCompra(id=oid, numero=numero, proveedor_id=proveedor.id, cliente_id=cliente.id, sociedad_id=sociedad.id,
                monto_total=Decimal(total), estado=estado,
                descripcion='[DEMO] ' + descripcion, creado_en=fecha))
            nuevas += 1
            if facturado:
                monto = Decimal(facturado)
                subtotal = (monto / Decimal('1.18')).quantize(Decimal('0.01'))
                db.add(Factura(id=identificador('factura', i), proveedor_id=proveedor.id, cliente_id=cliente.id, sociedad_id=sociedad.id,
                    serie='DEMO', correlativo=f'{i:08d}', orden_compra_id=oid,
                    monto_subtotal=subtotal, monto_igv=monto-subtotal, monto_total=monto,
                    estado='Emitida', creado_en=fecha+timedelta(days=1)))
        db.flush()
        resultado = [o for o in listar_ordenes({'ruc': RUC, 'cliente_id':cliente.id}, db) if o['numero'].startswith('DEMO-OC-2026-')]
        print('Órdenes nuevas:', nuevas)
        print('Estados demo:', dict(Counter(o['estado_facturacion'] for o in resultado)))
        print('Saldo pendiente demo:', sum(Decimal(str(o['saldo_por_facturar'])) for o in resultado if o['estado_facturacion'] in ['pendiente','parcial']))
    print('Datos de ejemplo guardados correctamente.')

if __name__ == '__main__':
    main()
