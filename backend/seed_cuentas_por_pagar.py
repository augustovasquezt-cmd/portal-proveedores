"""Crea/actualiza un usuario interno de demostración para Cuentas por pagar.

Uso: AP_USER=ap@demo.local AP_PASSWORD='...' AP_NAME='Cuentas por pagar' python seed_cuentas_por_pagar.py
"""
import os
from database import SessionLocal, crear_tablas
from auth import get_password_hash
from models import UsuarioInterno

crear_tablas()
usuario = os.getenv("AP_USER", "ap@demo.local").strip().lower()
password = os.getenv("AP_PASSWORD")
nombre = os.getenv("AP_NAME", "Analista de cuentas por pagar").strip()
if not password or len(password) < 12:
    raise SystemExit("Define AP_PASSWORD con al menos 12 caracteres antes de ejecutar el seed.")
with SessionLocal.begin() as db:
    account = db.query(UsuarioInterno).filter(UsuarioInterno.usuario == usuario).one_or_none()
    if account:
        if account.rol != "cuentas_por_pagar":
            raise SystemExit("Ese correo ya pertenece a otro rol; no se modificó la cuenta.")
        account.nombre = nombre
        account.password_hash = get_password_hash(password)
        account.activo = True
        account.cambio_password_requerido = False
    else:
        db.add(UsuarioInterno(usuario=usuario, nombre=nombre, rol="cuentas_por_pagar", password_hash=get_password_hash(password), activo=True))
print(f"Usuario interno listo: {usuario}")
