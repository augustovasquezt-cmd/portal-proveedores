import asyncio
import io
import json
import unittest
from datetime import date
import test_facturas_registro as base
from fastapi import UploadFile,HTTPException
from models import DocumentoBase,DocumentoBaseLinea,Factura,OrdenCompra,FacturaOrigen
from posiciones import registrar_posiciones
from documentos_base import listar,pendiente

class DocumentosTests(base.RegistroTests):
    def setUp(self):
        super().setUp()
        self.db.get(OrdenCompra,'oc').monto_total=236
        for i,tipo,estado in [('1','mercancia','recibido'),('2','mercancia','recibido'),('3','servicio','aceptado'),('4','guia','despachado')]:
            self.db.add(DocumentoBase(id='d'+i,proveedor_id='a',cliente_id='tenant',tipo=tipo,numero='DEMO-'+i,estado=estado,fecha=date(2026,1,1)))
            self.db.add(DocumentoBaseLinea(id='l'+i,documento_id='d'+i,posicion_id='pos',numero='1',cantidad=1))
        self.db.commit()
    def send(self,rows,net=100,num='1'):
        header=dict(serie='F008',correlativo=num,fecha_emision='2026-01-01',moneda='PEN',ruc_emisor='20999999999',ruc_receptor='20999999999',monto_subtotal=net,monto_igv=net*.18,monto_total=net*1.18)
        return asyncio.run(registrar_posiciones(orden_compra_id='oc',modo='pdf',asignaciones=json.dumps(rows),cabecera=json.dumps(header),pdf=UploadFile(io.BytesIO(base.PDF),filename='f.pdf'),xml=None,user=self.user,db=self.db))
    def row(self,lid,q=1):return dict(posicion_id='pos',documento_linea_id=lid,cantidad=q)
    def test_saldo(self):
        self.db.get(OrdenCompra,'oc').monto_total=200;self.db.commit()
        super().test_saldo()
    def test_dos_recepciones_misma_posicion(self):
        self.send([self.row('l1'),self.row('l2')],net=200)
        self.assertEqual(self.db.query(FacturaOrigen).count(),2)
        self.assertEqual(listar('mercancia',self.user,self.db),[])
    def test_limite_documento_y_atomicidad(self):
        with self.assertRaises(HTTPException):self.send([self.row('l1',2)],net=200)
        self.assertEqual(self.db.query(Factura).count(),0)
    def test_consumo_parcial(self):
        self.send([self.row('l1',.5)],net=50)
        self.assertEqual(float(pendiente(self.db,self.db.get(DocumentoBaseLinea,'l1'))),.5)
        with self.assertRaises(HTTPException):self.send([self.row('l1')],num='2')
    def test_servicio_y_guia(self):
        from models import OrdenPosicion
        self.db.get(OrdenPosicion,'pos').tipo='servicio';self.db.commit()
        self.send([self.row('l3')])
        self.assertEqual(self.db.query(FacturaOrigen).count(),1)
    def test_guia_de_remision(self):
        self.send([self.row('l4')])
        self.assertEqual(self.db.query(FacturaOrigen).count(),1)
    def test_posicion_de_servicio_exige_hes_y_conserva_linea(self):
        from models import OrdenPosicion
        position=self.db.get(OrdenPosicion,'pos')
        position.tipo='servicio';position.material='';position.codigo_servicio='SRV-01'
        position.paquete_servicio='0000123456';position.numero_servicio='0000000010'
        self.db.commit()
        with self.assertRaises(HTTPException):self.send([dict(posicion_id='pos',cantidad=1)])
        with self.assertRaises(HTTPException):self.send([self.row('l1')])
        self.send([self.row('l3')])
        self.assertEqual(self.db.query(FacturaOrigen).count(),1)
    def test_documento_ajeno_o_no_aceptado(self):
        d=self.db.get(DocumentoBase,'d1');d.proveedor_id='b';self.db.commit()
        self.assertEqual(len(listar('mercancia',self.user,self.db)),1)
        with self.assertRaises(HTTPException):self.send([self.row('l1')])
        d=self.db.get(DocumentoBase,'d3');d.estado='pendiente';self.db.commit()
        self.assertEqual(listar('servicio',self.user,self.db),[])
        with self.assertRaises(HTTPException):self.send([self.row('l3')])
    def test_no_mezclar_bases(self):
        with self.assertRaises(HTTPException):self.send([self.row('l1'),self.row('l3')],net=200)

if __name__=='__main__':unittest.main()

