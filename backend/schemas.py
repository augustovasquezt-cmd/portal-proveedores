from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import date, datetime

from typing import List, Optional
from decimal import Decimal
from datetime import date, datetime

# Esquemas para Facturas
class FacturaLineaBase(BaseModel):
    numero_linea: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    monto_subtotal: Decimal
    igv: Decimal
    monto_total: Decimal
    codigo_producto: Optional[str] = None


class FacturaLineaCreate(FacturaLineaBase):
    pass


class FacturaLineaResponse(FacturaLineaBase):
    id: int
    factura_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class FacturaBase(BaseModel):
    numero_comprobante: str
    serie: Optional[str] = None
    correlativo: Optional[str] = None
    fecha_emision: date
    monto_subtotal: Decimal
    monto_igv: Decimal
    monto_total: Decimal
    estado: Optional[str] = "Emitida"
    cae: Optional[str] = None


class FacturaCreate(FacturaBase):
    lineas: List[FacturaLineaCreate]


class FacturaResponse(FacturaBase):
    id: str
    proveedor_id: str
    creado_en: datetime
    lineas: List[FacturaLineaResponse]

    class Config:
        from_attributes = True


class FacturaListResponse(BaseModel):
    id: str
    numero_comprobante: str
    fecha_emision: date
    monto_total: Decimal
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True
        # Esquemas Facturas
class FacturaLineaBase(BaseModel):
    numero_linea: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    monto_subtotal: Decimal
    igv: Decimal
    monto_total: Decimal
    codigo_producto: Optional[str] = None

class FacturaLineaResponse(FacturaLineaBase):
    id: int
    factura_id: str
    created_at: datetime

    class Config:
        from_attributes = True

class FacturaResponse(BaseModel):
    id: str
    numero_comprobante: str
    fecha_emision: date
    monto_subtotal: Decimal
    monto_igv: Decimal
    monto_total: Decimal
    estado: str
    creado_en: datetime
    lineas: List[FacturaLineaResponse]

    class Config:
        from_attributes = True

class FacturaListResponse(BaseModel):
    id: str
    numero_comprobante: str
    fecha_emision: date
    monto_total: Decimal
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True

class FacturaCreate(BaseModel):
    numero_comprobante: str
    serie: Optional[str] = None
    correlativo: Optional[str] = None
    fecha_emision: date
    monto_subtotal: Decimal
    monto_igv: Decimal
    monto_total: Decimal

class FacturaLineaCreate(BaseModel):
    numero_linea: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    monto_subtotal: Decimal
    igv: Decimal
    monto_total: Decimal
    codigo_producto: Optional[str] = None