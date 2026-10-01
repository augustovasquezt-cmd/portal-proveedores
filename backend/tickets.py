import re
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_provider_user
from models import (Proveedor, ProveedorCliente, Ticket, TicketContexto, TicketMensaje, TicketAdjunto,
                    OrdenCompra, Factura, DocumentoBase, DocumentoBaseLinea,
                    OrdenPosicion, FacturaAsignacion)
from facturas import fail

router=APIRouter(prefix='/tickets',tags=['tickets'])
MAX_ADJUNTO=5*1024*1024
CATEGORIAS={'factura':'Factura','pedido':'Orden de compra','documento':'Documento asociado','pago':'Pago','acceso':'Acceso o soporte técnico','otro':'Otra consulta'}
ESTADOS={'abierto':'Abierto','esperando_comprador':'Esperando al comprador','esperando_proveedor':'Requiere información del proveedor','resuelto':'Resuelto','cerrado':'Cerrado'}

def validar_adjunto(nombre,data):
    ext='.'+nombre.rsplit('.',1)[-1].lower() if '.' in nombre else ''
    if ext not in {'.pdf','.png','.jpg','.jpeg','.xml'}: fail('Adjunta solo PDF, PNG, JPG o XML.')
    if not data or len(data)>MAX_ADJUNTO: fail('Cada archivo debe pesar entre 1 byte y 5 MB.')
    firmas={'.pdf':data.startswith(b'%PDF-'),'.png':data.startswith(b'\x89PNG\r\n\x1a\n'),'.jpg':data.startswith(b'\xff\xd8\xff'),'.jpeg':data.startswith(b'\xff\xd8\xff')}
    if ext in firmas and not firmas[ext]:fail('El contenido del archivo no coincide con su extensión.')
    if ext=='.xml' and (b'\x00' in data or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper()):fail('El XML adjunto no es válido o contiene declaraciones no permitidas.')
    return ext

def proveedor_actual(db,user):
    p=db.query(Proveedor).filter(Proveedor.ruc==user['ruc'],Proveedor.activo.is_(True)).first()
    if not p:fail('Proveedor no encontrado.',404)
    if not db.query(ProveedorCliente.id).filter_by(proveedor_id=p.id,cliente_id=user['cliente_id'],activo=True).first(): fail('No tienes acceso a este cliente.',403)
    return p

def referencias(db,p,cliente_id):
    items=[]
    for o in db.query(OrdenCompra).filter(OrdenCompra.proveedor_id==p.id,OrdenCompra.cliente_id==cliente_id).order_by(OrdenCompra.creado_en.desc()).all():
        items.append(dict(tipo='pedido',id=o.id,numero=o.numero,descripcion=o.descripcion or '',pedido=o.numero))
    for f in db.query(Factura).filter(Factura.proveedor_id==p.id,Factura.cliente_id==cliente_id).order_by(Factura.creado_en.desc()).all():
        order_ids={x[0] for x in db.query(OrdenPosicion.orden_id).join(FacturaAsignacion,FacturaAsignacion.posicion_id==OrdenPosicion.id).filter(FacturaAsignacion.factura_id==f.id).all()}
        if f.orden_compra_id:order_ids.add(f.orden_compra_id)
        order=db.get(OrdenCompra,next(iter(order_ids))) if len(order_ids)==1 else None
        items.append(dict(tipo='factura',id=f.id,numero=f'{f.serie}-{f.correlativo}',descripcion=f.estado,pedido=order.numero if order else 'Varias órdenes' if order_ids else ''))
    docs=db.query(DocumentoBase).filter(DocumentoBase.proveedor_id==p.id,DocumentoBase.cliente_id==cliente_id).order_by(DocumentoBase.fecha.desc()).all()
    for d in docs:
        links=db.query(DocumentoBaseLinea,OrdenPosicion,OrdenCompra).join(OrdenPosicion,OrdenPosicion.id==DocumentoBaseLinea.posicion_id).join(OrdenCompra,OrdenCompra.id==OrdenPosicion.orden_id).filter(DocumentoBaseLinea.documento_id==d.id,OrdenCompra.proveedor_id==p.id).all()
        orders={o.id:o.numero for _,_,o in links}
        items.append(dict(tipo='documento',id=d.id,numero=d.numero,descripcion=d.tipo+' · '+d.estado,pedido=', '.join(orders.values())))
    return items

