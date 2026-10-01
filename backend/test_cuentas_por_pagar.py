import asyncio
import os
import sys
import types
import unittest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException

# Keep route imports independent of the developer's configured database URL.
database = types.ModuleType("database")
database.get_db = lambda: None
sys.modules["database"] = database
os.environ.setdefault("SECRET_KEY", "unit-test-secret-that-is-not-used-outside-tests-123456")
sys.modules.pop("auth", None)
import auth
from models import Base, Cliente, Sociedad, UsuarioSociedad, Proveedor, ProveedorCliente, ProveedorSociedad, OrdenCompra, UsuarioInterno, Factura, FacturaRegistro, FacturaEvento
from cuentas_por_pagar import resumen, listar, detalle, archivo, accion_factura, datos_maestros, crear_solicitud, listar_solicitudes


class CuentasPorPagarTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Cliente(id='client-1', codigo='client-1', nombre='Cliente 1', activo=True))
        self.db.add(Sociedad(id='soc-1', cliente_id='client-1', ruc='20111111111', razon_social='Sociedad 1', activo=True))
        self.db.add(Proveedor(id="provider", ruc="20999999999", razon_social="Proveedor Demo", email="provider@example.test", password_hash="x"))
        self.ap = UsuarioInterno(id="ap-1", usuario="ap@example.test", nombre="Analista AP", rol="cuentas_por_pagar", cliente_id='client-1', password_hash="x", activo=True)
        self.db.add(self.ap)
        self.db.flush()
        self.db.add(UsuarioSociedad(cliente_id='client-1',usuario_id='ap-1',sociedad_id='soc-1'))
        membership=ProveedorCliente(id='pc-1',proveedor_id='provider',cliente_id='client-1',activo=True);self.db.add(membership)
        self.db.add(ProveedorSociedad(cliente_id='client-1',proveedor_cliente_id='pc-1',sociedad_id='soc-1'))
        self.invoice = Factura(id="inv-1", proveedor_id="provider", cliente_id='client-1', sociedad_id='soc-1', serie="F001", correlativo="0001", monto_subtotal=100, monto_igv=18, monto_total=118, estado="Pendiente de revisión")
        self.db.add(self.invoice)
        self.db.add(FacturaRegistro(factura_id="inv-1", fecha_emision=date.today(), moneda="PEN", ruc_receptor="20111111111", xml=b"<Invoice/>", pdf=b"%PDF"))
        self.db.commit()
        self.user = {"rol": "cuentas_por_pagar", "usuario_id": "ap-1", "usuario": "ap@example.test", "nombre": "Analista AP", "cliente_id":"client-1"}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_bandeja_y_resumen_por_rol(self):
        self.assertEqual(resumen(self.user, self.db)["facturas"]["pendientes"], 1)
        result = listar(estado="pendientes", limit=50, offset=0, _user=self.user, db=self.db)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["proveedor"]["ruc"], "20999999999")
        self.assertTrue(detalle("inv-1", self.user, self.db)["adjuntos"]["pdf"])

    def test_flujo_hasta_pago_y_auditoria(self):
        accion_factura("inv-1", {"accion": "recibir"}, self.user, self.db)
        accion_factura("inv-1", {"accion": "aceptar"}, self.user, self.db)
        paydate = date.today() + timedelta(days=14)
        accion_factura("inv-1", {"accion": "programar_pago", "fecha_pago": paydate.isoformat()}, self.user, self.db)
        accion_factura("inv-1", {"accion": "marcar_pagada"}, self.user, self.db)
        self.db.refresh(self.invoice)
        self.assertEqual(self.invoice.estado, "Pagada")
        self.assertEqual(self.db.query(FacturaEvento).count(), 4)
        self.assertEqual(len(detalle("inv-1", self.user, self.db)["historial"]), 4)

    def test_rechazo_requiere_motivo_y_estado_permitido(self):
        with self.assertRaises(HTTPException) as caught:
            accion_factura("inv-1", {"accion": "rechazar", "comentario": "mal"}, self.user, self.db)
        self.assertEqual(caught.exception.status_code, 400)
        accion_factura("inv-1", {"accion": "rechazar", "comentario": "No coincide el monto del pedido"}, self.user, self.db)
        self.assertEqual(self.invoice.estado, "Rechazada")
        with self.assertRaises(HTTPException) as caught:
            accion_factura("inv-1", {"accion": "marcar_pagada"}, self.user, self.db)
        self.assertEqual(caught.exception.status_code, 409)

    def test_solo_ap_activo_puede_usar_dependencia(self):
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(auth.get_current_ap_user({"rol": "proveedor", "ruc": "20999999999"}, self.db))
        self.assertEqual(caught.exception.status_code, 403)
        self.ap.activo = False
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(auth.get_current_ap_user(self.user, self.db))
        self.assertEqual(caught.exception.status_code, 401)

    def test_login_interno_emite_respuesta_de_rol_ap(self):
        self.ap.password_hash = auth.get_password_hash("Clave-Local-Segura-123!")
        self.db.commit()
        result = asyncio.run(auth.login(auth.LoginRequest(usuario="ap@example.test", password="Clave-Local-Segura-123!"), self.db))
        response = auth.LoginResponse(**result)
        self.assertEqual(response.rol, "cuentas_por_pagar")
        self.assertEqual(response.usuario["id"], "ap-1")
        self.assertIsNone(response.proveedor)

    def test_datos_maestros_y_solicitudes_protegidas_por_usuario(self):
        masters = datos_maestros(self.user, self.db)
        self.assertEqual(masters["proveedores"][0]["ruc"], "20999999999")
        created = crear_solicitud({"categoria": "Consulta de factura", "asunto": "Revisar comprobante F001", "descripcion": "Solicito revisar el estado del comprobante de prueba.", "factura_id": "inv-1"}, self.user, self.db)
        self.assertEqual(created["estado"], "Abierta")
        requests = listar_solicitudes(self.user, self.db)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["factura"], "F001-0001")
        other = {**self.user, "usuario_id": "other-user"}
        self.assertEqual(listar_solicitudes(other, self.db), [])

    def test_ap_user_cannot_list_or_open_another_client_invoice(self):
        self.db.add(Cliente(id='client-2', codigo='client-2', nombre='Cliente 2', activo=True))
        self.db.add(Sociedad(id='soc-2', cliente_id='client-2', ruc='20222222222', razon_social='Sociedad 2', activo=True))
        self.db.add(Factura(id='inv-2', proveedor_id='provider', cliente_id='client-2', sociedad_id='soc-2', serie='F002', correlativo='0002', monto_subtotal=50, monto_igv=9, monto_total=59, estado='Pendiente de revisión'))
        self.db.add(FacturaRegistro(factura_id='inv-2', fecha_emision=date.today(), moneda='PEN', ruc_receptor='20222222222', xml=b'<Invoice/>', pdf=b'%PDF'))
        self.db.commit()
        result = listar(estado='todas', limit=50, offset=0, _user=self.user, db=self.db)
        self.assertEqual(result['total'], 1)
        self.assertEqual([item['id'] for item in result['items']], ['inv-1'])
        with self.assertRaises(HTTPException) as denied:
            detalle('inv-2', self.user, self.db)
        self.assertEqual(denied.exception.status_code, 404)
        with self.assertRaises(HTTPException) as denied_file:
            archivo('inv-2', 'pdf', self.user, self.db)
        self.assertEqual(denied_file.exception.status_code, 404)

    def test_ap_user_cannot_open_invoice_from_unassigned_society(self):
        self.db.add(Sociedad(id='soc-3', cliente_id='client-1', ruc='20333333333', razon_social='Sociedad no asignada', activo=True))
        self.db.add(Factura(id='inv-3', proveedor_id='provider', cliente_id='client-1', sociedad_id='soc-3', serie='F003', correlativo='0003', monto_subtotal=10, monto_igv=1.8, monto_total=11.8, estado='Pendiente de revisión'))
        self.db.add(FacturaRegistro(factura_id='inv-3', fecha_emision=date.today(), moneda='PEN', ruc_receptor='20333333333', xml=b'<Invoice/>', pdf=b'%PDF'))
        self.db.commit()
        self.assertEqual(listar(estado='todas', limit=50, offset=0, _user=self.user, db=self.db)['total'], 1)
        with self.assertRaises(HTTPException) as denied:
            detalle('inv-3', self.user, self.db)
        self.assertEqual(denied.exception.status_code, 404)
        with self.assertRaises(HTTPException) as denied_file:
            archivo('inv-3', 'xml', self.user, self.db)
        self.assertEqual(denied_file.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
