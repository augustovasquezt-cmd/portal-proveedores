# Contrato de integración SAP: comprobantes de retención

## Alcance

El ERP calcula, numera, emite y conserva el CRE como sistema de registro. Este servicio recibe una copia del XML firmado, la representación PDF y el CDR de SUNAT; guarda los metadatos para consulta y ofrece los archivos al proveedor autenticado. El portal no genera certificados ni determina el importe retenido.

La API está lista para la parte del portal. El consultor ABAP debe implementar el envío desde el proceso de emisión del CRE y confirmar en cada landscape ECC, S/4HANA o GROW cómo obtener el XML/PDF/CDR y el estado final de SUNAT. El token de integración se configura de forma segura en el backend y en el destino técnico SAP; nunca se expone en el navegador.

## Configuración del backend

La cuenta superadministradora de IVS genera o rota una credencial individual por cliente desde el panel de IVS. El backend almacena solo su hash; la clave en claro se muestra una sola vez y se entrega al responsable técnico del cliente para cargarla en el almacén seguro del destino SAP. Cada llamada identifica al cliente por la credencial, y el backend valida el RUC emisor contra las sociedades habilitadas para ese cliente y la asignación del proveedor. No se configura una lista global de RUC en variables de entorno ni se acepta el `cliente_id` del payload como selector.

Usa HTTPS en cualquier ambiente compartido o productivo, restringe la conectividad entrante al origen SAP, almacena el token en un repositorio seguro y define rotación. En SAP, configura el usuario técnico y el secreto en el mecanismo seguro aprobado para el release; no los grabes en código ABAP.

Al iniciar, `Base.metadata.create_all()` crea la tabla `certificados_retencion` si no existe. No altera las tablas de facturas existentes.

## Recibir un CRE

`POST /integracion-sap/retenciones` usa `multipart/form-data` con:

| Campo | Obligatorio | Contenido |
| --- | --- | --- |
| `certificado` | Sí | JSON con los metadatos de abajo |
| `xml` | Sí | XML UBL `Retention` emitido por SUNAT, máximo 5 MB |
| `pdf` | Sí | PDF entregado al proveedor, máximo 5 MB |
| `cdr` | No al inicio | CDR UBL `ApplicationResponse`, máximo 5 MB; se requiere para publicar como aceptado |

Autenticación: `Authorization: Bearer <credencial SAP asignada por IVS a ese cliente>`.

Ejemplo de metadatos (`certificado`):

```json
{
  "evento_origen": "ECC-1000-2026-R001-00000001-ISSUED",
  "ruc_emisor": "20123456789",
  "ruc_proveedor": "20999999999",
  "sociedad": "1000",
  "serie": "R001",
  "correlativo": "1",
  "fecha_emision": "2026-09-29",
  "moneda": "PEN",
  "base_retencion": 10000.00,
  "tasa_retencion": 3.00,
  "importe_retencion": 300.00,
  "fecha_pago": "2026-09-29",
  "referencia_pago": "PAGO-2026-000123",
  "documento_sap": "1900001234",
  "ejercicio_sap": "2026",
  "estado_sunat": "aceptado",
  "motivo_estado": null,
  "facturas_relacionadas": [
    {
      "tipo": "01",
      "serie": "F001",
      "numero": "1234",
      "fecha_emision": "2026-09-15",
      "importe": 10000.00,
      "moneda": "PEN"
    }
  ]
}
```

La serie debe tener cuatro caracteres y comenzar por `R`. El correlativo puede llegar con ceros a la izquierda; el portal normaliza ese número para evitar duplicados por diferencias de formato. El RUC proveedor debe corresponder a un proveedor activo en el portal. El RUC emisor debe estar autorizado. El backend valida el tipo de XML, los RUC de agente/receptor, serie y correlativo cuando están presentes, la cabecera PDF, el tipo UBL del CDR y los tamaños.

`evento_origen` debe ser estable entre reintentos de la misma emisión. La combinación cliente + RUC emisor + serie + correlativo es única. Repetir el mismo evento con los mismos hashes devuelve `ya_recibido`; el mismo ID con archivos distintos o el mismo certificado con otro evento devuelve `409`. Una corrección que SUNAT numere como nuevo certificado se envía como un nuevo número y evento, manteniendo el documento anterior para auditoría.

Si el ERP publica el CRE antes de recibir la respuesta de SUNAT, envíalo con `estado_sunat: "pendiente"`, XML y PDF. Después:

