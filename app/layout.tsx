import type { Metadata } from "next";
import "./globals.css";
import styles from "./portal.module.css";

export const metadata: Metadata = {
  title: "Portal de Proveedores",
  description: "Portal para órdenes de compra, registro de facturas y seguimiento de pagos.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className={`${styles.portal} min-h-full flex flex-col`}>{children}</body>
    </html>
  );
}
