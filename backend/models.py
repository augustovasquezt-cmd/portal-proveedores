from sqlalchemy import Column, String, Integer, DateTime, Date, Numeric, ForeignKey, Boolean, Text, LargeBinary, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())

class Proveedor(Base):
    __tablename__ = "proveedores"
    id = Column(String, primary_key=True, default=gen_uuid)
    ruc = Column(String(11), unique=True, nullable=False)
    razon_social = Column(String(200), nullable=False)
    nombre_comercial = Column(String(200))
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    telefono = Column(String(20))
    direccion = Column(Text)
    estado = Column(String(20), default="pendiente")
    activo = Column(Boolean, default=True)
    cambio_password_requerido = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime, server_default=func.now())

class UsuarioInterno(Base):
    __tablename__ = "usuarios_internos"
    id = Column(String, primary_key=True, default=gen_uuid)
    usuario = Column(String(150), unique=True, nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    rol = Column(String(50), nullable=False, default="cuentas_por_pagar")
    cliente_id = Column(String, ForeignKey("clientes.id"), index=True)
    password_hash = Column(String(200), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    cambio_password_requerido = Column(Boolean, nullable=False, default=False)
    creado_en = Column(DateTime, server_default=func.now())

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(String, primary_key=True, default=gen_uuid)
    codigo = Column(String(60), unique=True, nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    max_administradores = Column(Integer, nullable=False, default=1)
    max_cuentas_por_pagar = Column(Integer, nullable=False, default=5)
    max_proveedores = Column(Integer, nullable=False, default=50)
    max_sociedades = Column(Integer, nullable=False, default=10)
    sap_api_key_hash = Column(String(64))
    creado_en = Column(DateTime, server_default=func.now(), nullable=False)

class Sociedad(Base):
    __tablename__ = "sociedades"
    __table_args__ = (UniqueConstraint("cliente_id", "ruc", name="uq_sociedad_cliente_ruc"),)
    id = Column(String, primary_key=True, default=gen_uuid)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    ruc = Column(String(11), nullable=False)
    razon_social = Column(String(200), nullable=False)
    codigo_sap = Column(String(20))
    es_principal = Column(Boolean, nullable=False, default=False)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, server_default=func.now(), nullable=False)

class ProveedorCliente(Base):
    __tablename__ = "proveedores_clientes"
    __table_args__ = (UniqueConstraint("proveedor_id", "cliente_id", name="uq_proveedor_cliente"),)
    id = Column(String, primary_key=True, default=gen_uuid)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False, index=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime, server_default=func.now(), nullable=False)

class UsuarioSociedad(Base):
    __tablename__ = "usuarios_sociedades"
    __table_args__ = (UniqueConstraint("usuario_id", "sociedad_id", name="uq_usuario_sociedad"),)
    id = Column(String, primary_key=True, default=gen_uuid)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    usuario_id = Column(String, ForeignKey("usuarios_internos.id"), nullable=False, index=True)
    sociedad_id = Column(String, ForeignKey("sociedades.id"), nullable=False, index=True)

class ProveedorSociedad(Base):
    __tablename__ = "proveedores_sociedades"
    __table_args__ = (UniqueConstraint("proveedor_cliente_id", "sociedad_id", name="uq_proveedor_cliente_sociedad"),)
    id = Column(String, primary_key=True, default=gen_uuid)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    proveedor_cliente_id = Column(String, ForeignKey("proveedores_clientes.id"), nullable=False, index=True)
    sociedad_id = Column(String, ForeignKey("sociedades.id"), nullable=False, index=True)

class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"
    __table_args__ = (UniqueConstraint("cliente_id", "numero", name="uq_orden_cliente_numero"),)
    id = Column(String, primary_key=True, default=gen_uuid)
    numero = Column(String(50), nullable=False)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False)
    cliente_id = Column(String, ForeignKey("clientes.id"), index=True)
    sociedad_id = Column(String, ForeignKey("sociedades.id"), index=True)
    monto_total = Column(Numeric(12, 2), nullable=False)
    estado = Column(String(30), default="por_recepcionar")
    descripcion = Column(Text)
    creado_en = Column(DateTime, server_default=func.now())

