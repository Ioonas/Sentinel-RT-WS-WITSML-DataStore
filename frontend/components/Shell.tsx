"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { api, ApiError, type SessionView } from "@/lib/api";
import { useApiQuery } from "@/lib/hooks";
import { Button } from "./ui";
import styles from "./Shell.module.css";

const NAV = [
  { href: "/admin/overview", label: "Resumen" },
  { href: "/admin/server-configuration", label: "Configuración" },
  { href: "/admin/service-accounts", label: "Cuentas de servicio" },
  { href: "/admin/admin-users", label: "Usuarios" },
  { href: "/admin/access", label: "Roles y acceso" },
  { href: "/admin/objects", label: "Objetos WITSML" },
  { href: "/admin/audit", label: "Auditoría" },
  { href: "/admin/profile", label: "Mi cuenta" },
];

/** Secciones que ve una persona con acceso web vinculado: solo lectura de objetos. */
const LINKED_NAV_HREFS = new Set(["/admin/objects", "/admin/profile"]);

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const profile = useApiQuery<SessionView>("/profile");
  const linked = Boolean(profile.data?.linked_service_account);
  const items = linked ? NAV.filter((item) => LINKED_NAV_HREFS.has(item.href)) : NAV;

  useEffect(() => {
    // Una persona vinculada solo accede a sus objetos y a su cuenta; cualquier otra ruta
    // (incluida una escrita a mano en la URL) se lleva a Objetos.
    if (linked && !LINKED_NAV_HREFS.has(pathname)) {
      router.replace("/admin/objects");
    }
  }, [linked, pathname, router]);

  async function logout() {
    try {
      await api("/auth/sessions", { method: "DELETE" });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    } finally {
      router.push("/admin/login");
      router.refresh();
    }
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <Link href="/admin/overview" className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <span>
            <strong>Sentinel</strong>
            <small>RT&amp;WS WITSML DataStore</small>
          </span>
        </Link>
        <nav aria-label="Administración" className={styles.nav}>
          {items.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={[styles.navItem, active ? styles.active : ""].join(" ")}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className={styles.footer}>
          <span className={styles.version}>v1.0.3 · WITSML 1.4.1.1</span>
          <Button variant="ghost" size="sm" onClick={logout}>
            Cerrar sesión
          </Button>
        </div>
      </aside>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
