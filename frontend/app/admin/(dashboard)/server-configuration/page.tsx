"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, Input, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import { Section, Stat } from "@/components/dashboard";
import { ApiError, api, type ServerConfigView, type SessionView } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

export default function ServerConfigurationPage() {
  const { data, error, loading, reload } = useApiQuery<ServerConfigView>("/server-config");
  const session = useApiQuery<SessionView>("/profile");
  // Solo el superadministrador cambia contacto e identidad; el resto ve los valores.
  const canEdit = Boolean(session.data?.is_superadmin);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [serviceName, setServiceName] = useState("");
  const [serviceDescription, setServiceDescription] = useState("");
  const [serviceFeedback, setServiceFeedback] = useState<string | null>(null);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [serviceBusy, setServiceBusy] = useState(false);
  const [limits, setLimits] = useState({
    nodes: "",
    points: "",
    growing: "",
    change: "",
    latest: "",
  });
  const [limitsBusy, setLimitsBusy] = useState(false);
  const [limitsFeedback, setLimitsFeedback] = useState<string | null>(null);
  const [limitsError, setLimitsError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setEmail(data.contact_email);
      setPhone(data.contact_phone);
      setServiceName(data.contact_name);
      setLimits({
        nodes: String(data.max_data_nodes),
        points: String(data.max_data_points),
        growing: String(data.growing_timeout_seconds),
        change: String(data.change_detection_seconds),
        latest: String(data.max_request_latest_values),
      });
      setServiceDescription(data.description);
    }
  }, [data]);

  async function submitServiceInfo(event: FormEvent) {
    event.preventDefault();
    setServiceBusy(true);
    setServiceError(null);
    setServiceFeedback(null);
    try {
      await api<ServerConfigView>("/server-config/service-info", {
        method: "PUT",
        body: JSON.stringify({ name: serviceName, description: serviceDescription }),
      });
      setServiceFeedback("Nombre y descripción actualizados. GetCap reflejará el cambio.");
      reload();
    } catch (caught) {
      setServiceError(caught instanceof ApiError ? caught.message : "No se pudo guardar.");
    } finally {
      setServiceBusy(false);
    }
  }

  async function submitLimits(event: FormEvent) {
    event.preventDefault();
    setLimitsBusy(true);
    setLimitsFeedback(null);
    setLimitsError(null);
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
      setLimitsFeedback("Límites operativos actualizados. Aplican a las siguientes solicitudes.");
      reload();
    } catch (caught) {
      setLimitsError(caught instanceof ApiError ? caught.message : "No se pudieron guardar los límites.");
    } finally {
      setLimitsBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setSaveError(null);
    setFeedback(null);
    try {
      await api<ServerConfigView>("/server-config/contact", {
        method: "PUT",
        body: JSON.stringify({ contact_email: email, contact_phone: phone }),
      });
      setFeedback("Contacto público actualizado. GetCap reflejará el cambio.");
      reload();
    } catch (caught) {
      setSaveError(caught instanceof ApiError ? caught.message : "No se pudo guardar el contacto.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Configuración del servidor"
        description="Datos de contacto publicados en GetCap y límites operativos del servidor."
        actions={
          <StatusBadge
            status={data?.setup_completed ? "ok" : "warn"}
            label={data?.setup_completed ? "Configurado" : "Primer arranque pendiente"}
          />
        }
      />

      {error ? <Alert>{error.message}</Alert> : null}
      {loading ? <Spinner /> : null}

      {data ? (
        <>
          <div className={styles.grid}>
            <Card>
              <Stat label="Producto" value={data.product_name} hint={`Versión ${data.version}`} />
            </Card>
            <Card>
              <Stat label="Esquema WITSML" value={data.schema_version} hint={`API ${data.api_version}`} />
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
              <Section
                title="Contacto público"
                description="Correo y teléfono que aparecen en GetCap."
              >
                {feedback ? <Alert tone="ok">{feedback}</Alert> : null}
                {saveError ? <Alert>{saveError}</Alert> : null}
                <form className={styles.form} onSubmit={submit}>
<fieldset className={styles.plain} disabled={!canEdit}>
                  <div className={styles.formRow}>
                    <Field label="Correo de contacto" htmlFor="contact-email">
                      <Input
                        id="contact-email"
                        type="email"
                        required
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                      />
                    </Field>
                    <Field label="Teléfono de contacto" htmlFor="contact-phone">
                      <Input
                        id="contact-phone"
                        required
                        minLength={6}
                        maxLength={32}
                        value={phone}
                        onChange={(event) => setPhone(event.target.value)}
                      />
                    </Field>
                  </div>
                  <div className={styles.actions}>
                    <Button type="submit" variant="primary" disabled={busy}>
                      {busy ? "Guardando…" : "Guardar contacto"}
                    </Button>
                  </div>
                  <p className={styles.faint}>
                    Solo un superadministrador puede modificar el contacto. Cada cambio queda auditado.
                  </p>
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

          <Card>
            <Section
              title="Identidad del servicio"
              description="Nombre y descripción publicados en GetCap. Solo superadministrador; cada cambio queda auditado."
            >
              {serviceFeedback ? <Alert tone="ok">{serviceFeedback}</Alert> : null}
              {serviceError ? <Alert>{serviceError}</Alert> : null}
              <form className={styles.form} onSubmit={submitServiceInfo}>
<fieldset className={styles.plain} disabled={!canEdit}>
                <Field label="Nombre del servicio" htmlFor="service-name" hint="Entre 3 y 255 caracteres.">
                  <Input
                    id="service-name"
                    required
                    minLength={3}
                    maxLength={255}
                    value={serviceName}
                    onChange={(event) => setServiceName(event.target.value)}
                  />
                </Field>
                <Field label="Descripción" htmlFor="service-description" hint="Hasta 512 caracteres.">
                  <Input
                    id="service-description"
                    required
                    maxLength={512}
                    value={serviceDescription}
                    onChange={(event) => setServiceDescription(event.target.value)}
                  />
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
                  ? "Valores aplicados a solicitudes WMLS y detección de cambios. Solo superadministrador; cada cambio queda auditado."
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
                    {limitsError ? <Alert>{limitsError}</Alert> : null}
                    {limitsFeedback ? <p className={styles.faint}>{limitsFeedback}</p> : null}
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
        </>
      ) : null}
    </div>
  );
}