class Factura(Base):
    __tablename__ = "facturas"
    id = Column(String, primary_key=True)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False)
    cliente_id = Column(String, ForeignKey("clientes.id"), index=True)
    sociedad_id = Column(String, ForeignKey("sociedades.id"), index=True)
    serie = Column(String(10), nullable=False)
    correlativo = Column(String(10), nullable=False)
    orden_compra_id = Column(String)
    monto_subtotal = Column(Numeric(12, 2), nullable=False)
    monto_igv = Column(Numeric(12, 2), nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)
    estado = Column(String(30), default="Emitida")
    cae = Column(String(100))
    creado_en = Column(DateTime, server_default=func.now())
    recibida_contabilidad_en = Column(DateTime)
    aceptada_portal_en = Column(DateTime)
    fecha_pago_programada = Column(Date)
    pagada_en = Column(DateTime)
    motivo_rechazo = Column(Text)
    lineas = relationship("FacturaLinea", back_populates="factura", cascade="all, delete-orphan")

class FacturaLinea(Base):
    __tablename__ = "factura_lineas"
    id = Column(Integer, primary_key=True)
    factura_id = Column(String, ForeignKey("facturas.id", ondelete="CASCADE"), nullable=False)
    numero_linea = Column(Integer)
    descripcion = Column(String, nullable=False)
    cantidad = Column(Numeric(10, 2), nullable=False)
    precio_unitario = Column(Numeric(12, 2), nullable=False)
    monto_subtotal = Column(Numeric(12, 2), nullable=False)
    igv = Column(Numeric(12, 2), nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)
    codigo_producto = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    factura = relationship("Factura", back_populates="lineas")

class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("cliente_id", "numero", name="uq_ticket_cliente_numero"),)
    id = Column(String, primary_key=True, default=gen_uuid)
    numero = Column(String(20), nullable=False)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False)
    cliente_id = Column(String, ForeignKey("clientes.id"), index=True)
    asunto = Column(String(200), nullable=False)
    descripcion = Column(Text)
    categoria = Column(String(50))
    prioridad = Column(String(20), default="normal")
    estado = Column(String(20), default="abierto")
    creado_en = Column(DateTime, server_default=func.now())

# Archivos y metadatos del registro, sin alterar las facturas existentes.
from sqlalchemy import LargeBinary, Date

class FacturaRegistro(Base):
    __tablename__ = 'factura_registros'
    factura_id = Column(String, ForeignKey('facturas.id'), primary_key=True)
    fecha_emision = Column(Date, nullable=False)
    moneda = Column(String(3), nullable=False)
    ruc_receptor = Column(String(11))
    sociedad_id = Column(String, ForeignKey('sociedades.id'), index=True)
    xml = Column(LargeBinary, nullable=False)
    pdf = Column(LargeBinary, nullable=False)

class OrdenPosicion(Base):
    __tablename__ = 'orden_posiciones'
    id = Column(String, primary_key=True, default=gen_uuid)
    orden_id = Column(String, ForeignKey('ordenes_compra.id'), nullable=False)
    numero = Column(String(10), nullable=False)
    material = Column(String(50), nullable=False)
    descripcion = Column(Text, nullable=False)
    unidad = Column(String(10), nullable=False, default='NIU')
    cantidad = Column(Numeric(14, 4), nullable=False)
    precio_unitario = Column(Numeric(14, 4), nullable=False)
    tasa_igv = Column(Numeric(5, 2), nullable=False, default=18)
    # A service specification line remains linked to its SAP PO item (`numero`).
    # `paquete_servicio` and `numero_servicio` preserve the child line identity.
    tipo = Column(String(20), nullable=False, default='material')
    codigo_servicio = Column(String(50))
    paquete_servicio = Column(String(20))
    numero_servicio = Column(String(20))

class FacturaAsignacion(Base):
    __tablename__ = 'factura_asignaciones'
    id = Column(String, primary_key=True, default=gen_uuid)
    factura_id = Column(String, ForeignKey('facturas.id'), nullable=False)
    posicion_id = Column(String, ForeignKey('orden_posiciones.id'), nullable=False)
    linea_xml = Column(Integer)
    cantidad = Column(Numeric(14, 4), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)
    igv = Column(Numeric(12, 2), nullable=False)
    total = Column(Numeric(12, 2), nullable=False)

class DocumentoBase(Base):
    __tablename__ = 'documentos_base'
    __table_args__ = (UniqueConstraint('cliente_id', 'numero', name='uq_documento_cliente_numero'),)
    id = Column(String, primary_key=True, default=gen_uuid)
    proveedor_id = Column(String, ForeignKey('proveedores.id'), nullable=False)
    cliente_id = Column(String, ForeignKey('clientes.id'), index=True)
    tipo = Column(String(20), nullable=False)
    numero = Column(String(50), nullable=False)
    estado = Column(String(20), nullable=False)
    fecha = Column(Date, nullable=False)

