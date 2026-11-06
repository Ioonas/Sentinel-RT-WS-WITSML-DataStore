"use client";

import Link from "next/link";
import { Alert, Card, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import { Section, Stat } from "@/components/dashboard";
import {
  type DependencyHealth,
  type MessageView,
  type ServerConfigView,
  type SessionView,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

const QUICK_LINKS = [
  { href: "/admin/server-configuration", label: "Configuración del servidor", hint: "Contacto y límites" },
  { href: "/admin/service-accounts", label: "Cuentas de servicio", hint: "Credenciales WMLS" },
  { href: "/admin/admin-users", label: "Usuarios administrativos", hint: "Invitaciones y roles" },
  { href: "/admin/access", label: "Roles y acceso", hint: "Permisos efectivos" },
  { href: "/admin/objects", label: "Objetos WITSML", hint: "Inventario y borrado" },
  { href: "/admin/audit", label: "Auditoría", hint: "Trazabilidad" },
];

function healthTone(status: string | undefined): "ok" | "warn" | "danger" | "neutral" {
  if (!status) return "neutral";
  if (status === "ok" || status === "ready" || status === "healthy") return "ok";
  if (status === "degraded") return "warn";
  if (status === "error" || status === "not_ready" || status === "unavailable") return "danger";
  return "neutral";
}

export default function OverviewPage() {
  const profile = useApiQuery<SessionView>("/profile");
  const config = useApiQuery<ServerConfigView>("/server-config");
  // Salud y cola de correo exigen admin.health.read; sin él no se piden ni se muestran.
  const canHealth = can(profile.data, "admin.health.read");
  const health = useApiQuery<DependencyHealth>(canHealth ? "/health/dependencies" : null);
  const outbox = useApiQuery<MessageView>(canHealth ? "/mail-outbox/pending" : null);

  const user = profile.data?.user;

  return (
    <div className={styles.stack}>
      <PageHeader
        title={user ? `Hola, ${user.display_name}` : "Resumen"}
        description="Estado operativo, configuración pública y accesos rápidos del DataStore."
        actions={
          canHealth ? (
            <StatusBadge
              status={healthTone(health.data?.status)}
              label={health.data?.status ?? (health.error ? "sin permiso" : "consultando")}
            />
          ) : undefined
        }
      />

      {config.error ? <Alert>{config.error.message}</Alert> : null}

      <div className={styles.grid}>
        <Card>
          <Stat
            label="Producto"
            value={config.data?.product_name ?? "—"}
            hint={`v${config.data?.version ?? "—"} · WITSML ${config.data?.schema_version ?? "—"}`}
          />
        </Card>
        <Card>
          <Stat
            label="API WMLS"
            value={config.data?.api_version ?? "—"}
            hint={config.data?.cascaded_delete ? "Borrado en cascada activo" : "Sin borrado en cascada"}
          />
        </Card>
        <Card>
          <Stat
            label="Configuración inicial"
            value={config.data ? (config.data.setup_completed ? "Completada" : "Pendiente") : "—"}
            hint={config.data?.updated_at ? `Actualizada ${formatDateTime(config.data.updated_at)}` : undefined}
          />
        </Card>
        {canHealth ? (
          <Card>
            <Stat
              label="Correo pendiente"
              value={outbox.data?.message ?? "—"}
              hint="Cola de invitaciones y recuperación"
            />
          </Card>
        ) : null}
      </div>

      <div className={styles.split}>
        {canHealth ? (
        <Card>
          <Section
            title="Estado de dependencias"
            description="Comprobaciones internas de base de datos, correo y almacenamiento."
            actions={
              health.loading ? (
                <Spinner />
              ) : (
                <StatusBadge status={healthTone(health.data?.status)} label={health.data?.status ?? "—"} />
              )
            }
          >
            {health.error ? (
              <Alert tone="warn">{health.error.message}</Alert>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Dependencia</th>
                      <th>Estado</th>
                      <th>Detalle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.data && Object.keys(health.data.dependencies).length > 0 ? (
                      Object.entries(health.data.dependencies).map(([name, detail]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>
                            <StatusBadge
                              status={healthTone(String(detail.status ?? ""))}
                              label={String(detail.status ?? "—")}
                            />
                          </td>
                          <td className={styles.wrap}>
                            <code>{JSON.stringify(detail)}</code>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={3} className={styles.muted}>
                          {health.loading ? "Consultando…" : "Sin datos de dependencias."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </Card>
        ) : null}

        <Card>
          <Section title="Contacto público" description="Datos expuestos en GetCap.">
            {config.data ? (
              <dl className={styles.detailsGrid}>
                <dt>Contacto</dt>
                <dd>{config.data.contact_name || "—"}</dd>
                <dt>Correo</dt>
                <dd>{config.data.contact_email || "—"}</dd>
                <dt>Teléfono</dt>
                <dd>{config.data.contact_phone || "—"}</dd>
                <dt>Descripción</dt>
                <dd>{config.data.description || "—"}</dd>
              </dl>
            ) : (
              <p className={styles.muted}>{config.loading ? "Consultando…" : "No disponible."}</p>
            )}
            <div className={styles.quickLinks} style={{ marginTop: "var(--space-4)" }}>
              <Link className={styles.quickLink} href="/admin/server-configuration">
                <span>Editar contacto</span>
                <span>→</span>
              </Link>
            </div>
          </Section>
        </Card>
      </div>

      <Card>
        <Section title="Accesos rápidos">
          <div className={styles.quickLinks}>
            {QUICK_LINKS.map((item) => (
              <Link key={item.href} className={styles.quickLink} href={item.href}>
                <span>{item.label}</span>
                <span>{item.hint}</span>
              </Link>
            ))}
          </div>
        </Section>
      </Card>
    </div>
  );
}
