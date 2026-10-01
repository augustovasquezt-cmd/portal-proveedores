This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Backend local (Windows)

Usa Python 3.12 para el backend. En PowerShell, desde la raíz del proyecto:

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload --port 8000
```

Para ejecutar las pruebas desde la raíz del proyecto, copia este bloque:

```powershell
Push-Location .\backend
.\.venv\Scripts\python.exe -m unittest test_cuentas_por_pagar test_posiciones test_documentos_base test_sap_ecc_contrato test_facturas_registro test_multipedido test_ordenes test_pedidos_completos test_validacion_sap
Pop-Location
```

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Perfil de cuentas por pagar (demo)

El perfil interno inicia sesión con usuario corporativo desde la pantalla principal, en vez de usar el RUC del proveedor. Para crear una cuenta demo, define una contraseña local segura de al menos 12 caracteres y ejecuta desde `backend`:

```powershell
$env:AP_USER = 'ap@demo.local'
$env:AP_NAME = 'Analista de cuentas por pagar'
$env:AP_PASSWORD = 'Reemplaza-por-una-clave-local-segura'
.\.venv\Scripts\python.exe .\seed_cuentas_por_pagar.py
```

Luego inicia sesión en `http://localhost:3000` con el perfil **Cuentas por pagar**. El menú incluye Inicio, Mis comprobantes, Datos maestros, Mis datos y Mis solicitudes. La bandeja muestra las facturas preregistradas por proveedores; permite recibirlas, aceptarlas, rechazarlas con motivo, programar fecha de pago y registrar el pago. Las acciones quedan en el historial. Este flujo de demostración todavía no contabiliza ni crea documentos en SAP.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
