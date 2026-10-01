import os
import json
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from models import (
    Base, Cliente, Sociedad, Proveedor, ProveedorCliente, ProveedorSociedad,
    UsuarioInterno, UsuarioSociedad, Factura, FacturaRegistro,
)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def crear_tablas():
    Base.metadata.create_all(bind=engine)
    client_columns = {column['name'] for column in inspect(engine).get_columns('clientes')}
    if 'sap_api_key_hash' not in client_columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE clientes ADD COLUMN sap_api_key_hash VARCHAR(64)'))
    society_columns = {column['name'] for column in inspect(engine).get_columns('sociedades')}
    if 'es_principal' not in society_columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE sociedades ADD COLUMN es_principal BOOLEAN NOT NULL DEFAULT FALSE'))
    # Tenant columns are nullable during the one-time backfill so the existing
    # installation can be migrated without dropping any portal data.
    tenant_columns = [
        ('usuarios_internos', 'cliente_id'),
        ('ordenes_compra', 'cliente_id'),
        ('ordenes_compra', 'sociedad_id'),
        ('facturas', 'cliente_id'),
        ('tickets', 'cliente_id'),
        ('documentos_base', 'cliente_id'),
        ('factura_envios_sap', 'cliente_id'),
        ('factura_eventos', 'cliente_id'),
        ('solicitudes_cuentas_por_pagar', 'cliente_id'),
        ('certificados_retencion', 'cliente_id'),
        ('registros_auditoria', 'cliente_id'),
        ('facturas', 'sociedad_id'),
        ('factura_registros', 'sociedad_id'),
    ]
    for table, name in tenant_columns:
        columns = {column['name'] for column in inspect(engine).get_columns(table)}
        if name not in columns:
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} VARCHAR'))
    # Force initial password rotation for accounts created or reset by an administrator.
    for table in ('proveedores', 'usuarios_internos'):
        columns = {column['name'] for column in inspect(engine).get_columns(table)}
        if 'cambio_password_requerido' not in columns:
            with engine.begin() as connection:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN cambio_password_requerido BOOLEAN NOT NULL DEFAULT FALSE'))
    # Additive migration for databases created before destination societies were selectable.
    columns = {column['name'] for column in inspect(engine).get_columns('factura_registros')}
    if 'ruc_receptor' not in columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE factura_registros ADD COLUMN ruc_receptor VARCHAR(11)'))
    # Additive migration: keep old PO rows as materials while retaining the
    # SAP service-package and service-line references for new service rows.
    position_columns = {column['name'] for column in inspect(engine).get_columns('orden_posiciones')}
    migrations = {
        'tipo': "ALTER TABLE orden_posiciones ADD COLUMN tipo VARCHAR(20) NOT NULL DEFAULT 'material'",
        'codigo_servicio': 'ALTER TABLE orden_posiciones ADD COLUMN codigo_servicio VARCHAR(50)',
        'paquete_servicio': 'ALTER TABLE orden_posiciones ADD COLUMN paquete_servicio VARCHAR(20)',
        'numero_servicio': 'ALTER TABLE orden_posiciones ADD COLUMN numero_servicio VARCHAR(20)',
    }
    missing = [statement for name, statement in migrations.items() if name not in position_columns]
    if missing:
        with engine.begin() as connection:
            for statement in missing:
                connection.execute(text(statement))
    # Additive AP workflow fields; existing supplier invoice records remain intact.
    factura_columns = {column['name'] for column in inspect(engine).get_columns('facturas')}
    factura_migrations = {
        'recibida_contabilidad_en': 'ALTER TABLE facturas ADD COLUMN recibida_contabilidad_en TIMESTAMP',
        'aceptada_portal_en': 'ALTER TABLE facturas ADD COLUMN aceptada_portal_en TIMESTAMP',
        'fecha_pago_programada': 'ALTER TABLE facturas ADD COLUMN fecha_pago_programada DATE',
        'pagada_en': 'ALTER TABLE facturas ADD COLUMN pagada_en TIMESTAMP',
        'motivo_rechazo': 'ALTER TABLE facturas ADD COLUMN motivo_rechazo TEXT',
    }
    missing_facturas = [statement for name, statement in factura_migrations.items() if name not in factura_columns]
    if missing_facturas:
        with engine.begin() as connection:
            for statement in missing_facturas:
                connection.execute(text(statement))
    # Additive migration for AP invoices entered without a PO/OS. The table
    # may already exist from an earlier schema version without coding fields.
    sin_orden_columns = {column['name'] for column in inspect(engine).get_columns('facturas_sin_orden')}
    sin_orden_migrations = {
        'centro_costo': 'ALTER TABLE facturas_sin_orden ADD COLUMN centro_costo VARCHAR(80)',
        'cuenta_contable': 'ALTER TABLE facturas_sin_orden ADD COLUMN cuenta_contable VARCHAR(80)',
        'periodo_servicio': 'ALTER TABLE facturas_sin_orden ADD COLUMN periodo_servicio VARCHAR(20)',
    }
    missing_sin_orden = [statement for name, statement in sin_orden_migrations.items() if name not in sin_orden_columns]
    if missing_sin_orden:
        with engine.begin() as connection:
            for statement in missing_sin_orden:
                connection.execute(text(statement))
    migrar_instalacion_a_tenant_inicial()


