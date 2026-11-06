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
import { EmptyRow, Section, Tags } from "@/components/dashboard";
import { ActionMenu } from "@/components/ActionMenu";
import { ModalDialog } from "@/components/Dialog";
import { ApiError, api, type MessageView, type ObjectView, type SessionView } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { useApiQuery } from "@/lib/hooks";
import { useReauth } from "@/components/Reauth";
import dialogStyles from "@/components/Dialog.module.css";
import styles from "../dashboard.module.css";

const OBJECT_TYPES = ["well", "wellbore", "log", "mudLog", "trajectory"] as const;

/** Nombres en español para los tipos WITSML; el valor técnico sigue siendo el de la API. */
const OBJECT_TYPE_LABELS: Record<string, string> = {
  well: "Pozo",
  wellbore: "Pozo lateral",
  log: "Registro",
  mudLog: "Registro de lodo",
  trajectory: "Trayectoria",
};

function objectPath(type: string, uid: string, uidWell?: string | null, uidWellbore?: string | null) {
  const params = new URLSearchParams();
  if (uidWell) params.set("uid_well", uidWell);
  if (uidWellbore) params.set("uid_wellbore", uidWellbore);
  const query = params.toString();
  return `/objects/${encodeURIComponent(type)}/${encodeURIComponent(uid)}${query ? `?${query}` : ""}`;
}