def serialize(db,t):
    ctx=db.get(TicketContexto,t.id)
    msgs=db.query(TicketMensaje).filter(TicketMensaje.ticket_id==t.id).order_by(TicketMensaje.creado_en,TicketMensaje.id).all()
    attachments=db.query(TicketAdjunto).filter(TicketAdjunto.ticket_id==t.id).all()
    return dict(id=t.id,numero=t.numero,asunto=t.asunto,descripcion=t.descripcion,categoria=t.categoria,prioridad=t.prioridad,estado=t.estado,creado_en=t.creado_en.isoformat() if t.creado_en else None,referencia=dict(tipo=ctx.tipo_referencia,numero=ctx.referencia_numero,orden_id=ctx.orden_id) if ctx else None,mensajes=[dict(id=m.id,autor_tipo=m.autor_tipo,mensaje=m.mensaje,creado_en=m.creado_en.isoformat() if m.creado_en else None,adjuntos=[dict(id=a.id,nombre=a.nombre) for a in attachments if a.mensaje_id==m.id]) for m in msgs],adjuntos=[dict(id=a.id,nombre=a.nombre) for a in attachments if not a.mensaje_id])

def buscar_ticket(db,p,ticket_id,cliente_id):
    t=db.query(Ticket).filter(Ticket.id==ticket_id,Ticket.proveedor_id==p.id,Ticket.cliente_id==cliente_id).first()
    if not t:fail('Ticket no encontrado.',404)
    return t

def resolver_referencia(db,p,tipo,refid,cliente_id):
    if tipo=='general':return None,None,None
    if tipo=='pedido':
        o=db.query(OrdenCompra).filter(OrdenCompra.id==refid,OrdenCompra.proveedor_id==p.id,OrdenCompra.cliente_id==cliente_id).first()
        if not o:fail('La orden seleccionada no pertenece a tu empresa.',404)
        return o.numero,o.id,o.numero
    if tipo=='factura':
        f=db.query(Factura).filter(Factura.id==refid,Factura.proveedor_id==p.id,Factura.cliente_id==cliente_id).first()
        if not f:fail('La factura seleccionada no pertenece a tu empresa.',404)
        ids={x[0] for x in db.query(OrdenPosicion.orden_id).join(FacturaAsignacion,FacturaAsignacion.posicion_id==OrdenPosicion.id).filter(FacturaAsignacion.factura_id==f.id).all()}
        if f.orden_compra_id:ids.add(f.orden_compra_id)
        oid=next(iter(ids)) if len(ids)==1 else None
        return f'{f.serie}-{f.correlativo}',oid,f'{f.serie}-{f.correlativo}'
    if tipo=='documento':
        d=db.query(DocumentoBase).filter(DocumentoBase.id==refid,DocumentoBase.proveedor_id==p.id,DocumentoBase.cliente_id==cliente_id).first()
        if not d:fail('El documento seleccionado no pertenece a tu empresa.',404)
        rows=db.query(OrdenCompra.id,OrdenCompra.numero).join(OrdenPosicion,OrdenPosicion.orden_id==OrdenCompra.id).join(DocumentoBaseLinea,DocumentoBaseLinea.posicion_id==OrdenPosicion.id).filter(DocumentoBaseLinea.documento_id==d.id,OrdenCompra.proveedor_id==p.id).all()
        orders={oid:num for oid,num in rows};oid=next(iter(orders)) if len(orders)==1 else None
        return d.numero,oid,d.numero
    fail('Tipo de referencia inválido.')

