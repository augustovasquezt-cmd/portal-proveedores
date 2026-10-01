"""Preparación local del envío. No realiza llamadas a SAP sin un adaptador configurado."""
import json
import os
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from auth import get_current_provider_user
from database import get_db
from models import Factura, FacturaEnvioSAP, Proveedor, OrdenPosicion, OrdenCompra, DocumentoBaseLinea, DocumentoBase
router=APIRouter(prefix='/integracion-sap',tags=['integración SAP'])

class SimulacionECCRequest(BaseModel):
    sociedad: str = Field(min_length=1, max_length=4, examples=['1000'])
    proveedor_sap: str = Field(min_length=1, max_length=20, examples=['0000100001'])
    fecha_contabilizacion: date
    codigos_impuesto: dict[str, str] = Field(examples=[{'18.00': 'V1'}])

@router.get('/estado')
def estado(user:dict=Depends(get_current_provider_user)):
    from sap_adaptadores import PERFILES
    return {'perfiles':[dict(id=p.id,nombre=p.nombre,interfaz=p.interfaz,pendientes=list(p.requisitos)) for p in PERFILES.values()],'habilitada':False,'estado':'pendiente_configuracion','mensaje':'Falta configurar la interfaz SAP y definir si el documento será preliminar o contabilizado.'}

@router.post('/simulador/ecc/facturas/{factura_id}', summary='Simular respuesta ECC sin enviar datos a SAP')
def simular_ecc(factura_id: str, config: SimulacionECCRequest, user:dict=Depends(get_current_provider_user), db:Session=Depends(get_db)):
    """Prepara los datos BAPI de una factura propia y devuelve un acuse ficticio.

    No realiza RFC, no modifica la factura ni la bandeja de salida y no debe
    interpretarse como documento contabilizado en SAP.
    """
    if os.getenv('SAP_SIMULADOR_HABILITADO', '').lower() not in {'1', 'true', 'si', 'sí'}:
        raise HTTPException(status_code=404, detail='El simulador SAP está deshabilitado en este entorno.')
    proveedor = db.query(Proveedor).filter(Proveedor.ruc == user['ruc']).first()
    factura = db.query(Factura).filter(Factura.id == factura_id, Factura.proveedor_id == (proveedor.id if proveedor else None), Factura.cliente_id == user['cliente_id']).first()
    if not factura:
        raise HTTPException(status_code=404, detail='Factura no encontrada.')
    envio = db.get(FacturaEnvioSAP, factura_id)
    if not envio:
        raise HTTPException(status_code=409, detail='La factura aún no tiene un envío preparado para SAP.')
    from sap_ecc_contrato import ErrorContratoECC, preparar_datos_bapi
    try:
        propuesta = preparar_datos_bapi(
            json.loads(envio.contenido),
            sociedad=config.sociedad,
            proveedor_sap=config.proveedor_sap,
            fecha_contabilizacion=config.fecha_contabilizacion.isoformat(),
            codigos_impuesto=config.codigos_impuesto,
        )
    except (ErrorContratoECC, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        'modo': 'simulacion_local',
        'sap_contactado': False,
        'persistido': False,
        'resultado': 'simulado_aceptado',
        'mensaje': 'La estructura BAPI pasó la validación local. No se creó ni contabilizó una factura en SAP.',
        'referencia_simulada': f"SIM-{factura.id[:8].upper()}",
        'bapi': propuesta,
    }

def preparar(db,factura,datos,lineas,ruc,ruc_receptor=None,sociedad_receptora=None):
    items=[]
    for l in lineas:
        p=db.get(OrdenPosicion,l['posicion_id']);o=db.get(OrdenCompra,l['orden_id'])
        ref=None
        if l.get('documento_linea_id'):
            dl=db.get(DocumentoBaseLinea,l['documento_linea_id']);d=db.get(DocumentoBase,dl.documento_id)
            ref=dict(tipo=d.tipo,numero=d.numero,posicion=dl.numero)
        items.append(dict(pedido=o.numero,posicion=p.numero,tipo_posicion=p.tipo or 'material',material=p.material if p.tipo!='servicio' else None,codigo_servicio=p.codigo_servicio if p.tipo=='servicio' else None,paquete_servicio=p.paquete_servicio if p.tipo=='servicio' else None,numero_servicio=p.numero_servicio if p.tipo=='servicio' else None,descripcion=p.descripcion,unidad=p.unidad,cantidad=str(l['cantidad']),precio_unitario=str(l['precio']),tasa_impuesto=str(p.tasa_igv),subtotal=str(l['subtotal']),impuestos=str(l['igv']),total=str(l['total']),referencia=ref))
    society = sociedad_receptora
    society_code = {'id': society.id, 'ruc': society.ruc, 'codigo_sap': society.codigo_sap, 'razon_social': society.razon_social} if society else None
    payload=dict(version=1,factura_portal=factura.id,cliente_id=factura.cliente_id,ruc_emisor=ruc,ruc_receptor=ruc_receptor,sociedad_destino=society_code,serie=datos['serie'],numero=datos['correlativo'],fecha_emision=datos['fecha_emision'].isoformat(),moneda=datos['moneda'],subtotal=str(datos['monto_subtotal']),impuestos=str(datos['monto_igv']),total=str(datos['monto_total']),posiciones=items,adjuntos={'factura_id':factura.id})
    db.add(FacturaEnvioSAP(factura_id=factura.id,cliente_id=factura.cliente_id,estado='pendiente_configuracion',clave_idempotencia='factura-'+factura.id,contenido=json.dumps(payload,ensure_ascii=False)))

