import sys
import types
import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, Cliente, Sociedad, UsuarioSociedad, Proveedor, ProveedorCliente, ProveedorSociedad, RegistroAuditoria, UsuarioInterno

database = types.ModuleType('database')
database.get_db = lambda: None
sys.modules['database'] = database
auth = types.ModuleType('auth')
auth.get_current_admin_user = lambda: None
auth.get_password_hash = lambda value: 'hash:' + value
sys.modules['auth'] = auth

from administracion import (
    CrearProveedor, CrearUsuarioInterno, EstadoCuenta, cambiar_estado_interno,
    cambiar_estado_proveedor, crear_proveedor, crear_usuario_interno,
    listar_usuarios, restablecer_password_interno,
)


class AdministracionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Cliente(id='c1', codigo='cliente1', nombre='Cliente Uno', max_administradores=1, max_cuentas_por_pagar=2, max_proveedores=2, max_sociedades=2))
        self.db.add(Sociedad(id='s1', cliente_id='c1', ruc='20111111111', razon_social='Sociedad Uno', activo=True))
        self.admin = {'usuario_id': 'admin-id', 'usuario': 'admin@empresa.com', 'rol': 'administrador', 'cliente_id':'c1'}
        self.db.add(UsuarioInterno(id='admin-id', usuario=self.admin['usuario'], nombre='Admin', rol='administrador', cliente_id='c1', password_hash='hash:x', activo=True))
        self.db.add(UsuarioInterno(id='ap-id', usuario='ap@empresa.com', nombre='Analista', rol='cuentas_por_pagar', cliente_id='c1', password_hash='hash:x', activo=True))
        self.db.add(Proveedor(id='provider-id', ruc='20999999999', razon_social='Proveedor', email='p@proveedor.pe', password_hash='hash:x', activo=True))
        self.db.flush()
        link=ProveedorCliente(id='pc1',proveedor_id='provider-id',cliente_id='c1',activo=True);self.db.add(link)
        self.db.add(ProveedorSociedad(id='ps1',cliente_id='c1',proveedor_cliente_id=link.id,sociedad_id='s1'))
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_admin_creates_accounts_with_temp_password_and_role_not_selectable(self):
        internal = crear_usuario_interno(CrearUsuarioInterno(usuario='nuevo@empresa.com', nombre='Nuevo Analista', sociedades_ids=['s1']), self.admin, self.db)
        provider = crear_proveedor(CrearProveedor(ruc='20122222222', razon_social='Nuevo Proveedor SAC', email='nuevo@proveedor.pe', sociedades_ids=['s1']), self.admin, self.db)
        self.assertEqual(self.db.get(UsuarioInterno, internal['id']).rol, 'cuentas_por_pagar')
        self.assertTrue(self.db.get(UsuarioInterno, internal['id']).cambio_password_requerido)
        self.assertTrue(self.db.get(Proveedor, provider['proveedor_id']).cambio_password_requerido)
        self.assertEqual(self.db.query(RegistroAuditoria).count(), 2)
        self.assertNotIn('password_temporal', listar_usuarios(self.admin, self.db)['usuarios_internos'][0])
        with self.assertRaises(ValidationError):
            CrearUsuarioInterno(usuario='otro@empresa.com', nombre='Admin', rol='administrador')

    def test_only_customer_admin_can_disable_and_reset_managed_accounts(self):
        changed = cambiar_estado_interno('ap-id', EstadoCuenta(activo=False), self.admin, self.db)
        self.assertFalse(changed['activo'])
        temp = restablecer_password_interno('ap-id', self.admin, self.db)
        self.assertTrue(temp['password_temporal'])
        self.assertTrue(self.db.get(UsuarioInterno, 'ap-id').cambio_password_requerido)
        provider = cambiar_estado_proveedor('pc1', EstadoCuenta(activo=False), self.admin, self.db)
        self.assertFalse(provider['activo'])
        with self.assertRaises(HTTPException) as admin_protected:
            cambiar_estado_interno('admin-id', EstadoCuenta(activo=False), self.admin, self.db)
        self.assertEqual(admin_protected.exception.status_code, 404)

    def test_global_provider_is_linked_to_second_client_without_password_reset(self):
        self.db.add(Cliente(id='c2', codigo='cliente2', nombre='Cliente Dos', max_administradores=1, max_cuentas_por_pagar=1, max_proveedores=2, max_sociedades=1))
        self.db.add(Sociedad(id='s2', cliente_id='c2', ruc='20133333333', razon_social='Sociedad Dos', activo=True))
        self.db.commit()
        second_admin = {**self.admin, 'cliente_id': 'c2'}
        original_hash = self.db.get(Proveedor, 'provider-id').password_hash
        result = crear_proveedor(CrearProveedor(ruc='20999999999', razon_social='Proveedor', email='p@proveedor.pe', sociedades_ids=['s2']), second_admin, self.db)
        self.assertEqual(result['proveedor_id'], 'provider-id')
        self.assertIsNone(result['password_temporal'])
        self.assertEqual(self.db.get(Proveedor, 'provider-id').password_hash, original_hash)
        self.assertEqual(self.db.query(ProveedorCliente).filter_by(proveedor_id='provider-id').count(), 2)
        self.assertEqual(self.db.query(ProveedorSociedad).filter_by(cliente_id='c2').one().sociedad_id, 's2')

    def test_customer_admin_cannot_exceed_supplier_quota(self):
        # One existing membership plus one new supplier fills this customer's quota.
        crear_proveedor(CrearProveedor(ruc='20122222222', razon_social='Nuevo Proveedor SAC', email='nuevo@proveedor.pe', sociedades_ids=['s1']), self.admin, self.db)
        with self.assertRaises(HTTPException) as caught:
            crear_proveedor(CrearProveedor(ruc='20144444444', razon_social='Tercer Proveedor SAC', email='tercero@proveedor.pe', sociedades_ids=['s1']), self.admin, self.db)
        self.assertEqual(caught.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
