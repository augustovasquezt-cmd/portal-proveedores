from sqlalchemy import Column, String, Boolean, DateTime, Text, Numeric, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid
import enum

Base = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())

class EstadoProveedor(str, enum.Enum):
    pendiente = "pendiente"
    en_revision = "en_revision"
    aprobado = "aprobado"
    rechazado = "rechazado"

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
    creado_en = Column(DateTime, server_default=func.now())

class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"
    id = Column(String, primary_key=True, default=gen_uuid)
    numero = Column(String(50), unique=True, nullable=False)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)
    estado = Column(String(30), default="por_recepcionar")
    descripcion = Column(Text)
    creado_en = Column(DateTime, server_default=func.now())

class Factura(Base):
    __tablename__ = "facturas"
    id = Column(String, primary_key=True, default=gen_uuid)
    serie = Column(String(10), nullable=False)
    correlativo = Column(String(10), nullable=False)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False)
    orden_compra_id = Column(String, ForeignKey("ordenes_compra.id"))
    monto_subtotal = Column(Numeric(12, 2), nullable=False)
    monto_igv = Column(Numeric(12, 2), nullable=False)
    monto_total = Column(Numeric(12, 2), nullable=False)
    estado = Column(String(30), default="en_revision")
    cae = Column(String(100))
    creado_en = Column(DateTime, server_default=func.now())

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(String, primary_key=True, default=gen_uuid)
    numero = Column(String(20), unique=True, nullable=False)
    proveedor_id = Column(String, ForeignKey("proveedores.id"), nullable=False)
    asunto = Column(String(200), nullable=False)
    descripcion = Column(Text)
    categoria = Column(String(50))
    prioridad = Column(String(20), default="normal")
    estado = Column(String(20), default="abierto")
    creado_en = Column(DateTime, server_default=func.now())