class DocumentoBaseLinea(Base):
    __tablename__ = 'documento_base_lineas'
    id = Column(String, primary_key=True, default=gen_uuid)
    documento_id = Column(String, ForeignKey('documentos_base.id'), nullable=False)
    posicion_id = Column(String, ForeignKey('orden_posiciones.id'), nullable=False)
    numero = Column(String(10), nullable=False)
    cantidad = Column(Numeric(14, 4), nullable=False)

class FacturaOrigen(Base):
    __tablename__ = 'factura_origenes'
    asignacion_id = Column(String, ForeignKey('factura_asignaciones.id'), primary_key=True)
    documento_linea_id = Column(String, ForeignKey('documento_base_lineas.id'), nullable=False)

class FacturaEnvioSAP(Base):
    __tablename__ = 'factura_envios_sap'
    factura_id = Column(String, ForeignKey('facturas.id'), primary_key=True)
    cliente_id = Column(String, ForeignKey('clientes.id'), index=True)
    estado = Column(String(40), nullable=False, default='pendiente_configuracion')
    clave_idempotencia = Column(String(100), unique=True, nullable=False)
    contenido = Column(Text, nullable=False)
    documento_sap = Column(String(100))
    creado_en = Column(DateTime, server_default=func.now())

class FacturaEvento(Base):
    __tablename__ = "factura_eventos"
    id = Column(String, primary_key=True, default=gen_uuid)
    factura_id = Column(String, ForeignKey("facturas.id", ondelete="CASCADE"), nullable=False, index=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), index=True)
    actor_id = Column(String(100), nullable=False)
    actor_nombre = Column(String(200), nullable=False)
    accion = Column(String(40), nullable=False)
    estado_anterior = Column(String(40))
    estado_nuevo = Column(String(40), nullable=False)
    comentario = Column(Text)
    fecha_pago_programada = Column(Date)
    creado_en = Column(DateTime, server_default=func.now())

class SolicitudCuentasPorPagar(Base):
    __tablename__ = "solicitudes_cuentas_por_pagar"
    id = Column(String, primary_key=True, default=gen_uuid)
    usuario_id = Column(String, ForeignKey("usuarios_internos.id"), nullable=False, index=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), index=True)
    factura_id = Column(String, ForeignKey("facturas.id"))
    categoria = Column(String(80), nullable=False)
    asunto = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=False)
    estado = Column(String(30), nullable=False, default="Abierta")
    creado_en = Column(DateTime, server_default=func.now())


class TicketContexto(Base):
    __tablename__ = 'ticket_contextos'
    ticket_id = Column(String, ForeignKey('tickets.id', ondelete='CASCADE'), primary_key=True)
    tipo_referencia = Column(String(20), nullable=False, default='general')
    referencia_id = Column(String(100))
    referencia_numero = Column(String(100))
    orden_id = Column(String, ForeignKey('ordenes_compra.id'))
    comprador_id = Column(String(100))

