import sys
import types
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

database = types.ModuleType('database'); database.get_db = lambda: None; sys.modules['database'] = database
auth = types.ModuleType('auth'); auth.get_current_ivs_admin_user = lambda: None; auth.get_current_provider_user = lambda: None; auth.get_password_hash = lambda value: 'hash:'+value; sys.modules['auth'] = auth
from models import Base, UsuarioInterno, Sociedad
from ivs import ClienteEntrada, ClienteActualizacion, SociedadEntrada, AdministradorEntrada, Cuotas, EstadoSociedad, crear, actualizar_cliente, crear_sociedad, crear_administrador, actualizar_cupos, estado_sociedad
from fastapi import HTTPException


class IvsProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(self.engine); self.db=Session(self.engine)
        self.user={'usuario_id':'ivs','usuario':'ivs@example.test','rol':'administrador_ivs'}
        self.db.add(UsuarioInterno(id='ivs',usuario='ivs@example.test',nombre='IVS',rol='administrador_ivs',password_hash='x')); self.db.commit()

    def tearDown(self): self.db.close(); self.engine.dispose()

    def test_ivs_controls_quotas_societies_and_admin_accounts(self):
        client=crear(ClienteEntrada(codigo='cliente-demo',nombre='Cliente Demo',ruc_principal='20111111111',razon_social_principal='Sociedad Uno',max_administradores=1,max_cuentas_por_pagar=2,max_proveedores=3,max_sociedades=2),self.user,self.db)
        principal=self.db.query(Sociedad).filter_by(cliente_id=client['id'],es_principal=True).one()
        self.assertEqual(principal.ruc,'20111111111')
        self.assertEqual(client['sociedad_principal']['id'],principal.id)
        society=crear_sociedad(client['id'],SociedadEntrada(ruc='20122222222',razon_social='Sociedad Dos',codigo_sap='2000'),self.user,self.db)
        admin=crear_administrador(client['id'],AdministradorEntrada(usuario='admin@example.com',nombre='Administrador'),self.user,self.db)
        self.assertEqual(self.db.get(UsuarioInterno,admin['id']).rol,'administrador')
        self.assertEqual(len(society['id']),36)
        with self.assertRaises(HTTPException) as e:
            crear_sociedad(client['id'],SociedadEntrada(ruc='20133333333',razon_social='Sociedad Tres'),self.user,self.db)
        self.assertEqual(e.exception.status_code,409)
        estado_sociedad(client['id'], society['id'], EstadoSociedad(activo=False), self.user, self.db)
        self.assertFalse(self.db.get(Sociedad, society['id']).activo)
        reactivated=estado_sociedad(client['id'], society['id'], EstadoSociedad(activo=True), self.user, self.db)
        self.assertTrue(reactivated['activo'])
        with self.assertRaises(HTTPException) as e:
            estado_sociedad(client['id'],principal.id,EstadoSociedad(activo=False),self.user,self.db)
        self.assertEqual(e.exception.status_code,409)
        with self.assertRaises(HTTPException) as e:
            crear_administrador(client['id'],AdministradorEntrada(usuario='admin2@example.com',nombre='Segundo administrador'),self.user,self.db)
        self.assertEqual(e.exception.status_code,409)
        updated=actualizar_cupos(client['id'],Cuotas(max_administradores=2,max_cuentas_por_pagar=2,max_proveedores=3,max_sociedades=2),self.user,self.db)
        self.assertEqual(updated['cupos']['administradores']['maximo'],2)

    def test_ivs_can_edit_customer_identity_and_cannot_duplicate_code(self):
        client=crear(ClienteEntrada(codigo='empresa-uno',nombre='Empresa Uno',ruc_principal='20111111111',razon_social_principal='Empresa Uno SAC'),self.user,self.db)
        result=actualizar_cliente(client['id'],ClienteActualizacion(codigo='grupo-uno',nombre='Grupo Uno SAC'),self.user,self.db)
        self.assertEqual(result['codigo'],'grupo-uno')
        self.assertEqual(result['nombre'],'Grupo Uno SAC')
        other=crear(ClienteEntrada(codigo='empresa-dos',nombre='Empresa Dos',ruc_principal='20122222222',razon_social_principal='Empresa Dos SAC'),self.user,self.db)
        with self.assertRaises(HTTPException) as e:
            actualizar_cliente(other['id'],ClienteActualizacion(codigo='grupo-uno',nombre='Duplicado'),self.user,self.db)
        self.assertEqual(e.exception.status_code,409)

    def test_client_code_is_normalized_from_uppercase(self):
        payload = ClienteEntrada(codigo=' IVS ', nombre='IVS Consulting', ruc_principal='20611753137', razon_social_principal='Information Value Solution S.a.C')
        self.assertEqual(payload.codigo, 'ivs')
        client = crear(payload, self.user, self.db)
        self.assertEqual(client['codigo'], 'ivs')


if __name__=='__main__': unittest.main()
