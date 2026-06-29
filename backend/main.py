from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import crear_tablas
from auth import router as auth_router

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

@app.get("/")
def root():
    return {"mensaje": "Portal de Proveedores API funcionando"}

@app.get("/health")
def health():
    return {"status": "ok"}
