import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from fastapi import APIRouter, Depends, Form, File, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_provider_user
from models import OrdenCompra, OrdenPosicion, Factura, FacturaAsignacion, FacturaRegistro, FacturaLinea, DocumentoBase, DocumentoBaseLinea, FacturaOrigen
from facturas import fail, proveedor_actual, parse_xml, MAX_FILE
from xml_review import review_xml

router=APIRouter(tags=['registro por posiciones'])
EXCLUIDOS=['anulada','anulado','rechazada','rechazado','cancelada','cancelado']
def money(v): return Decimal(v).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
def number(v):
    try:
        d=Decimal(str(v))
        if not d.is_finite() or d<0 or d>=Decimal('10000000000'): raise ValueError()
        return d
    except (InvalidOperation,ValueError,TypeError): fail('Valor numérico inválido.')

def posiciones(db, orden):
    rows=db.query(OrdenPosicion).filter(OrdenPosicion.orden_id==orden.id).order_by(OrdenPosicion.numero).all()
    servicios={};lineas_servicio=[]
    ids_servicio=[p.id for p in rows if p.tipo=='servicio']
    if ids_servicio:
        lineas_servicio=db.query(DocumentoBaseLinea).join(DocumentoBase,DocumentoBase.id==DocumentoBaseLinea.documento_id).filter(DocumentoBaseLinea.posicion_id.in_(ids_servicio),DocumentoBase.tipo=='servicio',DocumentoBase.estado=='aceptado').all()
        consumos={}
        if lineas_servicio:
            consumos=dict(db.query(FacturaOrigen.documento_linea_id,func.coalesce(func.sum(FacturaAsignacion.cantidad),0)).join(FacturaAsignacion,FacturaAsignacion.id==FacturaOrigen.asignacion_id).join(Factura,Factura.id==FacturaAsignacion.factura_id).filter(FacturaOrigen.documento_linea_id.in_([l.id for l in lineas_servicio]),func.lower(func.trim(Factura.estado)).notin_(EXCLUIDOS)).group_by(FacturaOrigen.documento_linea_id).all())
        for linea in lineas_servicio:
            accepted,remaining=servicios.get(linea.posicion_id,(Decimal(0),Decimal(0)))
            servicios[linea.posicion_id]=(accepted+linea.cantidad,remaining+max(linea.cantidad-consumos.get(linea.id,Decimal(0)),Decimal(0)))
    output=[]
    for p in rows:
        qty,total=db.query(func.coalesce(func.sum(FacturaAsignacion.cantidad),0),func.coalesce(func.sum(FacturaAsignacion.total),0)).join(Factura,Factura.id==FacturaAsignacion.factura_id).filter(FacturaAsignacion.posicion_id==p.id,func.lower(func.trim(Factura.estado)).notin_(EXCLUIDOS)).one()
        net=money(p.cantidad*p.precio_unitario);gross=net+money(net*p.tasa_igv/100)
        service_accepted,service_billable=servicios.get(p.id,(Decimal(0),Decimal(0)))
        if p.tipo=='servicio':
            service_billable=min(service_billable,max(p.cantidad-qty,Decimal(0)))
        qty_billable=service_billable if p.tipo=='servicio' else max(p.cantidad-qty,Decimal(0))
        billable_amount=money(qty_billable*p.precio_unitario);billable_amount+=money(billable_amount*p.tasa_igv/100)
        output.append(dict(id=p.id,numero=p.numero,material=p.material or '',tipo=p.tipo or 'material',codigo_servicio=p.codigo_servicio,paquete_servicio=p.paquete_servicio,numero_servicio=p.numero_servicio,descripcion=p.descripcion,unidad=p.unidad,cantidad=float(p.cantidad),cantidad_servicio_aceptada=float(service_accepted),cantidad_facturable=float(qty_billable),saldo_facturable=float(billable_amount),requiere_aceptacion_servicio=p.tipo=='servicio',precio_unitario=float(p.precio_unitario),tasa_igv=float(p.tasa_igv),total=float(gross),cantidad_facturada=float(qty),cantidad_pendiente=float(max(p.cantidad-qty,0)),saldo=float(max(gross-total,0))))
    # Las facturas históricas sin asignación no pueden distribuirse de forma inventada.
    antiguas=db.query(Factura).filter(Factura.orden_compra_id==orden.id,func.lower(func.trim(Factura.estado)).notin_(EXCLUIDOS),~db.query(FacturaAsignacion.id).filter(FacturaAsignacion.factura_id==Factura.id).exists()).count()
    return dict(posiciones=output,bloqueo='Existen facturas anteriores sin asignación por posición. Deben conciliarse antes de continuar.' if antiguas else 'El pedido no tiene posiciones cargadas.' if not rows else '')

