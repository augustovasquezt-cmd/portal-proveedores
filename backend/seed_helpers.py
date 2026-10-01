"""Helpers para cargar datos de demostración en el tenant demo de forma explícita."""
from fastapi import HTTPException
from models import Cliente, Sociedad


DEMO_CLIENT_CODE = 'ferreteria-demo'
DEMO_RECEIVER_RUC = '20999999999'


def demo_context(db):
    client = db.query(Cliente).filter(Cliente.codigo == DEMO_CLIENT_CODE, Cliente.activo.is_(True)).one_or_none()
    if not client:
        raise RuntimeError('Primero ejecuta la migración inicial para crear el cliente de demo.')
    society = db.query(Sociedad).filter(Sociedad.cliente_id == client.id, Sociedad.ruc == DEMO_RECEIVER_RUC, Sociedad.activo.is_(True)).one_or_none()
    if not society:
        raise RuntimeError('IVS debe habilitar la sociedad de demo antes de cargar pedidos de ejemplo.')
    return client, society