1. Adjunta el CDR con `POST /integracion-sap/retenciones/cdr` (`multipart`: `ruc_emisor`, `serie`, `correlativo`, `cdr`).
2. Actualiza el estado con `PATCH /integracion-sap/retenciones/estado` y JSON `{"ruc_emisor":"20123456789","serie":"R001","correlativo":"1","estado_sunat":"aceptado","motivo_estado":null}`.

También se aceptan `rechazado` y `anulado`. El portal conserva el registro y deshabilita descargas del CRE como documento válido si su estado no es `aceptado`. Para pasar a aceptado tiene que haberse recibido el CDR. ABAP solo debe informar `aceptado` después de interpretar el resultado del CDR.

## Consulta del proveedor

El portal autentica al proveedor con su sesión normal; el RUC se obtiene del token y no se acepta como filtro libre. Las llamadas deben llevar `Authorization: Bearer <access_token>` del proveedor:

- `GET /retenciones?desde=2026-01-01&hasta=2026-12-31&estado=aceptado&sociedad=20123456789&limit=50&offset=0`
- `GET /retenciones/{id}/archivos/pdf`
- `GET /retenciones/{id}/archivos/xml`
- `GET /retenciones/{id}/archivos/cdr`

Los filtros de fecha, estado, sociedad y paginación son opcionales. La API de archivos valida el RUC, el cliente seleccionado, la membresía activa del proveedor y la asignación a la sociedad emisora; solo sirve documentos aceptados, y envía `Cache-Control: private, no-store` y `X-Content-Type-Options: nosniff`. No se publican enlaces permanentes ni se exponen las columnas binarias en la lista.

La respuesta de listado es `{ "items": [...], "total": 1, "limit": 50, "offset": 0 }`. Cada elemento incluye los datos del CRE, las facturas relacionadas, los estados, disponibilidad de archivos y hashes SHA-256.

## Ejemplo de envío desde PowerShell

Para una prueba local, genera la credencial desde el panel IVS del cliente de prueba y guárdala temporalmente en PowerShell. Usa los archivos y XML/CDR del entorno de calidad, nunca documentos productivos:

```powershell
$headers = @{ Authorization = "Bearer $env:CLIENTE_SAP_API_TOKEN" }
$metadata = Get-Content .\cre-metadata.json -Raw
$form = @{
  certificado = $metadata
  xml = Get-Item .\R001-1.xml
  pdf = Get-Item .\R001-1.pdf
  cdr = Get-Item .\R001-1-CDR.xml
}
Invoke-RestMethod -Method Post -Uri http://localhost:8000/integracion-sap/retenciones -Headers $headers -Form $form
```

En producción cambia `http://localhost:8000` por el HTTPS del portal. Los archivos deben ser UBL CRE/CDR de prueba válidos; la prueba no crea ni modifica un documento SAP.

## Lista para el consultor ABAP

1. Identificar el evento/proceso donde el CRE ya tiene serie, correlativo y XML final; no publicar borradores.
2. Extraer el XML firmado que SUNAT recibió, el PDF entregable y el CDR/resultado de aceptación. No regenerar el XML en el portal.
3. Mapear sociedad/RUC emisor, proveedor/RUC, base, tasa, retención, pago y facturas relacionadas desde los datos oficiales del proceso SAP.
4. Generar un `evento_origen` estable y reintentar con el mismo valor hasta recibir respuesta HTTP satisfactoria. No crear otro certificado como reacción automática a un timeout.
5. Configurar HTTPS, destino, autenticación y secretos conforme a ECC, S/4HANA on-prem/private o GROW. Sin middleware, un job ABAP puede llamar directamente al endpoint solo si el landscape permite salida HTTPS; si no, acordar SFTP controlado u otra interfaz aprobada por SAP/Basis.
6. Implementar reintentos con backoff para errores temporales (`429`/`5xx`), registro de respuesta y cola de fallos; tratar `400`, `401`, `403`, `409` y `422` como errores que requieren revisión/configuración.
7. Probar proveedor inexistente, sociedad no autorizada, CRE aceptado/rechazado/anulado, respuesta tardía de CDR, duplicados y archivos sobre el límite en calidad.

Las credenciales y sociedades están separadas por cliente. Antes de producción, ejecutar la migración de esquema respaldada y versionada para el motor configurado y trasladar adjuntos a almacenamiento de objetos privado si el volumen o la política de retención lo requiere. El portal conserva hashes y mantiene la interfaz SAP desacoplada del ERP.
