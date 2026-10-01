# Seguridad y preparación empresarial

## Propósito

Este documento separa los controles visibles en el código de los controles que dependen del despliegue o de una evaluación externa. Es una guía de implementación; no declara certificación, auditoría independiente ni cumplimiento legal.

## Modelo de acceso

El portal es multiempresa sobre una base de datos compartida. El token identifica el rol y el cliente activo. Los endpoints de facturas y archivos consultan usando ese contexto; Cuentas por pagar queda limitada además a las sociedades asociadas a su usuario. El proveedor consulta únicamente sus documentos dentro del cliente seleccionado. El administrador de cliente administra usuarios y sociedades de ese cliente; la administración IVS provisiona clientes y cupos.

La separación lógica depende de que cada endpoint aplique autorización a cada objeto y acción. Los identificadores no son una autorización. Toda API nueva que consulte una factura, pedido, sociedad, certificado, ticket o archivo debe filtrar por cliente y comprobar rol y asignaciones.

## Controles presentes en el código

- Inicio de sesión con contraseñas almacenadas con hash bcrypt, tokens Bearer firmados y verificación de estado activo de la cuenta y el cliente.
- Roles separados para proveedor, Cuentas por pagar, administrador de cliente y administrador IVS.
- Consultas de facturas con filtro de cliente; proveedor limitado por RUC y cliente; Cuentas por pagar limitada por cliente y sociedades asignadas.
- Descargas XML/PDF con comprobación de acceso al registro de factura; archivos almacenados en registros asociados a la factura, no expuestos por URL pública.
- Límite de 5 MB y lectura XML que bloquea DTD/entidades externas.
- Auditoría de acciones administrativas y flujo de estados de factura.
- Esta actualización: duración de token configurable con valor predeterminado de 60 minutos; CORS configurable con lista permitida, sin credenciales de cookies; documentación API desactivada por defecto fuera del entorno de desarrollo; encabezados de seguridad HTTP; errores de `/auth/me` sin información interna en la respuesta.
- Pruebas para acceso cruzado entre clientes y sociedades, incluidas descargas de XML/PDF.

## Configuración requerida antes de un despliegue productivo

1. Configurar `APP_ENV=production`, `ENABLE_API_DOCS=false`, `CORS_ALLOWED_ORIGINS` con los dominios HTTPS reales, `ENABLE_HSTS=true` detrás de TLS, y un `ACCESS_TOKEN_EXPIRE_MINUTES` apropiado. La API rechaza `*` y exige orígenes HTTPS explícitos en producción.
2. Generar `SECRET_KEY` aleatorio de al menos 32 caracteres y guardar secretos (incluida la clave SAP) en un gestor de secretos; nunca en Git, imágenes, logs o tickets.
3. Terminar TLS en un proxy administrado y verificar TLS entre servicios sensibles. Activar cifrado de base de datos, almacenamiento y respaldos en la plataforma donde se despliegue.
4. Usar MFA para administradores y cuentas privilegiadas; establecer recuperación segura de cuenta, revocación de sesiones y rotación de credenciales.
5. Añadir límites de frecuencia para login, carga de archivos y API; monitorear intentos fallidos, cambios de privilegios, descargas masivas y accesos SAP.
6. Configurar respaldos cifrados, retención aprobada por cada cliente, prueba periódica de restauración, plan de incidentes y responsables de atención.
7. Ejecutar análisis de dependencias y secretos en CI, revisión de código, escaneo dinámico y una prueba de penetración independiente antes de producción; corregir hallazgos y conservar evidencia.

## Criterio de aceptación de aislamiento

Para cada endpoint que recibe un ID, probar al menos: otro cliente; otra sociedad del mismo cliente; otro proveedor; usuario sin sociedad asignada; cuenta desactivada; y archivo adjunto asociado a un documento no autorizado. Las respuestas de recursos ajenos deben ser denegadas sin revelar si el documento existe. Repetir las pruebas en listado, detalle, filtros, exportaciones, acciones y descargas.

## Evidencia para evaluación del cliente

Preparar y mantener: diagrama de flujo de datos; matriz de roles y sociedades; inventario de datos y ubicaciones; configuración de cifrado y respaldos del entorno; política de retención y eliminación; procedimiento de incidentes; resumen de pruebas de aislamiento; reporte ejecutivo de prueba de penetración; inventario de subprocesadores; y guía de conexión SAP con ciclo de rotación de secretos.

## Referencias de trabajo

- OWASP ASVS 5.0 como lista de requisitos verificables para la aplicación.
- OWASP API Security Top 10, en particular autorización de objetos y funciones.
- NIST SP 800-218 (SSDF) para integrar prácticas seguras en el ciclo de desarrollo.

Estas referencias sirven como objetivos de ingeniería. Usarlas no implica certificación ni conformidad automática.
