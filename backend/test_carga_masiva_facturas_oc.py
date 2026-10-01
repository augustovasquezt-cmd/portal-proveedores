import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from carga_masiva_facturas_oc import _issue_date, _normal_position, _validate_group, _workbook_rows, build_template
from models import (
    Base, Cliente, Factura, FacturaAsignacion, FacturaEnvioSAP, FacturaLinea,
    FacturaRegistro, OrdenCompra, OrdenPosicion, Proveedor, ProveedorCliente,
    ProveedorSociedad, Sociedad, UsuarioSociedad,
)


class CargaMasivaWorkbookTests(unittest.TestCase):
    def test_template_is_a_readable_xlsx_with_expected_sheets(self):
        workbook = build_template()
        sheets = _workbook_rows(workbook)
        self.assertEqual(set(sheets), {'Facturas', 'Posiciones'})
        self.assertEqual(sheets['Facturas'], [])
        self.assertEqual(sheets['Posiciones'], [])

    def test_order_position_numbers_ignore_leading_zeroes(self):
        self.assertEqual(_normal_position('00010'), _normal_position('10'))
        self.assertEqual(_normal_position('00000'), '0')

    def test_excel_date_cells_and_iso_dates_are_supported(self):
        self.assertEqual(_issue_date('2026-09-30').isoformat(), '2026-09-30')
        self.assertEqual(_issue_date('46295').isoformat(), '2026-09-30')

    def test_invalid_excel_is_rejected(self):
        with self.assertRaises(Exception):
            _workbook_rows(b'not an xlsx')


class CargaMasivaSaveTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Cliente(id='tenant', codigo='tenant', nombre='Cliente demo'))
        self.db.add(Sociedad(id='soc', cliente_id='tenant', ruc='20999999999', razon_social='Sociedad demo'))
        self.db.add(Proveedor(id='supplier', ruc='20123456789', razon_social='Proveedor demo', email='proveedor@test.local', password_hash='hash'))
        membership = ProveedorCliente(id='membership', proveedor_id='supplier', cliente_id='tenant', activo=True)
        self.db.add(membership)
        self.db.add(ProveedorSociedad(id='supplier-soc', cliente_id='tenant', proveedor_cliente_id=membership.id, sociedad_id='soc'))
        self.db.add(UsuarioSociedad(id='ap-soc', cliente_id='tenant', usuario_id='ap-user', sociedad_id='soc'))
        self.db.add(OrdenCompra(id='order', numero='OC-100', proveedor_id='supplier', cliente_id='tenant', sociedad_id='soc', monto_total=118, estado='entregado'))
        self.db.add(OrdenPosicion(id='position', orden_id='order', numero='00010', material='MAT-1', descripcion='Material demo', unidad='NIU', cantidad=1, precio_unitario=100, tasa_igv=18))
        self.db.commit()
        self.user = {'cliente_id': 'tenant', 'usuario_id': 'ap-user', 'rol': 'cuentas_por_pagar'}
        self.header = {
            'clave_factura': 'F001-123', 'ruc_proveedor': '20123456789',
            'razon_social_proveedor': 'Proveedor demo', 'ruc_sociedad': '20999999999',
            'serie': 'F001', 'correlativo': '123', 'fecha_emision': date.today().isoformat(),
            'moneda': 'PEN', 'subtotal': '100.00', 'igv': '18.00', 'total': '118.00',
            'archivo_xml': '', 'archivo_pdf': 'F001-123.pdf',
        }
        self.position = {
            'clave_factura': 'F001-123', 'pedido': 'OC-100', 'posicion': '10',
            'cantidad': '1', 'linea_xml': '', 'tipo_documento': '',
            'numero_documento': '', 'posicion_documento': '',
        }

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_validated_invoice_is_saved_with_pdf_assignments_and_sap_outbox(self):
        result = _validate_group(
            self.db, self.user, self.header, [self.position], {},
            {'f001-123.pdf': ('F001-123.pdf', b'%PDF-1.4 demo %%EOF')}, save=True,
        )
        self.db.commit()

        invoice = self.db.query(Factura).one()
        self.assertEqual(result['estado'], 'registrada')
        self.assertEqual(invoice.estado, 'Pendiente de revisión')
        self.assertEqual(self.db.query(FacturaRegistro).one().pdf, b'%PDF-1.4 demo %%EOF')
        self.assertEqual(self.db.query(FacturaAsignacion).one().cantidad, 1)
        self.assertEqual(self.db.query(FacturaLinea).one().monto_total, 118)
        self.assertEqual(self.db.query(FacturaEnvioSAP).one().estado, 'pendiente_configuracion')


if __name__ == '__main__':
    unittest.main()
