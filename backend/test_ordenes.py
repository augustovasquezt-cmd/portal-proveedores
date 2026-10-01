import sys
import types
import unittest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models import Base, Cliente, Proveedor, OrdenCompra, Factura

# No conexión a la base real ni dependencia de credenciales.
database = types.ModuleType('database')
database.get_db = lambda: None
auth = types.ModuleType('auth')
auth.get_current_user = lambda: None
auth.get_current_provider_user = lambda: None
sys.modules['database'] = database
sys.modules['auth'] = auth
from ordenes import listar_ordenes, resumen_facturacion

class OrdenesTests(unittest.TestCase):
    def test_saldos(self):
        for total, facturado, estado, esperado, saldo in [
            (100, 0, 'entregado', 'pendiente', 100),
            (100, 40, 'entregado', 'parcial', 60),
            (100, 100, 'entregado', 'facturada', 0),
            (100, 120, 'entregado', 'facturada', 0),
            (100, 0, 'cancelado', 'cancelada', 100),
            ('0.30', '0.10', 'entregado', 'parcial', 0.20),
        ]:
            with self.subTest(total=total, facturado=facturado):
                r = resumen_facturacion(total, facturado, estado)
                self.assertEqual(r['estado_facturacion'], esperado)
                self.assertEqual(r['saldo_por_facturar'], saldo)

    def test_aislamiento_y_facturas_excluidas(self):
        engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(Cliente(id='tenant',codigo='tenant',nombre='Tenant'))
            for i in ['a', 'b']:
                db.add(Proveedor(id=i, ruc=i, razon_social=i, email=i+'@test.local', password_hash='test'))
                db.add(OrdenCompra(id='oc'+i, numero='OC-'+i, proveedor_id=i, cliente_id='tenant', monto_total=100))
            for i, proveedor, estado, monto in [('1','a','Emitida',40), ('2','a',' Anulada ',30), ('3','a','Rechazada',20), ('4','b','Emitida',90)]:
                db.add(Factura(id=i, proveedor_id=proveedor, cliente_id='tenant', orden_compra_id='oca', serie='F001', correlativo=i, monto_subtotal=monto, monto_igv=0, monto_total=monto, estado=estado))
            db.commit()
            result = listar_ordenes({'ruc':'a','cliente_id':'tenant'}, db)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['id'], 'oca')
            self.assertEqual(result[0]['monto_facturado'], 40)
            self.assertEqual(result[0]['saldo_por_facturar'], 60)

if __name__ == '__main__':
    unittest.main()