class TicketMensaje(Base):
    __tablename__ = 'ticket_mensajes'
    id = Column(String, primary_key=True, default=gen_uuid)
    ticket_id = Column(String, ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    autor_tipo = Column(String(20), nullable=False)
    autor_id = Column(String(100))
    mensaje = Column(Text, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())

class TicketAdjunto(Base):
    __tablename__ = 'ticket_adjuntos'
    id = Column(String, primary_key=True, default=gen_uuid)
    ticket_id = Column(String, ForeignKey('tickets.id', ondelete='CASCADE'), nullable=False)
    mensaje_id = Column(String, ForeignKey('ticket_mensajes.id', ondelete='CASCADE'))
    nombre = Column(String(255), nullable=False)
    tipo_mime = Column(String(100), nullable=False)
    contenido = Column(LargeBinary, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())


class RegistroAuditoria(Base):
    __tablename__ = 'registros_auditoria'
    id = Column(String, primary_key=True, default=gen_uuid)
    actor_usuario_id = Column(String(100), nullable=False, index=True)
    actor_usuario = Column(String(150), nullable=False)
    cliente_id = Column(String, ForeignKey('clientes.id'), index=True)
    accion = Column(String(60), nullable=False)
    tipo_objetivo = Column(String(30), nullable=False)
    objetivo_id = Column(String(100), nullable=False, index=True)
    detalles = Column(Text, nullable=False, default='{}')
    creado_en = Column(DateTime, server_default=func.now(), nullable=False)


class CertificadoRetencion(Base):
    """Copia inmutable de un CRE emitido por el ERP para consulta del proveedor."""
    __tablename__ = 'certificados_retencion'
    __table_args__ = (UniqueConstraint('cliente_id', 'ruc_emisor', 'serie', 'correlativo', name='uq_cre_cliente_emisor_serie_numero'), UniqueConstraint('cliente_id', 'evento_origen', name='uq_cre_cliente_evento_origen'))
    id = Column(String, primary_key=True, default=gen_uuid)
    proveedor_id = Column(String, ForeignKey('proveedores.id'), nullable=False, index=True)
    cliente_id = Column(String, ForeignKey('clientes.id'), index=True)
    ruc_emisor = Column(String(11), nullable=False, index=True)
    sociedad = Column(String(4))
    serie = Column(String(4), nullable=False)
    correlativo = Column(String(20), nullable=False)
    fecha_emision = Column(Date, nullable=False, index=True)
    moneda = Column(String(3), nullable=False, default='PEN')
    base_retencion = Column(Numeric(14, 2), nullable=False)
    tasa_retencion = Column(Numeric(7, 4))
    importe_retencion = Column(Numeric(14, 2), nullable=False)
    fecha_pago = Column(Date)
    referencia_pago = Column(String(100))
    documento_sap = Column(String(100))
    ejercicio_sap = Column(String(4))
    facturas_relacionadas = Column(Text, nullable=False, default='[]')
    estado_sunat = Column(String(20), nullable=False, default='pendiente')
    motivo_estado = Column(Text)
    evento_origen = Column(String(100), nullable=False)
    sha256_metadatos = Column(String(64), nullable=False)
    nombre_xml = Column(String(255), nullable=False)
    xml = Column(LargeBinary, nullable=False)
    sha256_xml = Column(String(64), nullable=False)
    nombre_pdf = Column(String(255), nullable=False)
    pdf = Column(LargeBinary, nullable=False)


class FacturaSinOrden(Base):
    """Invoice received by AP without a purchase order or service order."""
    __tablename__ = 'facturas_sin_orden'
    __table_args__ = (UniqueConstraint('cliente_id', 'proveedor_ruc', 'serie', 'correlativo', name='uq_factura_sin_orden_documento'),)
    id = Column(String, primary_key=True, default=gen_uuid)
    cliente_id = Column(String, ForeignKey('clientes.id'), nullable=False, index=True)
    sociedad_id = Column(String, ForeignKey('sociedades.id'), nullable=False, index=True)
    usuario_id = Column(String, ForeignKey('usuarios_internos.id'), nullable=False, index=True)
    proveedor_ruc = Column(String(11), nullable=False, index=True)
    proveedor_razon_social = Column(String(200), nullable=False)
    serie = Column(String(10), nullable=False)
    correlativo = Column(String(20), nullable=False)
    fecha_emision = Column(Date, nullable=False)
    moneda = Column(String(3), nullable=False, default='PEN')
    categoria = Column(String(50), nullable=False, default='Otros')
    descripcion = Column(Text)
    centro_costo = Column(String(80))
    cuenta_contable = Column(String(80))
    periodo_servicio = Column(String(20))
    monto_subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    monto_igv = Column(Numeric(14, 2), nullable=False, default=0)
    monto_total = Column(Numeric(14, 2), nullable=False)
    origen = Column(String(20), nullable=False, default='xml')
    estado = Column(String(40), nullable=False, default='Pendiente de revisión')
    nombre_xml = Column(String(255))
    nombre_pdf = Column(String(255))
    xml = Column(LargeBinary)
    pdf = Column(LargeBinary)
    observacion = Column(Text)
    creado_en = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class FacturaSinOrdenEvento(Base):
    __tablename__ = 'facturas_sin_orden_eventos'
    id = Column(String, primary_key=True, default=gen_uuid)
    factura_id = Column(String, ForeignKey('facturas_sin_orden.id', ondelete='CASCADE'), nullable=False, index=True)
    cliente_id = Column(String, ForeignKey('clientes.id'), nullable=False, index=True)
    actor_id = Column(String, ForeignKey('usuarios_internos.id'), nullable=False)
    actor_nombre = Column(String(200), nullable=False)
    accion = Column(String(30), nullable=False)
    estado_anterior = Column(String(40), nullable=False)
    estado_nuevo = Column(String(40), nullable=False)
    comentario = Column(Text)
    creado_en = Column(DateTime, server_default=func.now(), nullable=False)
