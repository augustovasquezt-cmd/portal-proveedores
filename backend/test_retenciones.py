import asyncio
import hashlib
import io
import os
import sys
import types
import unittest
from datetime import date

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, Cliente, Sociedad, ProveedorSociedad, ProveedorCliente, Proveedor

database = types.ModuleType('database')
database.get_db = lambda: None
sys.modules['database'] = database
auth = types.ModuleType('auth')
auth.get_current_user = lambda: None
auth.get_current_provider_user = lambda: None
sys.modules['auth'] = auth

from retenciones import (
    CambioEstado, adjuntar_cdr, actualizar_estado, autorizacion_sap, descargar_archivo,
    listar_certificados, recibir_certificado,
)

XML = b'''<Retention xmlns="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"><cbc:ID>R001-1</cbc:ID><cac:AgentParty><cac:PartyIdentification><cbc:ID>20123456789</cbc:ID></cac:PartyIdentification></cac:AgentParty><cac:ReceiverParty><cac:PartyIdentification><cbc:ID>20999999999</cbc:ID></cac:PartyIdentification></cac:ReceiverParty></Retention>'''
PDF = b'%PDF-1.4\nCRE test\n%%EOF'
CDR = b'''<ApplicationResponse xmlns="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"/>'''


class RetencionesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.tenant=Cliente(id='tenant',codigo='tenant',nombre='Cliente',sap_api_key_hash=hashlib.sha256(('x'*48).encode()).hexdigest())
        self.db.add(self.tenant)
        self.db.add(Sociedad(id='soc',cliente_id='tenant',ruc='20123456789',razon_social='Emisor',activo=True))
        self.db.add_all([
            Proveedor(id='p1', ruc='20999999999', razon_social='Proveedor uno', email='p1@test.local', password_hash='x', activo=True),
            Proveedor(id='p2', ruc='20111111111', razon_social='Proveedor dos', email='p2@test.local', password_hash='x', activo=True),
        ])
        membership=ProveedorCliente(id='pc1',proveedor_id='p1',cliente_id='tenant',activo=True)
        self.db.add(membership);self.db.flush();self.db.add(ProveedorSociedad(id='ps1',cliente_id='tenant',proveedor_cliente_id='pc1',sociedad_id='soc'))
        self.db.commit()
        self.user = {'ruc': '20999999999', 'rol': 'proveedor','cliente_id':'tenant'}
        self.other = {'ruc': '20111111111', 'rol': 'proveedor','cliente_id':'tenant'}
        self.metadata = {
            'evento_origen': 'ECC-1000-R001-1-ISSUED', 'ruc_emisor': '20123456789',
            'ruc_proveedor': '20999999999', 'sociedad': '1000', 'serie': 'R001',
            'correlativo': '0001', 'fecha_emision': date.today().isoformat(),
            'moneda': 'PEN', 'base_retencion': 10000, 'tasa_retencion': 3,
            'importe_retencion': 300, 'fecha_pago': None, 'estado_sunat': 'aceptado',
            'facturas_relacionadas': [{'tipo': '01', 'serie': 'F001', 'numero': '1234', 'fecha_emision': date.today().isoformat(), 'importe': 10000, 'moneda': 'PEN'}],
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def upload(self, data, name):
        return UploadFile(io.BytesIO(data), filename=name)

    def send(self, meta=None, xml=XML, pdf=PDF, cdr=CDR):
        return asyncio.run(recibir_certificado(
            certificado=__import__('json').dumps(meta or self.metadata),
            xml=self.upload(xml, 'certificate.xml'), pdf=self.upload(pdf, 'certificate.pdf'),
            cdr=self.upload(cdr, 'cdr.xml') if cdr else None, tenant=self.tenant, db=self.db,
        ))

    def test_receive_filters_by_provider_and_downloads_original_bytes(self):
        result = self.send()
        self.assertEqual(result['resultado'], 'recibido')
        own = listar_certificados(desde=None, hasta=None, estado=None, sociedad=None, limit=50, offset=0, user=self.user, db=self.db)
        self.assertEqual(own['total'], 1)
        self.assertEqual(own['items'][0]['numero'], 'R001-1')
        self.assertEqual(descargar_archivo(result['id'], 'xml', self.user, self.db).body, XML)
        self.assertEqual(descargar_archivo(result['id'], 'pdf', self.user, self.db).body, PDF)
        with self.assertRaises(HTTPException) as denied:
            descargar_archivo(result['id'], 'pdf', self.other, self.db)
        self.assertEqual(denied.exception.status_code, 404)

    def test_same_event_is_idempotent_and_conflicts_are_rejected(self):
        first = self.send()
        again = self.send()
        self.assertEqual(again['resultado'], 'ya_recibido')
        with self.assertRaises(HTTPException) as conflict:
            self.send(pdf=PDF + b' different')
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(listar_certificados(desde=None, hasta=None, estado=None, sociedad=None, limit=50, offset=0, user=self.user, db=self.db)['total'], 1)

    def test_wait_for_cdr_then_publish_accepted_status(self):
        meta = {**self.metadata, 'evento_origen': 'pending-event', 'estado_sunat': 'pendiente'}
        result = self.send(meta=meta, cdr=None)
        with self.assertRaises(HTTPException) as hidden:
            descargar_archivo(result['id'], 'pdf', self.user, self.db)
        self.assertEqual(hidden.exception.status_code, 409)
        asyncio.run(adjuntar_cdr('20123456789', 'R001', '1', self.upload(CDR, 'cdr.xml'), self.tenant, self.db))
        updated = actualizar_estado(CambioEstado(
            ruc_emisor='20123456789', serie='R001', correlativo='1',
            estado_sunat='aceptado', motivo_estado=None,
        ), self.tenant, self.db)
        self.assertEqual(updated['estado_sunat'], 'aceptado')
        self.assertEqual(descargar_archivo(result['id'], 'cdr', self.user, self.db).body, CDR)

    def test_rejects_invalid_xml_pdf_and_unapproved_issuer(self):
        with self.assertRaises(HTTPException):
            self.send(xml=b'<Invoice/>')
        with self.assertRaises(HTTPException):
            self.send(pdf=b'not pdf')
        meta = {**self.metadata, 'evento_origen': 'other-issuer', 'ruc_emisor': '20222222222'}
        with self.assertRaises(HTTPException) as denied:
            self.send(meta=meta)
        self.assertEqual(denied.exception.status_code, 403)

    def test_requires_integration_secret_and_provider_role(self):
        with self.assertRaises(HTTPException) as bad_secret:
            autorizacion_sap('Bearer incorrect', self.db)
        self.assertEqual(bad_secret.exception.status_code, 401)
        with self.assertRaises(HTTPException) as wrong_role:
            listar_certificados(user={'rol': 'cuentas_por_pagar'}, db=self.db)
        self.assertEqual(wrong_role.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()
