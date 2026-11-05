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
import { EmptyRow, GrantEditor, Section, Tags } from "@/components/dashboard";
import {
  ApiError,
  api,
  type CredentialView,
  type Grant,
  type ServiceAccountView,
} from "@/lib/api";
import { WellPicker } from "@/components/WellPicker";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

type CreatedAccount = {
  account: ServiceAccountView;
  credential: CredentialView;
};

function grantLabel(grant: Grant): string {
  return `${grant.object_type}:${grant.action}${grant.uid_well ? `@${grant.uid_well}` : ""}`;
}

export default function ServiceAccountsPage() {
  const { data, error, loading, reload } = useApiQuery<ServiceAccountView[]>("/service-accounts");
  const [name, setName] = useState("");
  const [role, setRole] = useState("reader");
  const [grants, setGrants] = useState<Grant[]>([
    { object_type: "*", action: "read", uid_well: null },
  ]);
  const [selectedWells, setSelectedWells] = useState<string[]>([]);
  const [cascade, setCascade] = useState(false);
  const [replacesId, setReplacesId] = useState("");
  const [graceDays, setGraceDays] = useState("7");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedAccount | null>(null);
  const [rotated, setRotated] = useState<{ name: string; secret: string } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    setCreated(null);
    setRotated(null);
    try {
      const result = await api<CreatedAccount>("/service-accounts", {
        method: "POST",
        body: JSON.stringify({
          name,
          role,
          grants,
          well_scope: selectedWells.length > 0 ? selectedWells : null,
          can_cascade_delete: cascade,
          replaces_account_id: replacesId || null,
          replacement_grace_days: replacesId ? Number(graceDays) : undefined,
        }),
      });
      setCreated(result);
      setName("");
      setSelectedWells([]);
      setCascade(false);
      setReplacesId("");
      setGraceDays("7");
      setGrants([{ object_type: "*", action: "read", uid_well: null }]);
      reload();
    } catch (caught) {
      setFormError(caught instanceof ApiError ? caught.message : "No se pudo crear la cuenta.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(account: ServiceAccountView) {
    setActionError(null);
    try {
      await api<ServiceAccountView>(`/service-accounts/${account.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !account.enabled }),
      });
      reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudo actualizar la cuenta.");
    }
  }

  async function rotate(account: ServiceAccountView) {
    if (!window.confirm(`¿Rotar la credencial de "${account.name}"? La anterior dejará de funcionar.`)) {
      return;
    }
    setActionError(null);
    setCreated(null);
    try {
      const result = await api<CredentialView>(`/service-accounts/${account.id}/rotate-credential`, {
        method: "POST",
      });
      setRotated({ name: account.name, secret: result.secret });
      reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudo rotar la credencial.");
    }
  }

  async function revoke(account: ServiceAccountView) {
    if (!window.confirm(`¿Revocar la credencial de "${account.name}"?`)) return;
    setActionError(null);
    try {
      await api(`/service-accounts/${account.id}/revoke-credential`, { method: "POST" });
      setRotated(null);
      reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudo revocar la credencial.");
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Cuentas de servicio"
        description="Identidades WMLS con permisos por objeto y alcance opcional por pozo. Las credenciales se muestran una sola vez."
        actions={<StatusBadge status="neutral" label={`${data?.length ?? 0} cuentas`} />}
      />

      {error ? <Alert>{error.message}</Alert> : null}
      {actionError ? <Alert>{actionError}</Alert> : null}

      {created ? (
        <Alert tone="ok">
          Cuenta <strong>{created.account.name}</strong> creada. Guarde ahora la credencial; no volverá a mostrarse.
          <code className={styles.secret}>{created.credential.secret}</code>
        </Alert>
      ) : null}

      {rotated ? (
        <Alert tone="warn">
          Nueva credencial para <strong>{rotated.name}</strong>. La anterior fue invalidada.
          <code className={styles.secret}>{rotated.secret}</code>
        </Alert>
      ) : null}

      <div className={styles.split}>
        <Card>
          <Section
            title="Cuentas registradas"
            description="Los cambios de estado, rotación y revocación quedan auditados."
            actions={<Button size="sm" variant="ghost" onClick={reload}>Actualizar</Button>}
          >
            {loading ? (
              <Spinner />
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Rol</th>
                      <th>Permisos</th>
                      <th>Alcance</th>
                      <th>Estado</th>
                      <th>Último uso</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data && data.length > 0 ? (
                      data.map((account) => (
                        <tr key={account.id}>
                          <td>
                            <strong>{account.name}</strong>
                            <div className={styles.faint}>{account.id}</div>
                          </td>
                          <td>{account.role}</td>
                          <td>
                            <Tags values={account.grants.map(grantLabel)} />
                          </td>
                          <td>
                            <Tags values={account.well_scope ?? []} />
                          </td>
                          <td>
                            <div className={styles.stack}>
                              <StatusBadge
                                status={account.enabled ? "ok" : "danger"}
                                label={account.enabled ? "Activa" : "Deshabilitada"}
                              />
                              <StatusBadge
                                status={account.can_cascade_delete ? "warn" : "neutral"}
                                label={account.can_cascade_delete ? "Borrado en cascada" : "Sin borrado en cascada"}
                              />
                              {account.replaced_by_id ? (
                                <span className={styles.faint}>
                                  Reemplazada por {account.replaced_by_id}
                                  {account.replacement_expires_at
                                    ? ` · vence ${formatDateTime(account.replacement_expires_at)}`
                                    : ""}
                                </span>
                              ) : null}
                            </div>
                          </td>
                          <td className={styles.faint}>{formatDateTime(account.last_used_at)}</td>
                          <td>
                            <div className={styles.actions}>
                              <Button size="sm" onClick={() => toggle(account)}>
                                {account.enabled ? "Deshabilitar" : "Habilitar"}
                              </Button>
                              <Button size="sm" onClick={() => rotate(account)}>
                                Rotar
                              </Button>
                              <Button size="sm" variant="danger" onClick={() => revoke(account)}>
                                Revocar
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={7}>Aún no hay cuentas de servicio.</EmptyRow>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Nueva cuenta" description="Mínimo un permiso WMLS.">
            {formError ? <Alert>{formError}</Alert> : null}
            <form className={styles.form} onSubmit={create}>
              <Field label="Nombre" htmlFor="account-name" hint="3 a 64 caracteres, único.">
                <Input
                  id="account-name"
                  required
                  minLength={3}
                  maxLength={64}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field label="Rol" htmlFor="account-role">
                <Select id="account-role" value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="reader">reader</option>
                  <option value="writer">writer</option>
                </Select>
              </Field>
              <div>
                <span className={styles.statLabel}>Permisos</span>
                <GrantEditor grants={grants} onChange={setGrants} />
              </div>
              <WellPicker value={selectedWells} onChange={setSelectedWells} />
              <label className={styles.statLabel}>
                <input
                  type="checkbox"
                  checked={cascade}
                  onChange={(event) => setCascade(event.target.checked)}
                />{" "}
                Permitir borrado en cascada
              </label>
              <p className={styles.faint}>
                Solo aplica a esta cuenta y no se puede cambiar después. Sin esta opción, borrar un pozo con hijos devuelve error.
              </p>
              <Field
                label="Reemplaza a una cuenta existente"
                hint="Opcional. La cuenta anterior sigue activa durante el periodo de gracia y luego se retira."
                htmlFor="account-replaces"
              >
                <Select id="account-replaces" value={replacesId} onChange={(event) => setReplacesId(event.target.value)}>
                  <option value="">Ninguna</option>
                  {(data ?? [])
                    .filter((account) => !account.replaced_by_id)
                    .map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.name}
                      </option>
                    ))}
                </Select>
              </Field>
              {replacesId ? (
                <Field label="Días de gracia" hint="De 0 a 90. Por defecto, 7." htmlFor="account-grace">
                  <Input
                    id="account-grace"
                    type="number"
                    min={0}
                    max={90}
                    value={graceDays}
                    onChange={(event) => setGraceDays(event.target.value)}
                  />
                </Field>
              ) : null}
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "Creando…" : "Crear cuenta"}
              </Button>
            </form>
          </Section>
        </Card>
      </div>
    </div>
  );
}
