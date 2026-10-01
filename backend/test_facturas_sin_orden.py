import os
import sys
import asyncio
import io
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

os.environ.setdefault('SECRET_KEY', 'unit-test-secret-for-non-production-use-only-123456')
sys.path.insert(0, str(Path(__file__).parent))
# Earlier legacy suites install lightweight auth stubs in sys.modules. The
# parser tests do not exercise auth; add the missing dependency only for import.
import auth
_had_ap_dependency = hasattr(auth, 'get_current_ap_user')
if not _had_ap_dependency:
    auth.get_current_ap_user = lambda: None
from facturas_sin_orden import _parse_xml, cargar_manual, cargar_lote_pdf, accion, _society
if not _had_ap_dependency:
    del auth.get_current_ap_user
from models import Base, Cliente, Sociedad, UsuarioInterno, UsuarioSociedad, FacturaSinOrden, FacturaSinOrdenEvento


def invoice_xml(receiver='20111111111'):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>F001-0000042</cbc:ID><cbc:IssueDate>2026-09-29</cbc:IssueDate>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode><cbc:DocumentCurrencyCode>PEN</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyIdentification><cbc:ID>20123456789</cbc:ID></cac:PartyIdentification><cac:PartyLegalEntity><cbc:RegistrationName>Empresa de Servicios</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID>{receiver}</cbc:ID></cac:PartyIdentification></cac:Party></cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal><cbc:TaxExclusiveAmount>100.00</cbc:TaxExclusiveAmount><cbc:PayableAmount>118.00</cbc:PayableAmount></cac:LegalMonetaryTotal>
  <cac:TaxTotal><cbc:TaxAmount>18.00</cbc:TaxAmount></cac:TaxTotal>
</Invoice>'''.encode()


class FacturasSinOrdenParsingTests(unittest.TestCase):
    def test_extrae_campos_sunat_ubl_sin_referencia_a_pedido(self):
        data = _parse_xml(invoice_xml())
        self.assertEqual(data['proveedor_ruc'], '20123456789')
        self.assertEqual(data['serie'], 'F001')
        self.assertEqual(data['correlativo'], '42')
        self.assertEqual(data['ruc_receptor'], '20111111111')
        self.assertEqual(data['monto_total'], 118)
        self.assertEqual(data['warnings'], [])

    def test_rechaza_dtd_y_entidades(self):
        with self.assertRaises(HTTPException) as caught:
            _parse_xml(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>')
        self.assertEqual(caught.exception.status_code, 400)

    def test_total_no_cuadrado_se_marca_para_revision_y_no_se_descarta(self):
        xml = invoice_xml().replace(b'<cbc:PayableAmount>118.00</cbc:PayableAmount>', b'<cbc:PayableAmount>120.00</cbc:PayableAmount>')
        data = _parse_xml(xml)
        self.assertEqual(data['monto_total'], 120)
        self.assertTrue(data['warnings'])


class FacturasSinOrdenWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Cliente(id='client-ap', codigo='client-ap', nombre='Cliente AP', activo=True))
        self.db.add_all([
            Sociedad(id='soc-assigned', cliente_id='client-ap', ruc='20111111111', razon_social='Sociedad asignada', activo=True),
            Sociedad(id='soc-other', cliente_id='client-ap', ruc='20222222222', razon_social='Sociedad no asignada', activo=True),
        ])
        self.db.add(UsuarioInterno(id='ap-u', usuario='ap@example.test', nombre='Analista AP', rol='cuentas_por_pagar', cliente_id='client-ap', password_hash='x', activo=True))
        self.db.flush()
        self.db.add(UsuarioSociedad(cliente_id='client-ap', usuario_id='ap-u', sociedad_id='soc-assigned'))
        self.db.commit()
        self.user = {'rol': 'cuentas_por_pagar', 'usuario_id': 'ap-u', 'usuario': 'ap@example.test', 'nombre': 'Analista AP', 'cliente_id': 'client-ap'}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_manual(self):
        return asyncio.run(cargar_manual(
            sociedad_id='soc-assigned', proveedor_ruc='20123456789', proveedor_razon_social='Proveedor de luz SAC',
            serie='F001', correlativo='00042', fecha_emision='2026-09-29', moneda='PEN',
            categoria='Servicios básicos', descripcion='Recibo de electricidad', centro_costo='CC-10',
            cuenta_contable='631100', periodo_servicio='09/2026', monto_subtotal='100', monto_igv='18',
            monto_total='118', pdf=UploadFile(filename='recibo.pdf', file=io.BytesIO(b'%PDF-1.4 demo')),
            user=self.user, db=self.db,
        ))

    def test_registro_manual_adjunto_y_aprobacion_auditable(self):
        created = self.create_manual()
        self.assertEqual(created['estado'], 'Pendiente de revisión')
        self.assertTrue(created['tiene_pdf'])
        self.assertEqual(created['centro_costo'], 'CC-10')
        approved = accion(created['id'], {'accion': 'aprobar'}, self.user, self.db)
        self.assertEqual(approved['estado'], 'Aprobada para integración SAP')
        self.assertEqual(self.db.query(FacturaSinOrdenEvento).count(), 1)

    def test_duplicate_y_sociedad_no_asignada_se_rechazan(self):
        self.create_manual()
        with self.assertRaises(HTTPException) as duplicate:
            self.create_manual()
        self.assertEqual(duplicate.exception.status_code, 409)
        with self.assertRaises(HTTPException) as society:
            _society(self.db, self.user, 'soc-other')
        self.assertEqual(society.exception.status_code, 403)

    def test_lote_csv_vincula_el_pdf_por_nombre_y_sin_cuenta_de_proveedor(self):
        content = ('pdf_filename,proveedor_ruc,proveedor_razon_social,serie,correlativo,fecha_emision,moneda,categoria,monto_subtotal,monto_igv,monto_total,centro_costo,cuenta_contable,periodo_servicio,descripcion\n'
                   'recibo-luz.pdf,20123456789,Proveedor electrico,F001,42,2026-09-29,PEN,Servicios básicos,100,18,118,CC-10,631100,09/2026,Luz oficina\n').encode()
        result = asyncio.run(cargar_lote_pdf(
            sociedad_id='soc-assigned', manifiesto=UploadFile(filename='lote.csv', file=io.BytesIO(content)),
            pdf_files=[UploadFile(filename='recibo-luz.pdf', file=io.BytesIO(b'%PDF-1.4 recibo'))],
            user=self.user, db=self.db,
        ))
        self.assertEqual(result['registradas'], 1)
        self.assertEqual(result['items'][0]['factura']['centro_costo'], 'CC-10')
        self.assertEqual(self.db.query(FacturaSinOrden).count(), 1)


if __name__ == '__main__':
    unittest.main()