def migrar_instalacion_a_tenant_inicial():
    """Backfill the single-company prototype into a preserved demo tenant."""
    codigo = 'ferreteria-demo'
    config_path = Path(__file__).with_name('portal_config.json')
    try:
        config = json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        config = {}
    rows = config.get('sociedades') or []

    with SessionLocal.begin() as db:
        tenant = db.query(Cliente).filter(Cliente.codigo == codigo).one_or_none()
        if tenant is None:
            tenant = Cliente(
                id='cliente-demo-ferreteria', codigo=codigo,
                nombre='Ferretería La Torre SAC', activo=True,
                max_administradores=1, max_cuentas_por_pagar=5,
                max_proveedores=50, max_sociedades=max(10, len(rows)),
            )
            db.add(tenant)
            db.flush()

        for row in rows:
            if not isinstance(row, dict):
                continue
            ruc = str(row.get('ruc', '')).strip()
            if len(ruc) != 11 or not ruc.isdigit():
                continue
            society = db.query(Sociedad).filter(
                Sociedad.cliente_id == tenant.id, Sociedad.ruc == ruc,
            ).one_or_none()
            if society is None:
                society = Sociedad(
                    cliente_id=tenant.id, ruc=ruc,
                    razon_social=str(row.get('razon_social') or 'Sociedad receptora').strip(),
                    codigo_sap=str(row.get('codigo_sap') or '').strip() or None,
                    activo=True,
                )
                db.add(society)

        db.flush()
        if db.query(Sociedad.id).filter(Sociedad.cliente_id == tenant.id, Sociedad.es_principal.is_(True)).first() is None:
            principal = db.query(Sociedad).filter(
                Sociedad.cliente_id == tenant.id, Sociedad.ruc == '20999999999',
            ).one_or_none()
            if principal is None:
                principal = db.query(Sociedad).filter_by(cliente_id=tenant.id).order_by(Sociedad.creado_en, Sociedad.id).first()
            if principal is not None:
                principal.es_principal = True
        for model in (Factura,):
            db.query(model).filter(model.cliente_id.is_(None)).update(
                {model.cliente_id: tenant.id}, synchronize_session=False,
            )
        from models import OrdenCompra, Ticket, DocumentoBase, FacturaEnvioSAP, FacturaEvento, SolicitudCuentasPorPagar, CertificadoRetencion
        for model in (OrdenCompra, Ticket, DocumentoBase, FacturaEnvioSAP, FacturaEvento, SolicitudCuentasPorPagar, CertificadoRetencion):
            db.query(model).filter(model.cliente_id.is_(None)).update(
                {model.cliente_id: tenant.id}, synchronize_session=False,
            )
        db.query(UsuarioInterno).filter(
            UsuarioInterno.cliente_id.is_(None), UsuarioInterno.rol != 'administrador_ivs',
        ).update({UsuarioInterno.cliente_id: tenant.id}, synchronize_session=False)

        suppliers = db.query(Proveedor).all()
        for supplier in suppliers:
            membership = db.query(ProveedorCliente).filter_by(
                proveedor_id=supplier.id, cliente_id=tenant.id,
            ).one_or_none()
            if membership is None:
                membership = ProveedorCliente(
                    proveedor_id=supplier.id, cliente_id=tenant.id,
                    activo=bool(supplier.activo),
                )
                db.add(membership)
                db.flush()
            for society in db.query(Sociedad).filter_by(cliente_id=tenant.id, activo=True).all():
                assigned = db.query(ProveedorSociedad).filter_by(
                    proveedor_cliente_id=membership.id, sociedad_id=society.id,
                ).one_or_none()
                if assigned is None:
                    db.add(ProveedorSociedad(
                        cliente_id=tenant.id, proveedor_cliente_id=membership.id,
                        sociedad_id=society.id,
                    ))

        societies = db.query(Sociedad).filter_by(cliente_id=tenant.id, activo=True).all()
        demo_society = next((society for society in societies if society.ruc == '20999999999'), None)
        if demo_society is None and len(societies) == 1:
            demo_society = societies[0]
        if demo_society:
            db.query(OrdenCompra).filter(OrdenCompra.cliente_id == tenant.id, OrdenCompra.sociedad_id.is_(None)).update(
                {OrdenCompra.sociedad_id: demo_society.id}, synchronize_session=False,
            )
        internal_users = db.query(UsuarioInterno).filter(
            UsuarioInterno.cliente_id == tenant.id,
            UsuarioInterno.rol == 'cuentas_por_pagar',
        ).all()
        for user in internal_users:
            for society in societies:
                assigned = db.query(UsuarioSociedad).filter_by(
                    usuario_id=user.id, sociedad_id=society.id,
                ).one_or_none()
                if assigned is None:
                    db.add(UsuarioSociedad(
                        cliente_id=tenant.id, usuario_id=user.id, sociedad_id=society.id,
                    ))

        for registry in db.query(FacturaRegistro).filter(FacturaRegistro.sociedad_id.is_(None)).all():
            society = db.query(Sociedad).filter_by(
                cliente_id=tenant.id, ruc=registry.ruc_receptor,
            ).one_or_none()
            if society:
                registry.sociedad_id = society.id

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
