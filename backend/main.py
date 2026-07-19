from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from database import crear_tablas, get_db
from auth import router as auth_router, get_current_user
from ordenes import router as ordenes_router
from models import Factura, FacturaLinea, Proveedor
from schemas import FacturaListResponse, FacturaResponse

app = FastAPI(title="Portal de Proveedores API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

crear_tablas()
app.include_router(auth_router)
app.include_router(ordenes_router)

@app.get("/")
def root():
    return {"mensaje": "Portal de Proveedores API funcionando"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/facturas", response_model=List[FacturaListResponse])
async def listar_facturas(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        ruc = current_user.get("ruc")
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == ruc).first()
        if not proveedor:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        
        facturas = db.query(Factura).filter(
            Factura.proveedor_id == proveedor.id
        ).order_by(Factura.creado_en.desc()).all()
        
        return facturas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/facturas/{factura_id}", response_model=FacturaResponse)
async def obtener_factura(
    factura_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        ruc = current_user.get("ruc")
        proveedor = db.query(Proveedor).filter(Proveedor.ruc == ruc).first()
        if not proveedor:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        
        factura = db.query(Factura).filter(
            Factura.id == factura_id,
            Factura.proveedor_id == proveedor.id
        ).first()
        
        if not factura:
            raise HTTPException(status_code=404, detail="Factura no encontrada")
        
        return factura
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
