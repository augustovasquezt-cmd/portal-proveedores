from decimal import Decimal
from database import SessionLocal, crear_tablas
from models import Proveedor, OrdenCompra, OrdenPosicion
from seed_helpers import demo_context
crear_tablas()
with SessionLocal.begin() as db:
    cliente,sociedad=demo_context(db)
    p=db.query(Proveedor).filter(Proveedor.ruc=='20999999999').one()
    numero='DEMO-OC-2026-0012'
    o=db.query(OrdenCompra).filter(OrdenCompra.numero==numero).first()
    if not o:
        o=OrdenCompra(numero=numero,proveedor_id=p.id,cliente_id=cliente.id,sociedad_id=sociedad.id,monto_total=Decimal('4720'),estado='entregado',descripcion='[DEMO] Pedido de suministros eléctricos')
        db.add(o);db.flush()
        for num,mat,desc,q,price in [('00010','MAT-400','Cables eléctricos',10,100),('00020','MAT-500','Tableros eléctricos',5,400),('00030','MAT-600','Interruptores',20,50)]:
            db.add(OrdenPosicion(orden_id=o.id,numero=num,material=mat,descripcion=desc,unidad='NIU',cantidad=q,precio_unitario=price,tasa_igv=18))
    print('Pedido de ejemplo:',numero,'Total: 4720 PEN')