@router.get('/ordenes/{oid}/posiciones')
def listar(oid:str,user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    p=proveedor_actual(db,user)
    o=db.query(OrdenCompra).filter(OrdenCompra.id==oid,OrdenCompra.proveedor_id==p.id,OrdenCompra.cliente_id==user['cliente_id']).first()
    if not o: fail('Orden no encontrada.',404)
    return posiciones(db,o)

def validar(db,o,datos,asignaciones,revision=None):
    pedidos=o if isinstance(o,list) else [o]
    disponibles={}
    for pedido in pedidos:
        state=posiciones(db,pedido)
        if state['bloqueo']: fail(pedido.numero+': '+state['bloqueo'])
        for p in state['posiciones']: disponibles[p['id']]={**p,'orden_id':pedido.id,'orden_numero':pedido.numero}
    if not isinstance(asignaciones,list) or not asignaciones: fail('Selecciona al menos una posición.')
    usadas=set();xml_usadas=set();lineas=[];cantidades={};importes_posicion={}
    for a in asignaciones:
        if not isinstance(a,dict): fail('Asignación inválida.')
        pid=a.get('posicion_id');p=disponibles.get(pid)
        clave=(pid,a.get('documento_linea_id'))
        if not p or clave in usadas: fail('Posición o línea de documento repetida o ajena al pedido.')
        usadas.add(clave)
        q=number(a.get('cantidad'))
        if q<=0 or q!=q.quantize(Decimal('.0001')) or q>number(p['cantidad_pendiente']): fail(f"Cantidad inválida o superior al pendiente en posición {p['numero']}.")
        subtotal=money(q*number(p['precio_unitario']));igv=money(subtotal*number(p['tasa_igv'])/100);total=subtotal+igv
        cantidades[pid]=cantidades.get(pid,Decimal(0))+q
        importes_posicion[pid]=importes_posicion.get(pid,Decimal(0))+total
        if cantidades[pid]>number(p['cantidad_pendiente']): fail('La suma de documentos supera la cantidad pendiente de la posición.')
        if importes_posicion[pid]>number(p['saldo']): fail(f"Importe superior al saldo de posición {p['numero']}.")
        idx=None
        if revision is not None:
            idx=a.get('linea_xml')
            if not isinstance(idx,int) or idx<0 or idx>=len(revision['lineas']) or idx in xml_usadas: fail('Relaciona cada línea del XML una sola vez.')
            xml_usadas.add(idx);l=revision['lineas'][idx]
            if l.get('Pedido') and l['Pedido']!=p['orden_numero']: fail('La referencia de pedido de la línea XML no coincide.')
            if l.get('Posición pedido') and l['Posición pedido'].lstrip('0')!=p['numero'].lstrip('0'): fail('La posición indicada en el XML no coincide.')
            if number(l['Cantidad'])!=q or number(l['Valor unitario'])!=number(p['precio_unitario']) or number(l['Valor de venta'])!=subtotal or number(l['Impuestos'] or 0)!=igv: fail(f"Cantidad, precio o impuestos del XML no coinciden con posición {p['numero']}.")
            if l['Unidad']!=p['unidad']: fail(f"Unidad del XML diferente a posición {p['numero']}.")
            codigo_pedido=p['codigo_servicio'] if p['tipo']=='servicio' else p['material']
            if l['Código'] and codigo_pedido and l['Código']!=codigo_pedido: fail(f"Código del XML diferente a posición {p['numero']}.")
        if p['tipo']=='servicio' and not a.get('documento_linea_id'):
            fail(f"La posición de servicio {p['numero']} debe facturarse contra una hoja de entrada de servicios aceptada.")
        lineas.append(dict(documento_linea_id=a.get('documento_linea_id'),orden_id=p['orden_id'],posicion_id=pid,linea_xml=idx,cantidad=q,subtotal=subtotal,igv=igv,total=total,descripcion=p['descripcion'],precio=number(p['precio_unitario']),material=p['material'],codigo_producto=p['codigo_servicio'] if p['tipo']=='servicio' else p['material']))
    if revision is not None and len(xml_usadas)!=len(revision['lineas']): fail('Asigna todas las líneas del XML a posiciones del pedido.')
    for field,key in [('monto_subtotal','subtotal'),('monto_igv','igv'),('monto_total','total')]:
        if number(datos[field])!=sum(l[key] for l in lineas): fail('Los importes de la factura no coinciden con las posiciones seleccionadas.')
    return lineas

@router.post('/facturas/registrar-posiciones',status_code=201)
async def registrar_posiciones(orden_compra_id:str=Form(...),modo:str=Form(...),asignaciones:str=Form(...),cabecera:str=Form('{}'),pdf:UploadFile=File(...),xml:UploadFile|None=File(None),user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db),validar_solo:bool=False):
    from facturas import re
    try: asign=json.loads(asignaciones); manual=json.loads(cabecera)
    except (ValueError,TypeError): fail('Datos de registro inválidos.')
    pdf_data=await pdf.read(MAX_FILE+1)
    if len(pdf_data)>MAX_FILE or not pdf_data.startswith(b'%PDF-') or b'%%EOF' not in pdf_data[-1024:]: fail('Adjunta un PDF válido de hasta 5 MB.')
    xml_data=b'';revision=None
    try:
        proveedor=proveedor_actual(db,user,lock=True)
        if not isinstance(manual,dict): fail('Cabecera inválida.')
        from facturas import obtener_sociedad_receptora
        sociedad_receptora=obtener_sociedad_receptora(manual.get('ruc_receptor'),user,db)
        ruc_receptor=sociedad_receptora.ruc
        if not isinstance(asign,list) or not asign or any(not isinstance(a,dict) for a in asign): fail('Selecciona posiciones válidas.')
        ids=[a.get('posicion_id') for a in asign]
        if any(not isinstance(i,str) for i in ids): fail('Posición inválida.')
        rows=db.query(OrdenPosicion).join(OrdenCompra, OrdenCompra.id == OrdenPosicion.orden_id).filter(OrdenPosicion.id.in_(ids), OrdenCompra.cliente_id == user['cliente_id']).all()
        if len(rows)!=len(set(ids)): fail('Posición no encontrada.',404)
        order_ids=sorted({p.orden_id for p in rows})
        pedidos=db.query(OrdenCompra).filter(OrdenCompra.id.in_(order_ids),OrdenCompra.proveedor_id==proveedor.id,OrdenCompra.cliente_id==user['cliente_id']).order_by(OrdenCompra.id).with_for_update().all()
        if len(pedidos)!=len(order_ids): fail('Uno de los pedidos no pertenece al proveedor.',404)
        if any(o.sociedad_id != sociedad_receptora.id for o in pedidos):
            fail('La sociedad receptora seleccionada no coincide con una o más órdenes. Las órdenes sin sociedad asignada deben sincronizarse desde SAP antes de facturarse.', 409)
        if any(o.estado.lower() in EXCLUIDOS for o in pedidos): fail('Uno de los pedidos está cancelado.')
        if modo=='xml':
            if xml is None: fail('Adjunta el XML.')
            xml_data=await xml.read(MAX_FILE+1);datos=parse_xml(xml_data,user['ruc'])
            revision=review_xml(xml_data,user['ruc'],None,db,multipedido=True,ruc_receptor=ruc_receptor,cliente_id=user['cliente_id'])
            referencia=revision['cabecera']['Pedido XML']
            if referencia and referencia not in [o.numero for o in pedidos]: fail('La referencia del XML no corresponde a los pedidos seleccionados.')
            errores=[v['detalle'] for v in revision['validaciones'] if v['estado']=='error']
            if errores: fail(' '.join(errores), 409 if any(v['estado']=='error' and v['campo'] in ['Duplicados','Saldo disponible'] for v in revision['validaciones']) else 400)
        elif modo=='pdf':
            serie=str(manual.get('serie','')).strip().upper();correlativo=str(manual.get('correlativo','')).strip()
            if not re.fullmatch(r'[A-Z0-9]{1,10}',serie) or not re.fullmatch(r'[0-9]{1,10}',correlativo) or int(correlativo)<1: fail('Serie y correlativo inválidos.')
            try: fecha=date.fromisoformat(manual.get('fecha_emision',''))
            except (ValueError,TypeError): fail('Fecha inválida.')
            if fecha>date.today(): fail('La fecha no puede ser futura.')
            if manual.get('moneda')!='PEN': fail('El pedido está en PEN.')
            if manual.get('ruc_emisor')!=user['ruc'] or manual.get('ruc_receptor')!=ruc_receptor: fail('El RUC emisor debe coincidir con tu usuario y el receptor con la sociedad seleccionada.')
            datos=dict(serie=serie,correlativo=str(int(correlativo)),fecha_emision=fecha,moneda='PEN',**{k:number(manual.get(k)) for k in ['monto_subtotal','monto_igv','monto_total']})
        else: fail('Modo de registro inválido.')
        existentes=db.query(Factura).filter(Factura.cliente_id==user['cliente_id'],Factura.proveedor_id==proveedor.id,func.upper(Factura.serie)==datos['serie']).all()
        if any(f.correlativo.isdigit() and int(f.correlativo)==int(datos['correlativo']) for f in existentes): fail('Esta factura ya está registrada.',409)
        from documentos_base import validar_origenes
        validar_origenes(db,asign,proveedor.id, user['cliente_id'])
        lineas=validar(db,pedidos,datos,asign,revision)
        from saldos import importes_por_orden
        importes=importes_por_orden(db,proveedor.id,user['cliente_id'])
        for o in pedidos:
            aplicado=sum(l['total'] for l in lineas if l['orden_id']==o.id)
            if aplicado>o.monto_total-importes.get(o.id,0): fail('El importe supera el saldo del pedido '+o.numero,409)
        if isinstance(manual,dict) and manual.get('base_facturacion')=='pedido_completo':
            validar_completos(db,pedidos,lineas,manual.get('pedidos_completos'),importes)
        if datos['monto_total']<=0: fail('El importe debe ser positivo.')
        if validar_solo:
            resultado=dict(valida=True,mensaje='Los datos, posiciones, referencias e importes coinciden.',total=str(datos['monto_total']),pedidos=[dict(numero=o.numero,importe=str(sum(l['total'] for l in lineas if l['orden_id']==o.id))) for o in pedidos])
            db.rollback()
            return resultado
        fid=str(uuid4());f=Factura(id=fid,proveedor_id=proveedor.id,cliente_id=user['cliente_id'],sociedad_id=sociedad_receptora.id,orden_compra_id=pedidos[0].id if len(pedidos)==1 else None,estado='Pendiente de revisión',**{k:datos[k] for k in ['serie','correlativo','monto_subtotal','monto_igv','monto_total']})
        db.add(f);db.flush()
        db.add(FacturaRegistro(factura_id=fid,fecha_emision=datos['fecha_emision'],moneda='PEN',ruc_receptor=ruc_receptor,sociedad_id=sociedad_receptora.id,xml=xml_data,pdf=pdf_data))
        for i,l in enumerate(lineas,1):
            asignacion=FacturaAsignacion(factura_id=fid,**{k:l[k] for k in ['posicion_id','linea_xml','cantidad','subtotal','igv','total']})
            db.add(asignacion);db.flush()
            if l['documento_linea_id']:
                from models import FacturaOrigen
                db.add(FacturaOrigen(asignacion_id=asignacion.id,documento_linea_id=l['documento_linea_id']))
            db.add(FacturaLinea(factura_id=fid,numero_linea=i,descripcion=l['descripcion'],cantidad=l['cantidad'],precio_unitario=l['precio'],monto_subtotal=l['subtotal'],igv=l['igv'],monto_total=l['total'],codigo_producto=l['codigo_producto']))
        from sap_integracion import preparar
        preparar(db,f,datos,lineas,user['ruc'],ruc_receptor,sociedad_receptora)
        db.commit();return dict(id=fid,estado=f.estado,sap_estado='pendiente_configuracion')
    except Exception: db.rollback();raise






def validar_completos(db,pedidos,lineas,seleccionados,importes):
    if not isinstance(seleccionados,list) or any(not isinstance(i,str) for i in seleccionados) or set(seleccionados)!={o.id for o in pedidos}:
        fail('Deben incluirse todos los pedidos seleccionados para facturación completa.')
    for o in pedidos:
        state=posiciones(db,o)
        if state['bloqueo']: fail(state['bloqueo'])
        lineas_pedido=[l for l in lineas if l['orden_id']==o.id]
        if not lineas_pedido:
            fail('Incluye al menos una posición pendiente del pedido '+o.numero+'.')
        for linea in lineas_pedido:
            posicion=next((p for p in state['posiciones'] if p['id']==linea['posicion_id']),None)
            if not posicion or linea['cantidad']>number(posicion['cantidad_pendiente']):
                fail('La cantidad supera lo pendiente en el pedido '+o.numero+'.')
        if sum(l['total'] for l in lineas_pedido)>o.monto_total-importes.get(o.id,0):
            fail('La factura supera el saldo pendiente del pedido '+o.numero)
