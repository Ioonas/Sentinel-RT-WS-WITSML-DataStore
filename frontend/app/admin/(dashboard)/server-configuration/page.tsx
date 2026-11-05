"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, Input, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import { Section, Stat } from "@/components/dashboard";
import { ApiError, api, type ServerConfigView } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

export default function ServerConfigurationPage() {
  const { data, error, loading, reload } = useApiQuery<ServerConfigView>("/server-config");
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

  useEffect(() => {
    if (data) {
      setEmail(data.contact_email);
      setPhone(data.contact_phone);
      setServiceName(data.contact_name);
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
              </form>
            </Section>
          </Card>

          <Card>
            <Section
              title="Límites operativos"
              description="Valores efectivos aplicados a solicitudes WMLS y detección de cambios."
            >
              <div className={styles.grid}>
                <Stat label="Máx. nodos de datos" value={data.max_data_nodes.toLocaleString("es")} />
                <Stat label="Máx. puntos de datos" value={data.max_data_points.toLocaleString("es")} />
                <Stat label="Timeout growing" value={`${data.growing_timeout_seconds} s`} />
                <Stat label="Detección de cambios" value={`${data.change_detection_seconds} s`} />
                <Stat label="Máx. latest values" value={data.max_request_latest_values.toLocaleString("es")} />
              </div>
            </Section>
          </Card>
        </>
      ) : null}
    </div>
  );
}
