# Portal multiempresa para IVS

## Decisiones de producto

- IVS provisiona clientes, sociedades receptoras/RUC, cupos, administradores del cliente y credenciales SAP por cliente.
- Al crear el cliente se registra también su RUC principal como primera sociedad receptora. Los RUC adicionales se añaden solo cuando el grupo tiene otras sociedades; el principal no se puede desactivar.
- Cada cliente administra sus usuarios de Cuentas por Pagar y habilita proveedores, con límites de administradores, usuarios AP, proveedores y sociedades configurados por IVS.
- La identidad del proveedor es global por RUC. Un proveedor conserva una contraseña y puede tener membresías en varios clientes; al iniciar sesión selecciona el cliente habilitado.
- Usuarios AP y proveedores reciben asignaciones de una o más sociedades del cliente. La misma sociedad puede relacionarse con varios usuarios y proveedores.
- Una factura se asocia a un solo cliente y sociedad receptora. Puede agrupar posiciones de varias órdenes del mismo proveedor solo cuando cliente y sociedad coinciden.

## Implementación en esta versión

- Tablas/modelos multiempresa: `Cliente`, `Sociedad`, membresía `ProveedorCliente`, y asignaciones `UsuarioSociedad`/`ProveedorSociedad`.
- El token de negocio incluye el cliente seleccionado; las dependencias de API verifican rol, cliente activo y membresía. Órdenes, facturas, adjuntos, tickets, flujos AP, certificados de retención e integración SAP filtran por tenant; cuando aplica, también filtran por sociedades asignadas.
- IVS dispone de APIs y panel para alta de clientes, cuotas, sociedades, administradores y rotación de secreto SAP. El secreto SAP se guarda en hash y se muestra solo al rotarlo.
- IVS puede editar código/nombre del cliente, modificar sus cupos y añadir/desactivar sociedades adicionales. La sociedad principal y el grupo se muestran juntos en la vista de administración.
- El administrador cliente crea AP/proveedores, asigna sociedades, activa/desactiva miembros y consulta cupos. No crea sociedades, administradores ni modifica cupos.
- Se conservan datos del prototipo en el tenant demo `ferreteria-demo`; se crean membresías y asignaciones iniciales a partir de la configuración anterior.

## Rutas de administración principales

- IVS: `/ivs/clientes` y `/dashboard/ivs/clientes`.
- Cliente: `/administracion/cupos`, `/administracion/sociedades`, `/administracion/usuarios` y rutas hijas de asignación.
- Proveedor con más de un cliente: login seguido de `/auth/seleccionar-cliente`.
- API SAP de retenciones: credencial Bearer separada por cliente, provisionada/rotada por IVS.

## Estado de la migración y producción

La aplicación ejecuta actualmente una migración de desarrollo aditiva al arrancar y asigna el conjunto antiguo al tenant demo. Esto conserva la demo local, pero **no reemplaza una migración de producción versionada, revisable y respaldada**. Antes de incorporar datos reales o habilitar otros clientes:

1. Crear migraciones versionadas y reversibles (por ejemplo, Alembic), con copia de seguridad y ensayo sobre una copia representativa de la base.
2. Revisar/reconstruir las restricciones únicas heredadas que antes eran globales (número de orden, número de ticket/documento/certificado) para que incluyan `cliente_id`; `create_all` no cambia restricciones existentes.
3. Verificar y corregir las asignaciones demo (especialmente RUC receptor de órdenes y facturas); los datos de ejemplo no son datos SAP reales.
4. Completar pruebas de aislamiento entre al menos dos clientes para todos los recursos y descargas, así como carreras concurrentes en cuotas y altas. En producción las cuotas deben reservarse transaccionalmente y contar con restricciones/locking acordes al motor de base de datos.
5. Configurar almacenamiento privado de adjuntos, gestión de secretos, HTTPS, auditoría/retención de logs, respaldos, límites operativos y políticas de privacidad.
6. Implementar y probar la integración ABAP/SAP por cliente (ECC, S/4HANA on-premise y S/4HANA Cloud Public Edition/GROW). El portal aún no crea documentos reales en SAP hasta que se configure e implemente esa interfaz.

El backend de esta rama es una base funcional de demo y contrato de integración, no una certificación de seguridad ni un despliegue productivo multiempresa.
