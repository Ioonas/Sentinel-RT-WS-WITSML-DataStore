"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, Input, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import { Section, Stat } from "@/components/dashboard";
import {
  ApiError,
  api,
  type ServerConfigView,
  type ServiceStatusView,
  type SessionView,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

// Cada área de configuración tiene su propia sección navegable (ancla en la URL).
const SECTIONS = [
  { id: "general", label: "General" },
  { id: "witsml", label: "API WITSML" },
  { id: "admin-api", label: "API administrativa" },
  { id: "correo", label: "API de correo" },
  { id: "servicios", label: "Servicios" },
] as const;

type Feedback = { tone: "ok" | "error"; text: string } | null;

type ServiceName = "witsml" | "admin" | "mail-worker";

const SERVICE_LABELS: Record<string, string> = {
  witsml: "la API WITSML",
  admin: "la API administrativa",
  "mail-worker": "el worker de correo",
};

const STATE_LABELS: Record<string, string> = {
  running: "En ejecución",
  draining: "Terminando operaciones",
  restarting: "Reiniciando",
  stopped: "Detenido",
};

function ServiceRow({
  service,
  canEdit,
  busy,
  onRestart,
}: {
  service: ServiceStatusView;
  canEdit: boolean;
  busy: boolean;
  onRestart: (name: ServiceName) => void;
}) {
  const unreachable = service.stale;
  const stateLabel = unreachable ? "Sin respuesta" : (STATE_LABELS[service.state] ?? service.state);
  const pending = service.requested_generation > 0 && service.state === "draining";
  return (
    <Card>
      <Section title={SERVICE_LABELS[service.name] ?? service.name}>
        <dl className={styles.detailsGrid}>
          <dt>Estado</dt>
          <dd>{stateLabel}</dd>
          <dt>Operaciones en curso</dt>
          <dd>{service.in_flight}</dd>
          <dt>Proceso (PID)</dt>
          <dd>{service.pid ?? "—"}</dd>
          <dt>Último latido</dt>
          <dd>{formatDateTime(service.heartbeat_at)}</dd>
          <dt>Último reinicio solicitado</dt>
          <dd>
            {service.requested_at
              ? `${formatDateTime(service.requested_at)} por ${service.requested_by ?? "—"}`
              : "—"}
          </dd>
          {service.last_error ? (
            <>
              <dt>Último aviso</dt>
              <dd>{service.last_error}</dd>
            </>
          ) : null}
        </dl>
        {pending ? (
          <p className={styles.faint}>Esperando a que terminen las operaciones en curso.</p>
        ) : null}
        <div className={styles.actions}>
          <Button
            variant="danger"
            disabled={!canEdit || busy || unreachable}
            onClick={() => onRestart(service.name as ServiceName)}
          >
            {busy ? "Solicitando…" : "Reiniciar"}
          </Button>
        </div>
      </Section>
    </Card>
  );
}


function Notice({ feedback }: { feedback: Feedback }) {
  if (!feedback) return null;
  return feedback.tone === "ok" ? <Alert tone="ok">{feedback.text}</Alert> : <Alert>{feedback.text}</Alert>;
}

function errorText(caught: unknown, fallback: string) {
  return caught instanceof ApiError ? caught.message : fallback;
}

export default function ServerConfigurationPage() {
  const { data, error, loading, reload } = useApiQuery<ServerConfigView>("/server-config");
  const session = useApiQuery<SessionView>("/profile");
  // Solo el superadministrador cambia la configuración; el resto ve los valores.
  const canEdit = Boolean(session.data?.is_superadmin);

  // General: contacto público.
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [contactBusy, setContactBusy] = useState(false);
  const [contactFeedback, setContactFeedback] = useState<Feedback>(null);

  // WITSML: identidad y límites operativos.
  const [serviceName, setServiceName] = useState("");
  const [serviceDescription, setServiceDescription] = useState("");
  const [serviceBusy, setServiceBusy] = useState(false);
  const [serviceFeedback, setServiceFeedback] = useState<Feedback>(null);
  const [limits, setLimits] = useState({ nodes: "", points: "", growing: "", change: "", latest: "" });
  const [limitsBusy, setLimitsBusy] = useState(false);
  const [limitsFeedback, setLimitsFeedback] = useState<Feedback>(null);

  // Correo: remitente y reintentos.
  const [mailFrom, setMailFrom] = useState("");
  const [mailAttempts, setMailAttempts] = useState("");
  const [mailBackoff, setMailBackoff] = useState("");
  const [mailBusy, setMailBusy] = useState(false);
  const [mailFeedback, setMailFeedback] = useState<Feedback>(null);

  // Servicios: estado de cada proceso y reinicio independiente.
  const services = useApiQuery<ServiceStatusView[]>("/server-config/services");
  const [restartBusy, setRestartBusy] = useState<string | null>(null);
  const [restartFeedback, setRestartFeedback] = useState<Feedback>(null);

  useEffect(() => {
    if (!data) return;
    setEmail(data.contact_email);
    setPhone(data.contact_phone);
    setServiceName(data.contact_name);
    setServiceDescription(data.description);
    setLimits({
      nodes: String(data.max_data_nodes),
      points: String(data.max_data_points),
      growing: String(data.growing_timeout_seconds),
      change: String(data.change_detection_seconds),
      latest: String(data.max_request_latest_values),
    });
    setMailFrom(data.mail_from);
    setMailAttempts(String(data.mail_max_attempts));
    setMailBackoff(String(data.mail_backoff_base_seconds));
  }, [data]);

  async function submitContact(event: FormEvent) {
    event.preventDefault();
    setContactBusy(true);
    setContactFeedback(null);
    try {
      await api<ServerConfigView>("/server-config/contact", {
        method: "PUT",
        body: JSON.stringify({ contact_email: email, contact_phone: phone }),
      });
      setContactFeedback({ tone: "ok", text: "Contacto público actualizado. GetCap reflejará el cambio." });
      reload();
    } catch (caught) {
      setContactFeedback({ tone: "error", text: errorText(caught, "No se pudo guardar el contacto.") });
    } finally {
      setContactBusy(false);
    }
  }

  async function submitServiceInfo(event: FormEvent) {
    event.preventDefault();
    setServiceBusy(true);
    setServiceFeedback(null);
    try {
      await api<ServerConfigView>("/server-config/service-info", {
        method: "PUT",
        body: JSON.stringify({ name: serviceName, description: serviceDescription }),
      });
      setServiceFeedback({ tone: "ok", text: "Nombre y descripción actualizados. GetCap reflejará el cambio." });
      reload();
    } catch (caught) {
      setServiceFeedback({ tone: "error", text: errorText(caught, "No se pudo guardar la identidad.") });
    } finally {
      setServiceBusy(false);
    }
  }

  async function submitLimits(event: FormEvent) {
    event.preventDefault();
    setLimitsBusy(true);
    setLimitsFeedback(null);
    try {
      await api<ServerConfigView>("/server-config/limits", {
        method: "PUT",
        body: JSON.stringify({
          max_data_nodes: Number(limits.nodes),
          max_data_points: Number(limits.points),
          growing_timeout_seconds: Number(limits.growing),
          change_detection_seconds: Number(limits.change),
          max_request_latest_values: Number(limits.latest),
        }),
      });
      setLimitsFeedback({ tone: "ok", text: "Límites operativos actualizados. Aplican a las siguientes solicitudes." });
      reload();
    } catch (caught) {
      setLimitsFeedback({ tone: "error", text: errorText(caught, "No se pudieron guardar los límites.") });
    } finally {
      setLimitsBusy(false);
    }
  }

  async function submitMail(event: FormEvent) {
    event.preventDefault();
    setMailBusy(true);
    setMailFeedback(null);
    try {
      await api<ServerConfigView>("/server-config/mail", {
        method: "PUT",
        body: JSON.stringify({
          mail_from: mailFrom.trim(),
          mail_max_attempts: Number(mailAttempts),
          mail_backoff_base_seconds: Number(mailBackoff),
        }),
      });
      setMailFeedback({ tone: "ok", text: "Configuración de correo actualizada. El worker la usa desde el siguiente envío." });
      reload();
    } catch (caught) {
      setMailFeedback({ tone: "error", text: errorText(caught, "No se pudo guardar la configuración de correo.") });
    } finally {
      setMailBusy(false);
    }
  }

  async function requestRestart(service: ServiceName | "all") {
    const label = SERVICE_LABELS[service] ?? "todos los servicios";
    const confirmed = window.confirm(
      `Se reiniciará ${label}. Cada proceso termina sus operaciones en curso antes de salir ` +
        "(hasta 5 minutos); si no terminan, el reinicio se cancela. ¿Continuar?",
    );
    if (!confirmed) return;
    setRestartBusy(service);
    setRestartFeedback(null);
    try {
      await api<ServiceStatusView[]>("/server-config/restart", {
        method: "POST",
        body: JSON.stringify({ service }),
      });
      setRestartFeedback({
        tone: "ok",
        text: `Reinicio solicitado para ${label}. Esperando a que terminen sus operaciones en curso.`,
      });
      services.reload();
    } catch (caught) {
      setRestartFeedback({ tone: "error", text: errorText(caught, "No se pudo solicitar el reinicio.") });
    } finally {
      setRestartBusy(null);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Configuración del servidor"
        description="Configuración por servicio: general, API WITSML, API administrativa, correo y reinicio."
        actions={
          <StatusBadge
            status={data?.setup_completed ? "ok" : "warn"}
            label={data?.setup_completed ? "Configurado" : "Primer arranque pendiente"}
          />
        }
      />

      <nav aria-label="Secciones de configuración" className={styles.faint}>
        <ul style={{ display: "flex", flexWrap: "wrap", gap: "1rem", listStyle: "none", padding: 0, margin: 0 }}>
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a href={`#${section.id}`}>{section.label}</a>
            </li>
          ))}
        </ul>
      </nav>

      {error ? <Alert>{error.message}</Alert> : null}
      {loading ? <Spinner /> : null}

      {data ? (
        <>
          <section id="general" aria-labelledby="general-title" className={styles.stack}>
            <h2 id="general-title">General</h2>
            <div className={styles.grid}>
              <Card>
                <Stat label="Producto" value={data.product_name} hint={`Versión ${data.version}`} />
              </Card>
              <Card>
                <Stat label="Esquema WITSML" value={data.schema_version} />
              </Card>
              <Card>
                <Stat
                  label="Borrado en cascada"
                  value={data.cascaded_delete ? "Publicado" : "No publicado"}
                  hint="Cada cuenta de servicio necesita su propio permiso"
                />
              </Card>
              <Card>
                <Stat
                  label="Conversión de unidades"
                  value={data.support_uom_conversion ? "Soportada" : "No soportada"}
                />
              </Card>
            </div>

            <div className={styles.split}>
              <Card>
                <Section title="Contacto público" description="Correo y teléfono que aparecen en GetCap.">
                  <Notice feedback={contactFeedback} />
                  <form className={styles.form} onSubmit={submitContact}>
                    <fieldset className={styles.plain} disabled={!canEdit || contactBusy}>
                      <div className={styles.formRow}>
                        <Field label="Correo de contacto" htmlFor="contact-email">
                          <Input id="contact-email" type="email" required value={email}
                            onChange={(event) => setEmail(event.target.value)} />
                        </Field>
                        <Field label="Teléfono de contacto" htmlFor="contact-phone">
                          <Input id="contact-phone" required minLength={6} maxLength={32} value={phone}
                            onChange={(event) => setPhone(event.target.value)} />
                        </Field>
                      </div>
                      <div className={styles.actions}>
                        <Button type="submit" variant="primary" disabled={contactBusy}>
                          {contactBusy ? "Guardando…" : "Guardar contacto"}
                        </Button>
                      </div>
                    </fieldset>
                  </form>
                </Section>
              </Card>

              <Card>
                <Section title="Detalle">
                  <dl className={styles.detailsGrid}>
                    <dt>Nombre del servicio</dt>
                    <dd>{data.contact_name || "—"}</dd>
                    <dt>Descripción</dt>
                    <dd>{data.description || "—"}</dd>
                    <dt>Proveedor</dt>
                    <dd>{data.vendor}</dd>
                    <dt>Actualizado</dt>
                    <dd>{formatDateTime(data.updated_at)}</dd>
                    <dt>Actualizado por</dt>
                    <dd>{data.updated_by || "—"}</dd>
                  </dl>
                </Section>
              </Card>
            </div>
          </section>

          <section id="witsml" aria-labelledby="witsml-title" className={styles.stack}>
            <h2 id="witsml-title">API WITSML</h2>
            <Card>
              <Section
                title="Identidad del servicio"
                description="Nombre y descripción publicados en GetCap. Solo superadministrador; cada cambio queda auditado."
              >
                <Notice feedback={serviceFeedback} />
                <form className={styles.form} onSubmit={submitServiceInfo}>
                  <fieldset className={styles.plain} disabled={!canEdit || serviceBusy}>
                    <Field label="Nombre del servicio" htmlFor="service-name" hint="Entre 3 y 255 caracteres.">
                      <Input id="service-name" required minLength={3} maxLength={255} value={serviceName}
                        onChange={(event) => setServiceName(event.target.value)} />
                    </Field>
                    <Field label="Descripción" htmlFor="service-description" hint="Hasta 512 caracteres.">
                      <Input id="service-description" required maxLength={512} value={serviceDescription}
                        onChange={(event) => setServiceDescription(event.target.value)} />
                    </Field>
                    <div className={styles.actions}>
                      <Button type="submit" variant="primary" disabled={serviceBusy}>
                        {serviceBusy ? "Guardando…" : "Guardar identidad"}
                      </Button>
                    </div>
                  </fieldset>
                </form>
              </Section>
            </Card>

            <Card>
              <Section
                title="Límites operativos"
                description={
                  canEdit
                    ? "Valores aplicados a solicitudes WMLS y detección de cambios. Cada cambio queda auditado."
                    : "Valores efectivos aplicados a solicitudes WMLS y detección de cambios."
                }
              >
                {canEdit ? (
                  <form onSubmit={submitLimits}>
                    <fieldset className={styles.plain} disabled={limitsBusy}>
                      <div className={styles.grid}>
                        <Field label="Máx. nodos de datos" htmlFor="limit-nodes" hint="maxDataNodes en GetCap y en solicitudes.">
                          <Input id="limit-nodes" type="number" min={1} max={2147483647} required value={limits.nodes}
                            onChange={(event) => setLimits({ ...limits, nodes: event.target.value })} />
                        </Field>
                        <Field label="Máx. puntos de datos" htmlFor="limit-points" hint="maxDataPoints en GetCap y en solicitudes.">
                          <Input id="limit-points" type="number" min={1} max={2147483647} required value={limits.points}
                            onChange={(event) => setLimits({ ...limits, points: event.target.value })} />
                        </Field>
                        <Field label="Timeout growing (s)" htmlFor="limit-growing" hint="Tiempo sin datos para dar por cerrado un log creciente.">
                          <Input id="limit-growing" type="number" min={1} max={2147483647} required value={limits.growing}
                            onChange={(event) => setLimits({ ...limits, growing: event.target.value })} />
                        </Field>
                        <Field label="Detección de cambios (s)" htmlFor="limit-change" hint="Intervalo de detección de cambios.">
                          <Input id="limit-change" type="number" min={1} max={2147483647} required value={limits.change}
                            onChange={(event) => setLimits({ ...limits, change: event.target.value })} />
                        </Field>
                        <Field label="Máx. latest values" htmlFor="limit-latest" hint="Valores más recientes por solicitud.">
                          <Input id="limit-latest" type="number" min={1} max={2147483647} required value={limits.latest}
                            onChange={(event) => setLimits({ ...limits, latest: event.target.value })} />
                        </Field>
                      </div>
                      <Notice feedback={limitsFeedback} />
                      <div className={styles.actions}>
                        <Button type="submit" variant="primary" disabled={limitsBusy}>
                          {limitsBusy ? "Guardando…" : "Guardar límites"}
                        </Button>
                      </div>
                    </fieldset>
                  </form>
                ) : (
                  <div className={styles.grid}>
                    <Stat label="Máx. nodos de datos" value={data.max_data_nodes.toLocaleString("es")} />
                    <Stat label="Máx. puntos de datos" value={data.max_data_points.toLocaleString("es")} />
                    <Stat label="Timeout growing" value={`${data.growing_timeout_seconds} s`} />
                    <Stat label="Detección de cambios" value={`${data.change_detection_seconds} s`} />
                    <Stat label="Máx. latest values" value={data.max_request_latest_values.toLocaleString("es")} />
                  </div>
                )}
              </Section>
            </Card>
          </section>

          <section id="admin-api" aria-labelledby="admin-api-title" className={styles.stack}>
            <h2 id="admin-api-title">API administrativa</h2>
            <div className={styles.grid}>
              <Card>
                <Stat label="Versión de API" value={data.api_version} hint="Versión de la API administrativa" />
              </Card>
              <Card>
                <Stat label="Ruta base" value="/admin-api/v1" hint="Consumida por este panel" />
              </Card>
              <Card>
                <Stat label="Cookies de sesión" value="sentinel_session" hint="Protegidas con token CSRF (sentinel_csrf)" />
              </Card>
            </div>
            <Card>
              <Section
                title="Seguridad de acceso"
                description="Las cuentas que fallan el inicio de sesión varias veces se bloquean temporalmente."
              >
                <p className={styles.faint}>
                  El bloqueo y la sesión de cada cuenta se administran desde Accesos y Cuentas de servicio.
                </p>
              </Section>
            </Card>
          </section>

          <section id="correo" aria-labelledby="correo-title" className={styles.stack}>
            <h2 id="correo-title">API de correo</h2>
            <Card>
              <Section
                title="Remitente y reintentos"
                description="Controla desde qué dirección salen los correos y cuántas veces se reintenta un envío fallido. Credenciales, servidor y puerto SMTP siguen siendo de entorno y no se muestran."
              >
                <Notice feedback={mailFeedback} />
                <form className={styles.form} onSubmit={submitMail}>
                  <fieldset className={styles.plain} disabled={!canEdit || mailBusy}>
                    <div className={styles.formRow}>
                      <Field
                        label="Remitente"
                        htmlFor="mail-from"
                        hint="Vacío: usa el remitente de entorno (SENTINEL_SMTP_FROM)."
                      >
                        <Input id="mail-from" type="email" maxLength={255} value={mailFrom}
                          onChange={(event) => setMailFrom(event.target.value)} />
                      </Field>
                      <Field label="Intentos máximos" htmlFor="mail-attempts" hint="Entre 1 y 50 intentos por correo.">
                        <Input id="mail-attempts" type="number" min={1} max={50} required value={mailAttempts}
                          onChange={(event) => setMailAttempts(event.target.value)} />
                      </Field>
                      <Field label="Base de reintento (s)" htmlFor="mail-backoff" hint="Espera inicial; se duplica en cada intento, hasta 1 hora.">
                        <Input id="mail-backoff" type="number" min={1} max={3600} required value={mailBackoff}
                          onChange={(event) => setMailBackoff(event.target.value)} />
                      </Field>
                    </div>
                    <div className={styles.actions}>
                      <Button type="submit" variant="primary" disabled={mailBusy}>
                        {mailBusy ? "Guardando…" : "Guardar correo"}
                      </Button>
                    </div>
                  </fieldset>
                </form>
                {!canEdit ? (
                  <p className={styles.faint}>Solo un superadministrador puede cambiar la configuración de correo.</p>
                ) : null}
              </Section>
            </Card>
          </section>

          <section id="servicios" aria-labelledby="servicios-title" className={styles.stack}>
            <h2 id="servicios-title">Servicios</h2>
            <p className={styles.faint}>
              Reinicio por servicio, para fallas críticas. Un servicio que no responde o que
              tiene operaciones en curso se muestra así; el reinicio espera a que terminen. Requiere
              un supervisor que los relance (ver deploy/supervisor).
            </p>
            <Notice feedback={restartFeedback} />
            <div className={styles.grid}>
              {(services.data ?? []).map((service) => (
                <ServiceRow
                  key={service.name}
                  service={service}
                  canEdit={canEdit}
                  busy={restartBusy === service.name || restartBusy === "all"}
                  onRestart={requestRestart}
                />
              ))}
            </div>
            {services.error ? <Alert>{services.error.message}</Alert> : null}
            <div className={styles.actions}>
              <Button
                variant="danger"
                disabled={!canEdit || restartBusy !== null}
                onClick={() => requestRestart("all")}
              >
                {restartBusy === "all" ? "Solicitando…" : "Reiniciar todos los servicios"}
              </Button>
            </div>
            <p className={styles.faint}>
              Solo superadministrador, con sesión reciente y token CSRF. Cada reinicio queda auditado.
            </p>
          </section>
        </>
      ) : null}
    </div>
  );
}
