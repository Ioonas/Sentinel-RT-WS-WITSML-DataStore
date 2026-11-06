"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { api, ApiError, type SessionView } from "@/lib/api";
import { can } from "@/lib/permissions";
import { useApiQuery } from "@/lib/hooks";
import { Button } from "./ui";
import styles from "./Shell.module.css";

type NavItem = { href: string; label: string; permission?: string };

// Cada sección exige el permiso que el backend exige para leerla. "Resumen",
// "Configuración" y "Mi cuenta" no piden ninguno: sus widgets se filtran por permiso.
const NAV: NavItem[] = [
  { href: "/admin/overview", label: "Resumen" },
  { href: "/admin/server-configuration", label: "Configuración" },
  { href: "/admin/service-accounts", label: "Cuentas de servicio", permission: "admin.identities.write" },
  { href: "/admin/admin-users", label: "Usuarios", permission: "admin.identities.write" },
  { href: "/admin/access", label: "Roles y acceso", permission: "admin.roles.read" },
  { href: "/admin/objects", label: "Objetos WITSML", permission: "admin.objects.read" },
  { href: "/admin/audit", label: "Auditoría", permission: "admin.audit.read" },
  { href: "/admin/profile", label: "Mi cuenta" },
];

/** Secciones que ve una persona con acceso web vinculado: solo lectura de objetos. */
const LINKED_NAV_HREFS = new Set(["/admin/objects", "/admin/profile"]);

function allowedNav(session: SessionView | null | undefined): NavItem[] {
  if (!session) return [];
  const linked = Boolean(session.linked_service_account);
  return NAV.filter(
    (item) =>
      (!linked || LINKED_NAV_HREFS.has(item.href)) &&
      (item.permission === undefined || can(session, item.permission)),
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const profile = useApiQuery<SessionView>("/profile");
  const items = allowedNav(profile.data);
  const allowedHrefs = new Set(items.map((item) => item.href));

  useEffect(() => {
    // Una ruta que la sesión no puede ver (incluida una escrita a mano en la URL) se lleva
    // a la primera sección permitida. El backend también rechaza la petición.
    if (!profile.data) return;
    const isSection = NAV.some((item) => item.href === pathname);
    if (isSection && !allowedHrefs.has(pathname)) {
      router.replace(items[0]?.href ?? "/admin/profile");
    }
  }, [profile.data, pathname, router]);

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
