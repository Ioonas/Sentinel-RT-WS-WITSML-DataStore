"use client";

import { useState, type FormEvent } from "react";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { EmptyRow, Section } from "@/components/dashboard";
import { type AuditPage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

type Filters = {
  actor: string;
  action: string;
  object_type: string;
  object_uid: string;
  result: string;
  correlation_id: string;
  start: string;
  end: string;
};

const EMPTY_FILTERS: Filters = {
  actor: "",
  action: "",
  object_type: "",
  object_uid: "",
  result: "",
  correlation_id: "",
  start: "",
  end: "",
};

function resultTone(result: string): "ok" | "warn" | "danger" | "neutral" {
  if (result === "success") return "ok";
  if (result === "denied") return "warn";
  if (result === "error") return "danger";
  return "neutral";
}

export default function AuditPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [cursor, setCursor] = useState<number | null>(null);
  const [history, setHistory] = useState<(number | null)[]>([]);
  const [path, setPath] = useState<string | null>(null);

  const events = useApiQuery<AuditPage>(path);

  function buildPath(nextCursor: number | null): string {
    const params = new URLSearchParams({ limit: "50" });
    if (nextCursor) params.set("cursor", String(nextCursor));
    for (const [key, value] of Object.entries(filters)) {
      if (value.trim()) params.set(key, value.trim());
    }
    return `/audit-events?${params.toString()}`;
  }

  function search(event: FormEvent) {
    event.preventDefault();
    setCursor(null);
    setHistory([]);
    setPath(buildPath(null));
  }

  function nextPage() {
    if (!events.data?.next_cursor) return;
    setHistory((items) => [...items, cursor]);
    setCursor(events.data.next_cursor);
    setPath(buildPath(events.data.next_cursor));
  }

  function previousPage() {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setHistory((items) => items.slice(0, -1));
    setCursor(previous);
    setPath(buildPath(previous));
  }

  function update(key: keyof Filters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Auditoría"
        description="Registro inmutable de operaciones WMLS y administrativas. Nunca incluye contraseñas ni secretos."
        actions={
          <StatusBadge
            status="neutral"
            label={events.data ? `${events.data.items.length} eventos` : "sin consulta"}
          />
        }
      />

      {events.error ? <Alert>{events.error.message}</Alert> : null}

      <Card>
        <form className={styles.form} onSubmit={search}>
          <div className={styles.formRow}>
            <Field label="Actor" htmlFor="audit-actor">
              <Input id="audit-actor" value={filters.actor} onChange={(event) => update("actor", event.target.value)} />
            </Field>
            <Field label="Acción" htmlFor="audit-action">
              <Input id="audit-action" value={filters.action} onChange={(event) => update("action", event.target.value)} />
            </Field>
            <Field label="Tipo de objeto" htmlFor="audit-object-type">
              <Input
                id="audit-object-type"
                value={filters.object_type}
                onChange={(event) => update("object_type", event.target.value)}
              />
            </Field>
            <Field label="uid del objeto" htmlFor="audit-object-uid">
              <Input
                id="audit-object-uid"
                value={filters.object_uid}
                onChange={(event) => update("object_uid", event.target.value)}
              />
            </Field>
          </div>
          <div className={styles.formRow}>
            <Field label="Resultado" htmlFor="audit-result">
              <Select id="audit-result" value={filters.result} onChange={(event) => update("result", event.target.value)}>
                <option value="">Todos</option>
                <option value="success">success</option>
                <option value="denied">denied</option>
                <option value="error">error</option>
              </Select>
            </Field>
            <Field label="Correlation ID" htmlFor="audit-correlation">
              <Input
                id="audit-correlation"
                value={filters.correlation_id}
                onChange={(event) => update("correlation_id", event.target.value)}
              />
            </Field>
            <Field label="Desde" htmlFor="audit-start">
              <Input
                id="audit-start"
                type="datetime-local"
                value={filters.start}
                onChange={(event) => update("start", event.target.value)}
              />
            </Field>
            <Field label="Hasta" htmlFor="audit-end">
              <Input
                id="audit-end"
                type="datetime-local"
                value={filters.end}
                onChange={(event) => update("end", event.target.value)}
              />
            </Field>
          </div>
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={events.loading}>
              {events.loading ? "Consultando…" : "Buscar eventos"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setFilters(EMPTY_FILTERS);
                setCursor(null);
                setHistory([]);
                setPath(null);
              }}
            >
              Limpiar
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <Section title="Eventos">
          {events.loading ? (
            <Spinner />
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Actor</th>
                    <th>Canal</th>
                    <th>Acción</th>
                    <th>Objeto</th>
                    <th>Resultado</th>
                    <th>Correlation</th>
                    <th>Detalle</th>
                  </tr>
                </thead>
                <tbody>
                  {events.data && events.data.items.length > 0 ? (
                    events.data.items.map((event) => (
                      <tr key={event.id}>
                        <td className={styles.numeric}>{formatDateTime(event.occurred_at)}</td>
                        <td className={styles.wrap}>{event.actor_name}</td>
                        <td>{event.channel}</td>
                        <td className={styles.wrap}>
                          <code>{event.action}</code>
                        </td>
                        <td className={styles.faint}>
                          {event.object_type ? `${event.object_type}: ${event.object_uid ?? "—"}` : "—"}
                        </td>
                        <td>
                          <StatusBadge status={resultTone(event.result)} label={event.result} />
                        </td>
                        <td className={styles.wrap}>
                          <code>{event.correlation_id}</code>
                        </td>
                        <td>
                          <details>
                            <summary>Ver</summary>
                            <pre className={styles.pre}>{JSON.stringify(event.details, null, 2)}</pre>
                          </details>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <EmptyRow colSpan={8}>
                      {path ? "Sin eventos para los filtros indicados." : "Ejecute una búsqueda para consultar la auditoría."}
                    </EmptyRow>
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div className={styles.actions} style={{ marginTop: "var(--space-4)" }}>
            <Button size="sm" onClick={previousPage} disabled={history.length === 0 || events.loading}>
              Anterior
            </Button>
            <Button
              size="sm"
              onClick={nextPage}
              disabled={!events.data?.next_cursor || events.loading}
            >
              Siguiente
            </Button>
            <span className={styles.faint}>
              {events.data?.next_cursor ? "Hay más resultados." : "Fin de los resultados."}
            </span>
          </div>
        </Section>
      </Card>
    </div>
  );
}
