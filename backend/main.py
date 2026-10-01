import os

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from database import crear_tablas, get_db
from auth import router as auth_router, get_current_user
from ordenes import router as ordenes_router
from models import Factura, FacturaLinea, Proveedor
from schemas import FacturaListResponse, FacturaResponse

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
is_development = APP_ENV == "development"
docs_enabled = os.getenv("ENABLE_API_DOCS", "true" if is_development else "false").strip().lower() in {"1", "true", "yes"}
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
if "*" in allowed_origins:
    raise RuntimeError("CORS_ALLOWED_ORIGINS no puede incluir el comodín '*'.")
if APP_ENV == "production" and (not allowed_origins or any(not origin.startswith("https://") for origin in allowed_origins)):
    raise RuntimeError("En producción, CORS_ALLOWED_ORIGINS debe contener solo orígenes HTTPS explícitos.")

app = FastAPI(
    title="Portal de Proveedores API",
    version="1.0.0",
    description="API para órdenes de compra, registro y seguimiento de facturas, documentos de referencia e incidencias del portal de proveedores.",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Next.js may select another local port when 3000 is already occupied.
    # Keep this convenience limited to development; production uses explicit HTTPS origins.
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):3\d{3}" if is_development else None,
    # The API uses Authorization bearer tokens, not cross-site cookies.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if os.getenv("ENABLE_HSTS", "false").strip().lower() in {"1", "true", "yes"}:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

crear_tablas()
app.include_router(auth_router)
app.include_router(ordenes_router)

@app.get("/", summary="Verificar disponibilidad de la API", tags=["sistema"])
def root():
    return {"mensaje": "Portal de Proveedores API funcionando"}

@app.get("/health", summary="Comprobar estado del servicio", tags=["sistema"])
def health():
    return {"status": "ok"}


from facturas import router as facturas_router
app.include_router(facturas_router)
from posiciones import router as posiciones_router
app.include_router(posiciones_router)
from documentos_base import router as documentos_base_router
app.include_router(documentos_base_router)
from sap_integracion import router as sap_router
app.include_router(sap_router)

from tickets import router as tickets_router
app.include_router(tickets_router)
from cuentas_por_pagar import router as cuentas_por_pagar_router
app.include_router(cuentas_por_pagar_router)
from facturas_sin_orden import router as facturas_sin_orden_router
app.include_router(facturas_sin_orden_router)
from carga_masiva_facturas_oc import router as carga_masiva_facturas_oc_router
app.include_router(carga_masiva_facturas_oc_router)
from retenciones import router as retenciones_router
app.include_router(retenciones_router)
from administracion import router as administracion_router
app.include_router(administracion_router)
from ivs import router as ivs_router
app.include_router(ivs_router)
