"""Bootstrap idempotente de una cuenta superadministradora IVS.

Uso: establecer IVS_ADMIN_USER, IVS_ADMIN_NAME y IVS_ADMIN_PASSWORD en el
entorno antes de ejecutar este script. Nunca crea una cuenta si ya existe.
"""
import os
from uuid import uuid4

from auth import get_password_hash
from database import SessionLocal, crear_tablas
from models import UsuarioInterno


def main():
    usuario = os.getenv('IVS_ADMIN_USER', '').strip().lower()
    nombre = os.getenv('IVS_ADMIN_NAME', '').strip()
    password = os.getenv('IVS_ADMIN_PASSWORD', '')
    if not usuario or not nombre or len(password) < 12:
        raise SystemExit('Define IVS_ADMIN_USER, IVS_ADMIN_NAME y IVS_ADMIN_PASSWORD (mínimo 12 caracteres).')
    crear_tablas()
    with SessionLocal.begin() as db:
        existing = db.query(UsuarioInterno).filter(UsuarioInterno.usuario == usuario).first()
        if existing:
            raise SystemExit('Ese usuario ya existe; no se modificó ninguna cuenta.')
        db.add(UsuarioInterno(id=str(uuid4()), usuario=usuario, nombre=nombre, rol='administrador_ivs', cliente_id=None, password_hash=get_password_hash(password), activo=True, cambio_password_requerido=False))
    print(f'Cuenta de administración IVS creada: {usuario}')


if __name__ == '__main__':
    main()
