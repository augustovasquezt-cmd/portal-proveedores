"""Bootstrap explícito del primer administrador de esta instalación.

Define ADMIN_USER, ADMIN_PASSWORD y ADMIN_NAME en el entorno del backend y
ejecuta este archivo una sola vez o al rotar de forma controlada la clave.
No existe registro público de administradores ni endpoint para asignar ese rol.
"""
import os

from auth import get_password_hash
from database import SessionLocal, crear_tablas
from models import UsuarioInterno


usuario = os.getenv('ADMIN_USER', '').strip().lower()
password = os.getenv('ADMIN_PASSWORD', '')
nombre = os.getenv('ADMIN_NAME', 'Administrador de la empresa').strip()
if not usuario or '@' not in usuario:
    raise SystemExit('Define ADMIN_USER con el correo corporativo del administrador.')
if len(password) < 16:
    raise SystemExit('Define ADMIN_PASSWORD con al menos 16 caracteres.')

crear_tablas()
with SessionLocal.begin() as db:
    account = db.query(UsuarioInterno).filter(UsuarioInterno.usuario == usuario).one_or_none()
    if account and account.rol not in {'administrador', 'cuentas_por_pagar'}:
        raise SystemExit('El correo ya está asignado a un rol incompatible.')
    if account:
        account.nombre = nombre
        account.rol = 'administrador'
        account.password_hash = get_password_hash(password)
        account.activo = True
        account.cambio_password_requerido = True
    else:
        db.add(UsuarioInterno(
            usuario=usuario, nombre=nombre, rol='administrador',
            password_hash=get_password_hash(password), activo=True,
            cambio_password_requerido=True,
        ))
print(f'Administrador de empresa listo: {usuario}')
