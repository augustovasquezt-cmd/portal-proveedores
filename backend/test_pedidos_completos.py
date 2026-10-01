import unittest
from decimal import Decimal
from fastapi import HTTPException
import test_facturas_registro as base
from posiciones import validar_completos
from models import OrdenCompra
from saldos import importes_por_orden

class CompletosTests(base.RegistroTests):
    def test_pedido_completo_admite_facturacion_parcial(self):
        o=self.db.get(OrdenCompra,'oc');o.monto_total=236;self.db.commit()
        full=[dict(orden_id='oc',posicion_id='pos',cantidad=Decimal(2),total=Decimal(236))]
        validar_completos(self.db,[o],full,['oc'],{})
        partial=[dict(orden_id='oc',posicion_id='pos',cantidad=Decimal(1),total=Decimal(118))]
        validar_completos(self.db,[o],partial,['oc'],{})
        with self.assertRaises(HTTPException):validar_completos(self.db,[o],full,['oc','otro'],{})
    def test_solo_restante_despues_de_facturacion(self):
        o=self.db.get(OrdenCompra,'oc');o.monto_total=236;self.db.commit()
        self.submit()
        validar_completos(self.db,[o],[dict(orden_id='oc',posicion_id='pos',cantidad=Decimal(1),total=Decimal(118))],['oc'],importes_por_orden(self.db,'a'))
        with self.assertRaises(HTTPException):validar_completos(self.db,[o],[dict(orden_id='oc',posicion_id='pos',cantidad=Decimal(2),total=Decimal(236))],['oc'],importes_por_orden(self.db,'a'))
if __name__=='__main__':unittest.main()
