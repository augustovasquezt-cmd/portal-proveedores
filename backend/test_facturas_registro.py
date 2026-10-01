import asyncio
import io
import sys
import types
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from models import Base, Cliente, Sociedad, ProveedorSociedad, ProveedorCliente, Proveedor, OrdenCompra, Factura, FacturaRegistro, OrdenPosicion

database = types.ModuleType('database'); database.get_db = lambda: None
sys.modules['database'] = database
auth = types.ModuleType('auth'); auth.get_current_user = lambda: None; auth.get_current_provider_user = lambda: None
sys.modules['auth'] = auth
from facturas import parse_xml, archivo, detalle
from posiciones import registrar_posiciones
import json

XML = b'''<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"><cbc:ID>F001-0001</cbc:ID><cbc:IssueDate>2026-01-01</cbc:IssueDate><cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>PEN</cbc:DocumentCurrencyCode><cac:AccountingSupplierParty><cac:Party><cac:PartyIdentification><cbc:ID>20999999999</cbc:ID></cac:PartyIdentification></cac:Party></cac:AccountingSupplierParty><cac:TaxTotal><cbc:TaxAmount>18.00</cbc:TaxAmount></cac:TaxTotal><cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount>100.00</cbc:TaxExclusiveAmount><cbc:PayableAmount>118.00</cbc:PayableAmount></cac:LegalMonetaryTotal></Invoice>'''
XML = XML.replace(b'</Invoice>', b'<cac:AccountingCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID>20999999999</cbc:ID></cac:PartyIdentification></cac:Party></cac:AccountingCustomerParty><cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="NIU">1</cbc:InvoicedQuantity><cbc:LineExtensionAmount>100.00</cbc:LineExtensionAmount><cac:TaxTotal><cbc:TaxAmount>18.00</cbc:TaxAmount></cac:TaxTotal><cac:Item><cbc:Description>Producto de prueba</cbc:Description></cac:Item><cac:Price><cbc:PriceAmount>100.00</cbc:PriceAmount></cac:Price></cac:InvoiceLine></Invoice>').replace(b'<cbc:TaxExclusiveAmount>',b'<cbc:LineExtensionAmount>100.00</cbc:LineExtensionAmount><cbc:TaxExclusiveAmount>')
PDF = b'%PDF-1.4\nTest fixture\n%%EOF'

class RegistroTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.db.add(Cliente(id='tenant',codigo='tenant',nombre='Tenant'))
        self.db.add(Sociedad(id='soc',cliente_id='tenant',ruc='20999999999',razon_social='Sociedad destino',activo=True))
        for ident,ruc in [('a','20999999999'),('b','20111111111')]:
            self.db.add(Proveedor(id=ident,ruc=ruc,razon_social=ident,email=ident+'@test.local',password_hash='test'))
        membership=ProveedorCliente(id='pc',proveedor_id='a',cliente_id='tenant',activo=True);self.db.add(membership)
        self.db.add(ProveedorSociedad(id='ps',cliente_id='tenant',proveedor_cliente_id='pc',sociedad_id='soc'))
        self.db.add(OrdenCompra(id='oc',numero='OC1',proveedor_id='a',cliente_id='tenant',sociedad_id='soc',monto_total=200,estado='entregado'))
        self.db.add(OrdenPosicion(id='pos',orden_id='oc',numero='00010',material='M1',descripcion='Producto',unidad='NIU',cantidad=2,precio_unitario=100,tasa_igv=18))
        self.db.commit()
        self.db.flush()
        self.user={'ruc':'20999999999','rol':'proveedor','cliente_id':'tenant'}
    def tearDown(self): self.db.close();self.engine.dispose()
    def submit(self,xml=XML,pdf=PDF,order='oc'):
        return asyncio.run(registrar_posiciones(orden_compra_id=order,modo='xml',asignaciones=json.dumps([{'posicion_id':'pos','cantidad':1,'linea_xml':0}]),cabecera=json.dumps({'ruc_receptor':'20999999999'}),xml=UploadFile(io.BytesIO(xml),filename='f.xml'),pdf=UploadFile(io.BytesIO(pdf),filename='f.pdf'),user=self.user,db=self.db))
    def test_registro_adjuntos_y_duplicado(self):
        r=self.submit()
        detalle_factura=detalle(r['id'],self.user,self.db)
        self.assertEqual(detalle_factura['estado'],'Pendiente de revisión')
        self.assertEqual(detalle_factura['ruc_receptor'],'20999999999')
        self.assertEqual(archivo(r['id'],'xml',self.user,self.db).body,XML)
        with self.assertRaises(HTTPException) as e:self.submit()
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(self.db.query(Factura).count(),1)
        self.assertEqual(self.db.query(FacturaRegistro).count(),1)
        with self.assertRaises(HTTPException) as e:archivo(r['id'],'pdf',{'ruc':'20111111111','cliente_id':'tenant'},self.db)
        self.assertEqual(e.exception.status_code,404)
    def test_saldo(self):
        self.submit()
        with self.assertRaises(HTTPException) as e:self.submit(XML.replace(b'F001-0001',b'F001-2'))
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(self.db.query(Factura).count(),1)
    def test_documentos_invalidos(self):
        for data in [b'invalid',XML.replace(b'20999999999',b'20111111111'), XML.replace(b'118.00',b'119.00'), XML.replace(b'PEN',b'USD'), b'<!DOCTYPE a>'+XML]:
            with self.subTest(data=data[:20]),self.assertRaises(HTTPException):parse_xml(data,self.user['ruc'])
        with self.assertRaises(HTTPException):self.submit(pdf=b'not a pdf')
        self.assertEqual(self.db.query(Factura).count(),0)
    def test_orden_ajena_y_cancelada(self):
        self.db.get(OrdenCompra,'oc').proveedor_id='b';self.db.commit()
        with self.assertRaises(HTTPException) as e:self.submit()
        self.assertEqual(e.exception.status_code,404)
        self.db.get(OrdenCompra,'oc').proveedor_id='a';self.db.get(OrdenCompra,'oc').estado='cancelado';self.db.commit()
        with self.assertRaises(HTTPException):self.submit()

    def test_proveedor_no_puede_ver_factura_ni_archivos_de_otro_cliente(self):
        from datetime import date
        self.db.add(Cliente(id='otro-tenant', codigo='otro-tenant', nombre='Otro cliente', activo=True))
        self.db.add(Sociedad(id='otra-sociedad', cliente_id='otro-tenant', ruc='20111111111', razon_social='Otra sociedad', activo=True))
        self.db.add(Factura(id='factura-ajena', proveedor_id='a', cliente_id='otro-tenant', sociedad_id='otra-sociedad', serie='F099', correlativo='0009', monto_subtotal=10, monto_igv=1.8, monto_total=11.8, estado='Pendiente de revisión'))
        self.db.add(FacturaRegistro(factura_id='factura-ajena', fecha_emision=date.today(), moneda='PEN', ruc_receptor='20111111111', xml=b'<private/>', pdf=b'%PDF-private'))
        self.db.commit()
        provider_user = {'ruc': '20999999999', 'rol': 'proveedor', 'cliente_id': 'tenant'}
        with self.assertRaises(HTTPException) as hidden:
            detalle('factura-ajena', provider_user, self.db)
        self.assertEqual(hidden.exception.status_code, 404)
        for kind in ('xml', 'pdf'):
            with self.subTest(kind=kind), self.assertRaises(HTTPException) as hidden_file:
                archivo('factura-ajena', kind, provider_user, self.db)
            self.assertEqual(hidden_file.exception.status_code, 404)

    def test_revision_completa_y_referencia(self):
        from xml_review import review_xml
        order=self.db.get(OrdenCompra,'oc')
        review=review_xml(XML,self.user['ruc'],order,self.db)
        self.assertTrue(review['puede_enviar'])
        self.assertEqual(review['lineas'][0]['Descripción'],'Producto de prueba')
        self.assertTrue(len(review['campos'])>10)
        incorrecto=XML.replace(b'</Invoice>',b'<cac:OrderReference><cbc:ID>OTRO-PEDIDO</cbc:ID></cac:OrderReference></Invoice>')
        self.assertFalse(review_xml(incorrecto,self.user['ruc'],order,self.db)['puede_enviar'])
        with self.assertRaises(HTTPException):self.submit(incorrecto)
    def test_revision_importes_invalidos_visibles(self):
        from xml_review import review_xml
        review=review_xml(XML.replace(b'118.00',b'999.00'),self.user['ruc'],self.db.get(OrdenCompra,'oc'),self.db)
        self.assertFalse(review['puede_enviar'])
        self.assertEqual(review['totales']['Importe a pagar'],'999.00')

if __name__=='__main__': unittest.main()