@router.get('/referencias')
def listar_referencias(user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    return referencias(db,proveedor_actual(db,user),user['cliente_id'])

@router.get('')
def listar(user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    p=proveedor_actual(db,user)
    return [serialize(db,t) for t in db.query(Ticket).filter(Ticket.proveedor_id==p.id,Ticket.cliente_id==user['cliente_id']).order_by(Ticket.creado_en.desc()).all()]

@router.post('',status_code=201)
async def crear(referencia_tipo:str=Form('general'),referencia_id:str=Form(''),asunto:str=Form(...),categoria:str=Form(...),descripcion:str=Form(...),prioridad:str=Form('normal'),archivos:list[UploadFile]|None=File(None),user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    p=proveedor_actual(db,user)
    asunto=asunto.strip();descripcion=descripcion.strip()
    if len(asunto)<5 or len(asunto)>200:fail('El asunto debe tener entre 5 y 200 caracteres.')
    if len(descripcion)<10 or len(descripcion)>5000:fail('Describe el caso con al menos 10 caracteres y máximo 5000.')
    if categoria not in CATEGORIAS:fail('Selecciona una categoría válida.')
    if prioridad not in {'normal','alta'}:fail('Selecciona una prioridad válida.')
    if referencia_tipo not in {'general','pedido','factura','documento'}:fail('Selecciona un tipo de documento válido.')
    if referencia_tipo!='general' and not referencia_id:fail('Selecciona el documento relacionado.')
    ref_num,order_id,ref_label=resolver_referencia(db,p,referencia_tipo,referencia_id,user['cliente_id'])
    if len(archivos or [])>5:fail('Adjunta hasta 5 archivos por envío.')
    loaded=[]
    for file in archivos or []:
        name=(file.filename or 'evidencia').replace('\\','/').split('/')[-1]
        data=await file.read(MAX_ADJUNTO+1);ext=validar_adjunto(name,data)
        loaded.append((name,data,'application/pdf' if ext=='.pdf' else 'application/xml' if ext=='.xml' else 'image/png' if ext=='.png' else 'image/jpeg'))
        if sum(len(item[1]) for item in loaded)>20*1024*1024:fail('El tamaño total de los adjuntos supera 20 MB.')
    ticket_id=str(uuid4());number='TK-'+datetime.now().strftime('%Y%m%d')+'-'+ticket_id[:6].upper()
    t=Ticket(id=ticket_id,numero=number,proveedor_id=p.id,cliente_id=user['cliente_id'],asunto=asunto,descripcion=descripcion,categoria=categoria,prioridad=prioridad,estado='abierto')
    db.add(t);db.flush()
    db.add(TicketContexto(ticket_id=t.id,tipo_referencia=referencia_tipo,referencia_id=referencia_id or None,referencia_numero=ref_num,orden_id=order_id))
    m=TicketMensaje(ticket_id=t.id,autor_tipo='proveedor',autor_id=p.id,mensaje=descripcion);db.add(m);db.flush()
    for name,data,mime in loaded:db.add(TicketAdjunto(ticket_id=t.id,mensaje_id=m.id,nombre=name,tipo_mime=mime,contenido=data))
    db.commit();db.refresh(t)
    return serialize(db,t)

@router.post('/{ticket_id}/mensajes',status_code=201)
async def responder(ticket_id:str,mensaje:str=Form(...),archivos:list[UploadFile]|None=File(None),user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    p=proveedor_actual(db,user);t=buscar_ticket(db,p,ticket_id,user['cliente_id']);mensaje=mensaje.strip()
    if t.estado in {'resuelto','cerrado'}:fail('Este caso ya está cerrado. Abre uno nuevo si necesitas continuar.')
    if len(mensaje)<2 or len(mensaje)>5000:fail('El mensaje debe tener entre 2 y 5000 caracteres.')
    if len(archivos or [])>5:fail('Adjunta hasta 5 archivos por envío.')
    loaded=[]
    for file in archivos or []:
        name=(file.filename or 'evidencia').replace('\\','/').split('/')[-1];data=await file.read(MAX_ADJUNTO+1);ext=validar_adjunto(name,data)
        loaded.append((name,data,'application/pdf' if ext=='.pdf' else 'application/xml' if ext=='.xml' else 'image/png' if ext=='.png' else 'image/jpeg'))
        if sum(len(item[1]) for item in loaded)>20*1024*1024:fail('El tamaño total de los adjuntos supera 20 MB.')
    m=TicketMensaje(ticket_id=t.id,autor_tipo='proveedor',autor_id=p.id,mensaje=mensaje);db.add(m);db.flush()
    for name,data,mime in loaded:db.add(TicketAdjunto(ticket_id=t.id,mensaje_id=m.id,nombre=name,tipo_mime=mime,contenido=data))
    t.estado='abierto';db.commit();db.refresh(t);return serialize(db,t)

@router.get('/{ticket_id}/adjuntos/{adjunto_id}')
def descargar(ticket_id:str,adjunto_id:str,user:dict=Depends(get_current_provider_user),db:Session=Depends(get_db)):
    p=proveedor_actual(db,user);buscar_ticket(db,p,ticket_id,user['cliente_id'])
    a=db.query(TicketAdjunto).filter(TicketAdjunto.id==adjunto_id,TicketAdjunto.ticket_id==ticket_id).first()
    if not a:fail('Archivo no encontrado.',404)
    safe=re.sub(r'[^A-Za-z0-9._-]','_',a.nombre)
    return Response(a.contenido,media_type=a.tipo_mime,headers={'Content-Disposition':f'attachment; filename="{safe}"','X-Content-Type-Options':'nosniff'})
