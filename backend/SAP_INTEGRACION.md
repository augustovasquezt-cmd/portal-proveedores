# Preparación de integración SAP

## Estado de esta rama

- El portal valida y persiste la factura, sus posiciones, XML/PDF y un registro local en `factura_envios_sap` en una transacción.
- Las posiciones pueden ser materiales o servicios. Una posición de servicio conserva su posición SAP de pedido y las referencias de paquete/subposición; para facturarla se exige una hoja de entrada de servicios (HES/SES) aceptada y se limita la cantidad a lo aceptado que aún no se facturó.
- `sap_integracion.preparar` genera un contrato interno versionado y guarda las referencias de pedido/posición y documentos de base.
- `sap_ecc_contrato.preparar_datos_bapi` transforma ese contrato en `HEADERDATA` e `ITEMDATA` para revisión/pruebas unitarias. No abre conexión RFC, no crea ni contabiliza documentos y no confirma que los campos sean compatibles con un ECC particular.
- `POST /integracion-sap/simulador/ecc/facturas/{factura_id}` prepara una factura propia y devuelve un acuse simulado sin llamar SAP ni modificar datos. Está disponible para probar el contrato desde ReDoc.
- El endpoint `/integracion-sap/estado` sigue informando que no hay conexión activa. No hay sincronización entrante de pedidos, estados de factura ni pagos.

### Probar el simulador local desde ReDoc

1. Habilita el simulador solo para el backend local. En PowerShell, antes de iniciar Uvicorn, ejecuta `$env:SAP_SIMULADOR_HABILITADO = "true"`; luego reinicia el backend. También se puede poner `SAP_SIMULADOR_HABILITADO=true` en el `.env` que carga el backend. La ruta devuelve 404 mientras la bandera no esté habilitada.
2. Inicia sesión en el portal y copia el `access_token`.
3. En `/docs`, pulsa **Authorize** e ingresa el token. Swagger añade el prefijo `Bearer` automáticamente.
4. Registra una factura de prueba en el portal y copia su ID de respuesta, o búscala en `GET /facturas`.
5. Ejecuta `POST /integracion-sap/simulador/ecc/facturas/{factura_id}` con un cuerpo de este tipo:

```json
{
  "sociedad": "1000",
  "proveedor_sap": "0000100001",
  "fecha_contabilizacion": "2026-09-29",
  "codigos_impuesto": {"18.00": "V1"}
}
```

La respuesta debe decir `modo: simulacion_local`, `sap_contactado: false` y `persistido: false`; `referencia_simulada` es ficticia. Un 422 señala datos faltantes o un impuesto sin mapear; 404 indica simulador deshabilitado o factura inexistente para ese proveedor; 409 indica que aún no se generó el contrato local. Estos códigos no reflejan errores reales de ECC. No habilitar esta bandera en producción.

Las APIs del portal son el contrato estable para la interfaz web. Los adaptadores convierten entre ese contrato y cada cliente ERP; no se deben exponer credenciales SAP al navegador ni convertir el frontend en consumidor directo de SAP.

## Preparación para ECC

La traducción inicial está en `sap_ecc_contrato.py`. Para ejecutarla requiere como configuración del cliente, fuera del código:

1. Versión exacta de ECC/EHP y SAP_APPL; confirmar en SE37/BAPI Explorer las funciones instaladas, sus parámetros, extensiones y notas aplicables.
2. Sociedad, proveedor SAP asociado al RUC, moneda y fecha de contabilización. El proveedor no se deduce del RUC en el momento del envío.
3. Pedidos y posiciones con los números reales de SAP. No se deben integrar datos DEMO.
4. Mapeo explícito de tasa/escenario tributario a código de impuesto SAP. El mapeador falla si falta un código; no inventa uno.
5. Política de recepción basada en pedido, ingreso de mercancía, aceptación de servicio o guía, incluyendo el número/año/posición del documento de referencia.
6. Decidir si la primera entrega aparca la factura para revisión o la contabiliza. La fecha de emisión y la fecha de contabilización son campos distintos.
7. Definir transporte RFC o un servicio puente, red/VPN, usuario técnico de mínimo privilegio, secretos, certificados y monitoreo. Un middleware no es obligatorio para todos los clientes, pero conectividad y autenticación sí.
8. Definir repositorio de adjuntos. XML/PDF quedan en el portal; su transferencia a SAP requiere acordar ArchiveLink/DMS u otro repositorio y enviar la referencia correspondiente. No se adjuntan binarios a `ITEMDATA`.

El primer mapeo de factura por pedido/posición incluye cabecera (fecha de documento, fecha de contabilización, sociedad, moneda, total y referencia externa) y una línea por cada posición SAP, incluso si una factura agrupa líneas de varios pedidos. `supplier_sap` se conserva como contexto de mapeo para comprobar la relación del proveedor; el mapeador no lo fuerza dentro de un campo SAP cuya semántica debe validarse en la versión objetivo.