export default function ObjectsPage() {
  const { runWithReauth } = useReauth();
  const [objectType, setObjectType] = useState<string>("well");
  const [uidWell, setUidWell] = useState("");
  const [uidWellbore, setUidWellbore] = useState("");
  const [name, setName] = useState("");
  const [queryPath, setQueryPath] = useState<string | null>(null);

  const profile = useApiQuery<SessionView>("/profile");
  const canCreate = can(profile.data, "admin.objects.write");
  const canDelete = can(profile.data, "admin.objects.delete");
  const wellOptions = useApiQuery<ObjectView[]>(
    canCreate ? "/objects?objectType=well&limit=1000" : null,
  );
  const [createType, setCreateType] = useState<"well" | "wellbore">("well");
  const [createUid, setCreateUid] = useState("");
  const [createName, setCreateName] = useState("");
  const [createParent, setCreateParent] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const results = useApiQuery<ObjectView[]>(queryPath);
  const [detail, setDetail] = useState<ObjectView | null>(null);
  const [dependencies, setDependencies] = useState<string[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<ObjectView | null>(null);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);

  function search(event: FormEvent) {
    event.preventDefault();
    setDetail(null);
    setDependencies(null);
    setActionError(null);
    const params = new URLSearchParams({ objectType, limit: "200" });
    if (uidWell.trim()) params.set("uid_well", uidWell.trim());
    if (uidWellbore.trim()) params.set("uid_wellbore", uidWellbore.trim());
    if (name.trim()) params.set("name", name.trim());
    setQueryPath(`/objects?${params.toString()}`);
  }

  async function inspect(item: ObjectView) {
    setActionError(null);
    setDependencies(null);
    try {
      const result = await api<ObjectView>(
        objectPath(item.object_type, item.uid, item.uid_well, item.uid_wellbore),
      );
      setDetail(result);
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudo cargar el objeto.");
    }
  }

  async function loadDependencies(item: ObjectView) {
    setActionError(null);
    try {
      const result = await api<string[]>(
        `${objectPath(item.object_type, item.uid, item.uid_well, item.uid_wellbore)}/dependencies`,
      );
      setDetail(item);
      setDependencies(result);
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudieron cargar las dependencias.");
    }
  }

  function startDelete(item: ObjectView) {
    setDeleteTarget(item);
    setReason("");
    setConfirmation("");
    setActionError(null);
    setMessage(null);
  }

  async function createObject(event: FormEvent) {
    event.preventDefault();
    setCreateBusy(true);
    setCreateError(null);
    setMessage(null);
    try {
      const created = await runWithReauth(() =>
        api<ObjectView>(`/objects/${createType}`, {
          method: "POST",
          body: JSON.stringify({
            uid: createUid.trim() || null,
            name: createName.trim(),
            uid_well: createType === "wellbore" ? createParent : null,
          }),
        }),
      );
      setMessage(
        `${createType === "well" ? "Pozo" : "Pozo lateral"} creado: ${created.name ?? created.uid} (uid ${created.uid}).`,
      );
      setCreateUid("");
      setCreateName("");
      wellOptions.reload();
      if (queryPath) results.reload();
    } catch (caught) {
      setCreateError(caught instanceof ApiError ? caught.message : "No se pudo crear el objeto.");
    } finally {
      setCreateBusy(false);
    }
  }

  async function remove(event: FormEvent) {
    event.preventDefault();
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setActionError(null);
    try {
      const result = await runWithReauth(() =>
        api<MessageView>(
        `${objectPath(deleteTarget.object_type, deleteTarget.uid, deleteTarget.uid_well, deleteTarget.uid_wellbore)}/delete`,
        {
          method: "POST",
          body: JSON.stringify({ reason, confirmation }),
        },
        ),
      );
      setMessage(result.message);
      setDeleteTarget(null);
      setDetail(null);
      setDependencies(null);
      results.reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudo eliminar el objeto.");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Objetos WITSML"
        description="Inventario de pozos, sondeos, registros y trayectorias. El borrado nunca es en cascada."
        actions={<StatusBadge status="neutral" label={OBJECT_TYPE_LABELS[objectType] ?? objectType} />}
      />

      {profile.data?.linked_service_account ? (
        <Alert tone="ok">
          Viendo datos de la cuenta de servicio <strong>{profile.data.linked_service_account}</strong>. Solo lectura, y solo los pozos que esa cuenta crea.
        </Alert>
      ) : null}
      {message ? <Alert tone="ok">{message}</Alert> : null}
      {actionError ? <Alert>{actionError}</Alert> : null}
      {results.error ? <Alert>{results.error.message}</Alert> : null}

      <Card>
        <form className={styles.form} onSubmit={search}>
          <div className={styles.formRow}>
            <Field label="Tipo de objeto" htmlFor="object-type">
              <Select
                id="object-type"
                value={objectType}
                onChange={(event) => setObjectType(event.target.value)}
              >
                {OBJECT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {OBJECT_TYPE_LABELS[type]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Pozo (uidWell)" htmlFor="object-well" hint="Opcional. Limita la búsqueda a un pozo.">
              <Input
                id="object-well"
                value={uidWell}
                onChange={(event) => setUidWell(event.target.value)}
              />
            </Field>
            <Field label="Pozo lateral (uidWellbore)" htmlFor="object-wellbore" hint="Opcional.">
              <Input
                id="object-wellbore"
                value={uidWellbore}
                onChange={(event) => setUidWellbore(event.target.value)}
              />
            </Field>
            <Field label="Nombre" htmlFor="object-name">
              <Input
                id="object-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
          </div>
          <div className={styles.actions}>
            <Button type="submit" variant="primary" disabled={results.loading}>
              {results.loading ? "Buscando…" : "Buscar objetos"}
            </Button>
          </div>
        </form>
      </Card>

      {canCreate ? (
        <Card>
          <Section
            title="Crear pozo o pozo lateral"
            description="Alta directa en el Store, con las mismas validaciones XSD que WMLS_AddToStore. Requiere reautenticación y queda auditada."
          >
            {createError ? <Alert>{createError}</Alert> : null}
            <form className={styles.form} onSubmit={createObject}>
              <div className={styles.formRow}>
                <Field label="Tipo" htmlFor="create-type">
                  <Select
                    id="create-type"
                    value={createType}
                    onChange={(event) => setCreateType(event.target.value as "well" | "wellbore")}
                  >
                    <option value="well">Pozo</option>
                    <option value="wellbore">Pozo lateral (wellbore)</option>
                  </Select>
                </Field>
                {createType === "wellbore" ? (
                  <Field label="Pozo padre" htmlFor="create-parent" hint="Pozo al que pertenece el pozo lateral.">
                    <Select
                      id="create-parent"
                      value={createParent}
                      onChange={(event) => setCreateParent(event.target.value)}
                    >
                      <option value="">Seleccione un pozo…</option>
                      {(wellOptions.data ?? []).map((well) => (
                        <option key={well.uid} value={well.uid}>
                          {well.name ?? well.uid}
                        </option>
                      ))}
                    </Select>
                  </Field>
                ) : null}
                <Field label="Nombre" htmlFor="create-name">
                  <Input
                    id="create-name"
                    required
                    maxLength={64}
                    value={createName}
                    onChange={(event) => setCreateName(event.target.value)}
                  />
                </Field>
                <Field label="UID (opcional)" htmlFor="create-uid" hint="Si se omite, el sistema asigna uno.">
                  <Input
                    id="create-uid"
                    maxLength={64}
                    value={createUid}
                    onChange={(event) => setCreateUid(event.target.value)}
                  />
                </Field>
              </div>
              <div className={styles.actions}>
                <Button
                  type="submit"
                  variant="primary"
                  disabled={createBusy || (createType === "wellbore" && !createParent)}
                >
                  {createBusy ? "Creando…" : "Crear"}
                </Button>
              </div>
            </form>
          </Section>
        </Card>
      ) : null}

      <div className={styles.split}>
        <Card>
          <Section
            title="Resultados"
            description="Máximo 200 objetos por consulta; el alcance por pozo se aplica automáticamente."
          >
            {results.loading ? (
              <Spinner />
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>uid</th>
                      <th>Nombre</th>
                      <th>Jerarquía</th>
                      <th>Cambiado</th>
                      <th>Estado</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.data && results.data.length > 0 ? (
                      results.data.map((item) => (
                        <tr key={`${item.object_type}:${item.uid}:${item.uid_well ?? ""}`}>
                          <td className={styles.wrap}>
                            <code>{item.uid}</code>
                          </td>
                          <td>{item.name || "—"}</td>
                          <td className={styles.faint}>
                            {item.uid_well ? `pozo ${item.uid_well}` : "—"}
                            {item.uid_wellbore ? ` · sondeo ${item.uid_wellbore}` : ""}
                          </td>
                          <td className={styles.faint}>{formatDateTime(item.changed_at)}</td>
                          <td>
                            <StatusBadge
                              status={item.growing ? "warn" : "neutral"}
                              label={item.growing ? "En crecimiento" : "Estable"}
                            />
                          </td>
                          <td>
                            <div className={styles.actions}>
                              <Button size="sm" onClick={() => inspect(item)}>
                                Ver
                              </Button>
                              <ActionMenu
                                label="Más acciones"
                                subject={item.name || item.uid}
                                items={[
                                  { label: "Ver dependencias", onSelect: () => loadDependencies(item) },
                                  ...(canDelete
                                    ? [{ label: "Eliminar objeto", danger: true, onSelect: () => startDelete(item) }]
                                    : []),
                                ]}
                              />
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={6}>
                        {queryPath ? "Sin resultados para los filtros indicados." : "Ejecute una búsqueda para listar objetos."}
                      </EmptyRow>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Detalle">
            {detail ? (
              <dl className={styles.detailsGrid}>
                <dt>Tipo</dt>
                <dd>{OBJECT_TYPE_LABELS[detail.object_type] ?? detail.object_type}</dd>
                <dt>uid</dt>
                <dd className={styles.wrap}>{detail.uid}</dd>
                <dt>Nombre</dt>
                <dd>{detail.name || "—"}</dd>
                <dt>uidWell</dt>
                <dd className={styles.wrap}>{detail.uid_well || "—"}</dd>
                <dt>uidWellbore</dt>
                <dd className={styles.wrap}>{detail.uid_wellbore || "—"}</dd>
                <dt>Creado</dt>
                <dd>{formatDateTime(detail.created_at)}</dd>
                <dt>Cambiado</dt>
                <dd>{formatDateTime(detail.changed_at)}</dd>
                <dt>En crecimiento</dt>
                <dd>{detail.growing ? "Sí" : "No"}</dd>
                <dt>Dependencias</dt>
                <dd>
                  {dependencies ? <Tags values={dependencies} /> : <span className={styles.faint}>Pulse “Dependencias”.</span>}
                </dd>
              </dl>
            ) : (
              <p className={styles.muted}>Seleccione “Ver” en un objeto para inspeccionar su detalle.</p>
            )}
          </Section>
        </Card>
      </div>

      {deleteTarget ? (
        <ModalDialog
          titleId="delete-object-title"
          descriptionId="delete-object-description"
          role="alertdialog"
          tone="danger"
          busy={deleteBusy}
          onClose={() => setDeleteTarget(null)}
        >
          <h2 id="delete-object-title" className={dialogStyles.title}>
            Eliminar {(OBJECT_TYPE_LABELS[deleteTarget.object_type] ?? deleteTarget.object_type).toLowerCase()} {deleteTarget.uid}
          </h2>
          <p id="delete-object-description" className={dialogStyles.text}>
            El objeto se marca como eliminado, no se borra físicamente. Queda registrado en ChangeLog. Para confirmar, escriba su uid completo.
          </p>
          <form className={dialogStyles.form} onSubmit={remove}>
            <Field label="Motivo" htmlFor="delete-reason" hint="Mínimo 5 caracteres.">
              <Input
                id="delete-reason"
                data-initial-focus
                required
                minLength={5}
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
            <Field label="uid del objeto" htmlFor="delete-confirmation" hint={`Escriba exactamente: ${deleteTarget.uid}`}>
              <Input
                id="delete-confirmation"
                required
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </Field>
            <div className={dialogStyles.actions}>
              <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleteBusy}>
                Cancelar
              </Button>
              <Button
                type="submit"
                variant="danger"
                disabled={deleteBusy || confirmation !== deleteTarget.uid || reason.trim().length < 5}
              >
                {deleteBusy ? "Eliminando…" : "Eliminar objeto"}
              </Button>
            </div>
          </form>
        </ModalDialog>
      ) : null}
    </div>
  );
}
