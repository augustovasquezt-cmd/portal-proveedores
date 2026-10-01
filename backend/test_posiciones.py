import asyncio
import io
import json
import unittest
from test_facturas_registro import RegistroTests, PDF
from posiciones import registrar_posiciones, posiciones
from models import OrdenCompra, FacturaAsignacion, Factura
from fastapi import UploadFile, HTTPException

class PosicionesTests(RegistroTests):
    def manual(self,qty=1,numero='5',pos='pos',total='118',subtotal='100',igv='18'):
        return asyncio.run(registrar_posiciones(orden_compra_id='oc',modo='pdf',asignaciones=json.dumps([{'posicion_id':pos,'cantidad':qty}]),cabecera=json.dumps(dict(serie='F002',correlativo=numero,fecha_emision='2026-01-01',moneda='PEN',ruc_emisor='20999999999',ruc_receptor='20999999999',monto_subtotal=subtotal,monto_igv=igv,monto_total=total)),pdf=UploadFile(io.BytesIO(PDF),filename='f.pdf'),xml=None,user=self.user,db=self.db))
    def test_pdf_parcial_y_saldo(self):
        self.db.get(OrdenCompra,'oc').monto_total=236;self.db.commit()
        self.manual()
        p=posiciones(self.db,self.db.get(OrdenCompra,'oc'))['posiciones'][0]
        self.assertEqual(p['cantidad_pendiente'],1)
        self.assertEqual(p['saldo'],118)
        self.manual(numero='6')
        self.assertEqual(posiciones(self.db,self.db.get(OrdenCompra,'oc'))['posiciones'][0]['cantidad_pendiente'],0)
        with self.assertRaises(HTTPException):self.manual(numero='7')
        self.assertEqual(self.db.query(FacturaAsignacion).count(),2)
    def test_cantidades_y_posicion_ajena(self):
        for qty,pos in [(3,'pos'),(-1,'pos'),(1,'otra')]:
            with self.subTest(qty=qty,pos=pos),self.assertRaises(HTTPException):self.manual(qty=qty,pos=pos)
        self.assertEqual(self.db.query(Factura).count(),0)
    def test_totales_pdf_no_coinciden(self):
        with self.assertRaises(HTTPException):self.manual(total='119')
        self.assertEqual(self.db.query(Factura).count(),0)

if __name__=='__main__':unittest.main()
