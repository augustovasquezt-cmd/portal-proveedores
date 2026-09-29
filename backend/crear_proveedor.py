import uuid
from datetime import datetime
from database import SessionLocal
from models import Proveedor
from auth import pwd_context

db = SessionLocal()
ruc = "20999999999"

if db.query(Proveedor).filter(Proveedor.ruc == ruc).first():
    print("El proveedor ya existe")
else:
    p = Proveedor(
        id=str(uuid.uuid4()),
        ruc=ruc,
        razon_social="Ferreter\u00eda La Torre SAC",
        nombre_comercial="Ferreter\u00eda La Torre",
        email="contacto@ferreterialatorre.pe",
        password_hash=pwd_context.hash("Test1234"),
        telefono="987654321",
        direccion="Av. Primavera 123, Surco, Lima",
        estado="activo",
        activo=True,
        creado_en=datetime.utcnow(),
    )
    db.add(p)
    db.commit()
    print("Proveedor creado: RUC 20999999999 / clave Test1234")

db.close()
