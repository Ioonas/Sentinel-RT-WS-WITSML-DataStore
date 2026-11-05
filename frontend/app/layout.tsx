import type { Metadata } from "next";
import type { ReactNode } from "react";
// Fuentes autohospedadas: la interfaz no contacta CDN externos (ui-spec §12, criterio 30).
import "@fontsource-variable/roboto-flex";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sentinel RT&WS WITSML DataStore",
  description:
    "Administración de Sentinel RT&WS WITSML DataStore (WITSML 1.4.1.1).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
