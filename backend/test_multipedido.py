import asyncio
import io
import json
import unittest
import test_facturas_registro as base
from fastapi import UploadFile, HTTPException
from models import OrdenCompra, OrdenPosicion, Factura
from posiciones import registrar_posiciones
from saldos import importes_por_orden
from ordenes import listar_ordenes

class MultiPedidoTests(base.RegistroTests):
    def setUp(self):
        super().setUp()
        self.db.add(OrdenCompra(id='oc2',numero='OC2',proveedor_id='a',cliente_id='tenant',sociedad_id='soc',monto_total=236,estado='entregado'))
        self.db.add(OrdenPosicion(id='pos2',orden_id='oc2',numero='00010',material='M2',descripcion='Otro material',unidad='NIU',cantidad=2,precio_unitario=100,tasa_igv=18))
        self.db.commit()
    def send_multi(self):
        header=dict(serie='F009',correlativo='1',fecha_emision='2026-01-01',moneda='PEN',ruc_emisor='20999999999',ruc_receptor='20999999999',monto_subtotal='200',monto_igv='36',monto_total='236')
        return asyncio.run(registrar_posiciones(orden_compra_id='oc',modo='pdf',asignaciones=json.dumps([dict(posicion_id='pos',cantidad=1),dict(posicion_id='pos2',cantidad=1)]),cabecera=json.dumps(header),pdf=UploadFile(io.BytesIO(base.PDF),filename='f.pdf'),xml=None,user=self.user,db=self.db))
    def test_distribucion_independiente(self):
        r=self.send_multi()
        self.assertIsNone(self.db.get(Factura,r['id']).orden_compra_id)
        importes=importes_por_orden(self.db,'a','tenant')
        self.assertEqual(importes['oc'],118)
        self.assertEqual(importes['oc2'],118)
        ordenes={o['id']:o for o in listar_ordenes(self.user,self.db)}
        self.assertEqual(ordenes['oc']['saldo_por_facturar'],82)
        self.assertEqual(ordenes['oc2']['saldo_por_facturar'],118)
    def test_ajeno_no_guarda_nada(self):
        self.db.get(OrdenCompra,'oc2').proveedor_id='b';self.db.commit()
        with self.assertRaises(HTTPException):self.send_multi()
        self.assertEqual(self.db.query(Factura).count(),0)
    def test_limite_individual(self):
        self.db.get(OrdenCompra,'oc').monto_total=100;self.db.commit()
        with self.assertRaises(HTTPException):self.send_multi()
        self.assertEqual(self.db.query(Factura).count(),0)
    def test_cancelado_no_guarda_nada(self):
        self.db.get(OrdenCompra,'oc2').estado='cancelado';self.db.commit()
        with self.assertRaises(HTTPException):self.send_multi()
        self.assertEqual(self.db.query(Factura).count(),0)

    def test_xml_dos_pedidos(self):
        import xml.etree.ElementTree as ET
        import copy
        from facturas import NS
        root=ET.fromstring(base.XML)
        linea=copy.deepcopy(root.find('cac:InvoiceLine',NS))
        linea.find('cbc:ID',NS).text='2'
        root.append(linea)
        root.find('cac:TaxTotal/cbc:TaxAmount',NS).text='36.00'
        for name in ['LineExtensionAmount','TaxExclusiveAmount']:
            root.find('cac:LegalMonetaryTotal/cbc:'+name,NS).text='200.00'
        root.find('cac:LegalMonetaryTotal/cbc:PayableAmount',NS).text='236.00'
        result=asyncio.run(registrar_posiciones(orden_compra_id='oc',modo='xml',asignaciones=json.dumps([dict(posicion_id='pos',cantidad=1,linea_xml=0),dict(posicion_id='pos2',cantidad=1,linea_xml=1)]),cabecera=json.dumps({'ruc_receptor':'20999999999'}),pdf=UploadFile(io.BytesIO(base.PDF),filename='f.pdf'),xml=UploadFile(io.BytesIO(ET.tostring(root)),filename='f.xml'),user=self.user,db=self.db))
        self.assertIsNotNone(result['id'])
        self.assertEqual(importes_por_orden(self.db,'a','tenant')['oc2'],118)

if __name__=='__main__': unittest.main()

