"""Lectura para revisión humana de UBL; no certifica aceptación SUNAT."""
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException

NS={'cbc':'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2','cac':'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'}

def review_xml(data, ruc, orden, db, multipedido=False, ruc_receptor=None, cliente_id=None):
    from facturas import parse_xml, fail, MAX_FILE
    from models import Factura
    from sqlalchemy import func
    if not data or len(data)>MAX_FILE or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper() or b'\x00' in data: fail('XML no permitido.')
    try: root=ET.fromstring(data)
    except ET.ParseError: fail('El XML no es válido.')
    if root.tag!='{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice': fail('Se requiere una factura XML UBL.')
    def txt(node,path): return (node.findtext(path,default='',namespaces=NS) or '').strip()
    def attr(node,path,name):
        e=node.find(path,NS)
        return e.get(name,'') if e is not None else ''
    checks=[]
    def check(campo,estado,detalle): checks.append(dict(campo=campo,estado=estado,detalle=detalle))
    try:
        parsed=parse_xml(data,ruc)
        check('Cabecera e importes','ok','Emisor, fecha, moneda e importes compatibles con el registro.')
    except HTTPException as e:
        parsed=None
        check('Cabecera e importes','error',e.detail)
    parties={}
    for key,tag in [('emisor','AccountingSupplierParty'),('receptor','AccountingCustomerParty')]:
        p=root.find('cac:'+tag,NS)
        parties[key]={} if p is None else {
          'Documento':txt(p,'cac:Party/cac:PartyIdentification/cbc:ID') or txt(p,'cbc:CustomerAssignedAccountID'),
          'Tipo de documento':attr(p,'cac:Party/cac:PartyIdentification/cbc:ID','schemeID'),
          'Razón social':txt(p,'cac:Party/cac:PartyLegalEntity/cbc:RegistrationName') or txt(p,'cac:Party/cac:PartyTaxScheme/cbc:RegistrationName'),
          'Nombre comercial':txt(p,'cac:Party/cac:PartyName/cbc:Name'),
          'Dirección':txt(p,'cac:Party/cac:PartyLegalEntity/cac:RegistrationAddress/cac:AddressLine/cbc:Line'),
          'Ubigeo':txt(p,'cac:Party/cac:PartyLegalEntity/cac:RegistrationAddress/cbc:ID')}
    receptor=(ruc_receptor or '').strip()
    check('RUC receptor','ok' if receptor and parties['receptor'].get('Documento')==receptor else 'error' if receptor else 'aviso','Coincide con la empresa receptora.' if receptor and parties['receptor'].get('Documento')==receptor else 'El receptor no coincide.' if receptor else 'Falta configurar el RUC de la empresa receptora; no se ha validado.')
    lineas=[]
    for l in root.findall('cac:InvoiceLine',NS):
        lineas.append({'Pedido':txt(l,'cac:OrderLineReference/cac:OrderReference/cbc:ID'),'Posición pedido':txt(l,'cac:OrderLineReference/cbc:LineID'),'Ítem':txt(l,'cbc:ID'),'Código':txt(l,'cac:Item/cac:SellersItemIdentification/cbc:ID'),'Código SUNAT':txt(l,'cac:Item/cac:CommodityClassification/cbc:ItemClassificationCode'),'Descripción':' / '.join(e.text or '' for e in l.findall('cac:Item/cbc:Description',NS)), 'Cantidad':txt(l,'cbc:InvoicedQuantity'),'Unidad':attr(l,'cbc:InvoicedQuantity','unitCode'),'Valor unitario':txt(l,'cac:Price/cbc:PriceAmount'),'Precio de venta':txt(l,'cac:PricingReference/cac:AlternativeConditionPrice/cbc:PriceAmount'),'Valor de venta':txt(l,'cbc:LineExtensionAmount'),'Impuestos':txt(l,'cac:TaxTotal/cbc:TaxAmount'),'Afectación IGV':txt(l,'cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory/cbc:TaxExemptionReasonCode')})
    totales={label:txt(root,'cac:LegalMonetaryTotal/cbc:'+tag) for label,tag in [('Valor de venta','LineExtensionAmount'),('Base sin impuestos','TaxExclusiveAmount'),('Precio con impuestos','TaxInclusiveAmount'),('Descuentos','AllowanceTotalAmount'),('Cargos','ChargeTotalAmount'),('Anticipos','PrepaidAmount'),('Redondeo','PayableRoundingAmount'),('Importe a pagar','PayableAmount')]}
    if lineas:
        try:
            valores=[Decimal(l['Valor de venta']) for l in lineas]
            esperado=Decimal(totales['Valor de venta'])
            cantidades=[Decimal(l['Cantidad']) for l in lineas]
            valid=all(v.is_finite() and v>=0 for v in valores) and all(v.is_finite() and v>0 for v in cantidades) and esperado.is_finite() and abs(sum(valores)-esperado)<=Decimal('.01')
            check('Suma de ítems','ok' if valid else 'error','La suma de valores de venta coincide.' if valid else 'Cantidades inválidas o suma de ítems diferente al valor de venta.')
        except (InvalidOperation,ValueError): check('Suma de ítems','error','No se pueden comprobar los importes de las líneas.')
    else: check('Detalle de ítems','error','La factura no contiene líneas InvoiceLine.')
    impuestos=[{'Código':txt(t,'cac:TaxCategory/cac:TaxScheme/cbc:ID'),'Tributo':txt(t,'cac:TaxCategory/cac:TaxScheme/cbc:Name'),'Base':txt(t,'cbc:TaxableAmount'),'Importe':txt(t,'cbc:TaxAmount')} for t in root.findall('cac:TaxTotal/cac:TaxSubtotal',NS)]
    referencia=txt(root,'cac:OrderReference/cbc:ID')
    comparacion=None
    if orden is not None:
        from saldos import importes_por_orden
        facturado=importes_por_orden(db,orden.proveedor_id,cliente_id).get(orden.id,0)
        saldo=orden.monto_total-facturado
        comparacion=dict(numero=orden.numero,total=float(orden.monto_total),facturado=float(facturado),saldo=float(saldo),moneda='PEN')
        check('Referencia de pedido','ok' if referencia==orden.numero else 'error' if referencia else 'aviso','Coincide con la orden seleccionada.' if referencia==orden.numero else f'El XML indica {referencia}; la orden seleccionada es {orden.numero}.' if referencia else 'El XML no incluye referencia de pedido; se asociará a la orden seleccionada.')
        check('Estado del pedido','error' if orden.estado.lower() in ['cancelado','cancelada','anulado','anulada'] else 'ok',orden.estado)
        if parsed:
            check('Saldo disponible','ok' if parsed['monto_total']<=saldo else 'error',f"Factura: {parsed['monto_total']} PEN · saldo: {saldo} PEN · saldo posterior: {saldo-parsed['monto_total']} PEN")
            query=db.query(Factura).filter(Factura.proveedor_id==orden.proveedor_id,func.upper(Factura.serie)==parsed['serie'])
            if cliente_id: query=query.filter(Factura.cliente_id==cliente_id)
            anteriores=query.all()
            duplicada=any(f.correlativo.isdigit() and int(f.correlativo)==int(parsed['correlativo']) for f in anteriores)
            check('Duplicados','error' if duplicada else 'ok','La factura ya está registrada.' if duplicada else 'No existe ese comprobante para el proveedor.')
    elif not multipedido: check('Pedido','error','Selecciona una orden para validar el saldo y la referencia.')
    check('Cantidades y precios contra pedido','aviso','Relaciona las líneas con las posiciones. La comparación definitiva se realiza al enviar, con los saldos actualizados.')
    check('SUNAT y firma digital','aviso','No se ha consultado SUNAT ni verificado la firma criptográfica o el CDR.')
    campos=[]
    def walk(e,path):
        tag=e.tag.split('}')[-1];path=path+'/'+tag
        if (e.text or '').strip() or e.attrib:
            campos.append({'ruta':path,'valor':(e.text or '').strip(),'atributos':dict(e.attrib)})
        for index,child in enumerate(e):walk(child,path+f'[{index+1}]')
    walk(root,'')
    return {'cabecera':{'Comprobante':txt(root,'cbc:ID'),'Fecha de emisión':txt(root,'cbc:IssueDate'),'Hora':txt(root,'cbc:IssueTime'),'Vencimiento':txt(root,'cbc:DueDate'),'Tipo':txt(root,'cbc:InvoiceTypeCode'),'Moneda':txt(root,'cbc:DocumentCurrencyCode'),'UBL':txt(root,'cbc:UBLVersionID'),'Personalización':txt(root,'cbc:CustomizationID'),'Pedido XML':referencia},**parties,'totales':totales,'lineas':lineas,'impuestos':impuestos,'campos':campos,'validaciones':checks,'pedido':comparacion,'puede_enviar':not any(c['estado']=='error' for c in checks),'datos':parsed}