El módulo puro produce una propuesta con nombres comunes de campos BAPI y requiere revisión contra la interfaz real del cliente. No selecciona automáticamente `BAPI_INCOMINGINVOICE_CREATE`, `BAPI_INCOMINGINVOICE_PARK` o `BAPI_INCOMINGINVOICE_CREATE1`: la disponibilidad y semántica dependen de la versión y del proceso elegido. En ECC, SAP documenta `BAPI_INCOMINGINVOICE_CREATE1` para retener, aparcar, aparcar completa o contabilizar a partir de SAP_APPL 605; hay que confirmar el sistema concreto. Para una llamada transaccional, la implementación RFC debe gestionar retorno `RETURN`, commit solo si no hay errores y rollback cuando corresponda; un timeout requiere reconciliación antes de reintentar.

### Posiciones de servicios y hojas de entrada

El modelo guarda cada renglón de especificación como una fila hija asociada a la posición principal del pedido. `numero` es la posición SAP del pedido; `paquete_servicio`, `numero_servicio` y `codigo_servicio` preservan la identidad de la especificación. La HES/SES aceptada se representa con `documentos_base` de tipo `servicio` y líneas que referencian esas filas. El portal impide registrar servicio sin esa referencia y evita usar una recepción de mercancía como si fuera aceptación de servicio. En la pantalla de pedidos se muestran el paquete, sublínea, cantidad pedida, aceptada, facturada y saldo.

El contrato ECC conserva el contexto de HES y especificación en `SERVICE_CONTEXT`, junto con el pedido y posición SAP. Esto es intencionalmente contexto del adaptador: el mapeo final a tablas de servicios/hojas de entrada de la BAPI debe confirmarse en el release ECC, customizing y variante del cliente. No se deben enviar las sublíneas como si fueran materiales separados ni asumir que cada ECC expone la misma estructura de servicio.

Para revisar el flujo local se puede ejecutar `python seed_servicios.py` desde `backend` después de crear la empresa demo. Agrega el pedido `DEMO-OC-SERV-0002` con dos líneas de servicio bajo la posición SAP `00010` y una HES aceptada parcial `DEMO-HES-0002`.

## Preparación para pedidos, facturas y pagos entrantes

El siguiente contrato de sincronización debe normalizar por tenant/cliente al menos:

- Proveedor SAP, RUC, sociedad y asignaciones organizativas autorizadas.
- Pedido de compra y posiciones: número, posición, proveedor, sociedad, material/servicio, descripción, unidad, cantidad, precio, impuesto, moneda, estado, saldo y cantidades ya recibidas/facturadas.
- Referencias de ingreso de mercancía, aceptación de servicio o guía, con cantidades elegibles para facturar.
- Estado de factura SAP: documento y ejercicio, referencia externa, estado de aparcado/contabilizado/bloqueado, motivo de bloqueo y fechas relevantes.
- Estado de pago: documento de pago, fecha, vencimiento, importe pagado y saldo abierto, solo cuando el cliente provea una fuente SAP autorizada para esos datos.

La sincronización debe ser incremental e idempotente, conservando el identificador fuente SAP y la fecha de última actualización. La factura saliente debe usar clave de idempotencia del portal; no reintentar a ciegas un timeout porque SAP podría haber creado el documento.

## Criterios de activación

- Confirmar release ECC y BAPI exacta en el landscape del cliente.
- Probar primero en sandbox/calidad con `TESTRUN` o mecanismo de simulación disponible y sin contabilización productiva.
- Validar proveedor, pedido/posición, moneda, cantidades abiertas, impuestos, multi-pedido, recepción/servicio, redondeos y duplicados.
- Probar retorno de mensajes, commit/rollback, pérdida de conexión, reconciliación de timeout y recuperación de la bandeja de salida.
- Acordar seguridad, reintentos, auditoría, retención de adjuntos y estados que se muestran al proveedor.
- Solo después implementar el transporte y habilitar despachos reales.

## Referencias SAP

- [BAPI de ECC para retener/aparcar/contabilizar factura entrante (CREATE1; disponibilidad desde SAP_APPL 605)](https://help.sap.com/doc/8c4fa73704904b67991c1b99640945b1/6.05.16/en-US/Chapter_24__Procurement_and_Logistics_ExecutionE.PDF)
- [SAP: guardar cambios de BAPI requiere BAPI_TRANSACTION_COMMIT](https://help.sap.com/docs/SUPPORT_CONTENT/spmm/3362167428.html)
- [SAP: facturas entrantes con BAPI_INCOMINGINVOICE_CREATE](https://help.sap.com/docs/SUPPORT_CONTENT/spmm/3362167869.html)
- [SAP S/4HANA Cloud: API de factura de proveedor](https://help.sap.com/docs/SAP_S4HANA_CLOUD/bb9f1469daf04bd894ab2167f8132a1a/7bc52558ef790a02e10000000a44147b.html)
