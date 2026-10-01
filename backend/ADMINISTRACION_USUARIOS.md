# Gestión de usuarios y roles

## Modelo de acceso

La pantalla de inicio acepta un solo identificador. El backend lo interpreta como RUC de proveedor cuando contiene 11 dígitos, o como correo corporativo de una cuenta interna. La interfaz no selecciona ni concede roles: estos salen del registro activo en la base de datos y cada API aplica su propia dependencia de autorización.

Roles disponibles:

- `proveedor`: consulta y gestiona sus propios documentos.
- `cuentas_por_pagar`: bandeja interna de comprobantes.
- `administrador`: gestión de usuarios de la empresa y cuentas de proveedor de esta instalación.

La cuenta administradora no se crea desde la UI ni desde una llamada pública. Se crea con el bootstrap controlado y debe cambiar su clave en el primer ingreso. El administrador de empresa puede crear analistas de cuentas por pagar y proveedores, activarlos/desactivarlos y generarles una contraseña temporal. La API no permite asignar `administrador` ni cambiar el rol de una cuenta desde el panel.

## Bootstrap inicial

El `.env` local del backend ya tiene un `SECRET_KEY` aleatorio para firmar sesiones. Está ignorado por Git y su valor no debe compartirse. Al cambiarlo, los usuarios deberán iniciar sesión de nuevo.

En PowerShell, desde `backend`, define las variables para el administrador inicial y ejecuta el script de bootstrap:

```powershell
$env:ADMIN_USER = 'admin@empresa.com'
$env:ADMIN_NAME = 'Administrador de la empresa'
$env:ADMIN_PASSWORD = 'usa-una-frase-larga-y-unica-de-16-caracteres-o-mas'
python .\seed_administrador.py
```

Si ese Python no encuentra las dependencias, crea el entorno del proyecto e instala `requirements.txt` una vez; no uses una ruta `.venv` hasta haber creado ese entorno. No pongas la clave administrativa en Git, en una captura o en un comando compartido.

## Contrato de API administrativo

Todas las rutas requieren un token Bearer de un usuario con rol `administrador`; los controladores consultan además que la cuenta siga activa en la base de datos.

- `GET /administracion/usuarios`: listas internas y de proveedores sin hashes ni contraseñas.
- `POST /administracion/usuarios/cuentas-por-pagar` con `{ "usuario": "analista@empresa.com", "nombre": "Nombre Apellido" }`.
- `POST /administracion/usuarios/proveedores` con `{ "ruc": "20999999999", "razon_social": "Proveedor Demo SAC", "email": "proveedor@demo.pe" }`.
- `PATCH /administracion/usuarios/internos/{id}` con `{ "activo": false }`.
- `PATCH /administracion/usuarios/proveedores/{id}` con `{ "activo": false }`.
- `POST /administracion/usuarios/internos/{id}/restablecer-password`.
- `POST /administracion/usuarios/proveedores/{id}/restablecer-password`.

Las operaciones de creación, estado y restablecimiento dejan una fila en `registros_auditoria` con actor, acción, objetivo y hora. Las claves temporales se generan aleatoriamente, se devuelven una sola vez al administrador, se guardan en la base solo como hash y fuerzan un cambio de mínimo 12 caracteres antes de poder llamar a otras APIs. Tras cambiarla, el portal emite un token nuevo. Desactivar una cuenta bloquea también sus sesiones existentes.

El panel está disponible en `/dashboard/administracion/usuarios`. El primer administrador entra con correo y contraseña en la pantalla normal; no hay selector de perfil.

## Alcance de instalación

Las tablas actuales del portal pertenecen a una única instalación de empresa: no hay `tenant_id` en sus proveedores, pedidos y facturas. Por eso este administrador ve las cuentas de esa instalación. Antes de servir varias empresas clientes desde una sola base compartida, hay que añadir aislamiento por tenant a todas las tablas y consultas, y limitar a cada administrador a su propio tenant; el rol por sí solo no sustituye ese alcance.
