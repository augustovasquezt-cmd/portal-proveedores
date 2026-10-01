import asyncio
import io
import json
import unittest
import test_facturas_registro as base
from fastapi import UploadFile,HTTPException
from models import Factura,FacturaEnvioSAP,FacturaAsignacion
from posiciones import registrar_posiciones
from sap_adaptadores import PERFILES,adaptador
class ValidacionSAPTests(base.RegistroTests):
    def request(self,solo,total=118):
        cab=dict(serie='F007',correlativo='1',fecha_emision='2026-01-01',moneda='PEN',ruc_emisor='20999999999',ruc_receptor='20999999999',monto_subtotal=100,monto_igv=18,monto_total=total)
        return asyncio.run(registrar_posiciones(orden_compra_id='oc',modo='pdf',asignaciones=json.dumps([dict(posicion_id='pos',cantidad=1)]),cabecera=json.dumps(cab),pdf=UploadFile(io.BytesIO(base.PDF),filename='f.pdf'),xml=None,user=self.user,db=self.db,validar_solo=solo))
    def test_validar_no_guarda_ni_reserva(self):
        self.assertTrue(self.request(True)['valida'])
        self.assertEqual(self.db.query(Factura).count(),0)
        self.assertEqual(self.db.query(FacturaAsignacion).count(),0)
        self.assertEqual(self.db.query(FacturaEnvioSAP).count(),0)
    def test_invalido_no_prepara_envio(self):
        with self.assertRaises(HTTPException):self.request(False,119)
        self.assertEqual(self.db.query(FacturaEnvioSAP).count(),0)
    def test_guardado_atomico_y_duplicado(self):
        self.request(True);r=self.request(False)
        envio=self.db.get(FacturaEnvioSAP,r['id'])
        self.assertEqual(envio.estado,'pendiente_configuracion')
        self.assertIsNone(envio.documento_sap)
        payload=json.loads(envio.contenido)
        self.assertEqual(payload['posiciones'][0]['pedido'],'OC1')
        self.assertEqual(payload['posiciones'][0]['posicion'],'00010')
        with self.assertRaises(HTTPException):self.request(False)
        self.assertEqual(self.db.query(FacturaEnvioSAP).count(),1)
    def test_perfiles_no_simulan_envios(self):
        self.assertEqual(set(PERFILES),{'ecc','s4hana','s4hana_grow'})
        for perfil in PERFILES:
            with self.assertRaises(RuntimeError):adaptador(perfil).enviar({},'test')
if __name__=='__main__':unittest.main()
