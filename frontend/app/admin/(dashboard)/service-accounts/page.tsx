"use client";

import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, Input, PageHeader, Select, Spinner, StatusBadge, PasswordInput } from "@/components/ui";
import { EmptyRow, GrantEditor, Section, Tags } from "@/components/dashboard";
import { ActionMenu } from "@/components/ActionMenu";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ModalDialog } from "@/components/Dialog";
import { useReauth } from "@/components/Reauth";
import dialogStyles from "@/components/Dialog.module.css";
import {
  ApiError,
  api,
  type CredentialView,
  type Grant,
  type InvitationView,
  type MessageView,
  type ServiceAccountView,
  type WebAccessInvitationView,
  type WebAccessListView,
  type WebAccessUserView,
} from "@/lib/api";
import { WellPicker } from "@/components/WellPicker";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

const ROLE_LABELS: Record<string, string> = {
  reader: "Solo lectura",
  writer: "Lectura y escritura",
};

type ConfirmRequest = {
  title: string;
  description: string;
  confirmLabel: string;
  tone: "warn" | "danger";
  run: () => Promise<void>;
};

type CreatedAccount = {
  account: ServiceAccountView;
  credential: CredentialView;
};

function grantLabel(grant: Grant): string {
  return `${grant.object_type}:${grant.action}${grant.uid_well ? `@${grant.uid_well}` : ""}`;
}

export default function ServiceAccountsPage() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, error, loading, reload } = useApiQuery<ServiceAccountView[]>(
    showArchived ? "/service-accounts?include_archived=true" : "/service-accounts",
  );
  const [name, setName] = useState("");
  const [role, setRole] = useState("reader");
  const [grants, setGrants] = useState<Grant[]>([
    { object_type: "*", action: "read", uid_well: null },
  ]);
  const [allWells, setAllWells] = useState(false);
  const [cascade, setCascade] = useState(false);
  const [replacesId, setReplacesId] = useState("");
  const [credential, setCredential] = useState("");
  const [credentialConfirm, setCredentialConfirm] = useState("");
  const [graceDays, setGraceDays] = useState("7");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedAccount | null>(null);
  const [rotated, setRotated] = useState<{ name: string; secret: string | null } | null>(null);
  const [rotating, setRotating] = useState<ServiceAccountView | null>(null);
  const [webAccount, setWebAccount] = useState<ServiceAccountView | null>(null);
  const [webUsers, setWebUsers] = useState<WebAccessUserView[]>([]);
  const [webEmail, setWebEmail] = useState("");
  const [webBusy, setWebBusy] = useState(false);
  const [webError, setWebError] = useState<string | null>(null);
  const [webMessage, setWebMessage] = useState<string | null>(null);
  const [webRemoving, setWebRemoving] = useState<WebAccessUserView | null>(null);
  const [webInvitations, setWebInvitations] = useState<WebAccessInvitationView[]>([]);
  const [webCancelling, setWebCancelling] = useState<WebAccessInvitationView | null>(null);
  const [rotateCredential, setRotateCredential] = useState("");
  const [rotateConfirm, setRotateConfirm] = useState("");
  const [rotateBusy, setRotateBusy] = useState(false);
  const [rotateError, setRotateError] = useState<string | null>(null);
  const { runWithReauth } = useReauth();
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<ConfirmRequest | null>(null);
  const [editing, setEditing] = useState<ServiceAccountView | null>(null);
  const [editRole, setEditRole] = useState("reader");
  const [editGrants, setEditGrants] = useState<Grant[]>([]);
  const [editWells, setEditWells] = useState<string[]>([]);
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (credential && credential !== credentialConfirm) {
      setFormError("La credencial y su repetición no coinciden.");
      return;
    }
    setBusy(true);
    setFormError(null);
    setCreated(null);
    setRotated(null);
    try {
      const result = await runWithReauth(() =>
        api<CreatedAccount>("/service-accounts", {
          method: "POST",
          body: JSON.stringify({
            name,
            role,
            grants,
            // null = todos los pozos; lista vacía = solo los pozos que la cuenta cree.
            well_scope: allWells ? null : [],
            can_cascade_delete: cascade,
            replaces_account_id: replacesId || null,
            replacement_grace_days: replacesId ? Number(graceDays) : undefined,
            credential: credential || undefined,
          }),
        }),
      );
      setCreated(result);
      setName("");
      setAllWells(false);
      setCascade(false);
      setReplacesId("");
      setGraceDays("7");
      setCredential("");
      setCredentialConfirm("");
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

  function rotate(account: ServiceAccountView) {
    setRotating(account);
    setRotateCredential("");
    setRotateConfirm("");
    setRotateError(null);
  }

  function closeRotate() {
    if (rotateBusy) return;
    setRotating(null);
  }

  async function submitRotate(event: FormEvent) {
    event.preventDefault();
    if (!rotating) return;
    if (rotateCredential && rotateCredential !== rotateConfirm) {
      setRotateError("La credencial y su repetición no coinciden.");
      return;
    }
    setRotateBusy(true);
    setRotateError(null);
    try {
      const result = await api<CredentialView>(
        `/service-accounts/${rotating.id}/rotate-credential`,
        {
          method: "POST",
          body: rotateCredential ? JSON.stringify({ credential: rotateCredential }) : undefined,
        },
      );
      setCreated(null);
      setRotated({ name: rotating.name, secret: result.secret });
      setRotating(null);
      reload();
    } catch (caught) {
      setRotateError(caught instanceof ApiError ? caught.message : "No se pudo rotar la credencial.");
    } finally {
      setRotateBusy(false);
    }
  }

  function archive(account: ServiceAccountView) {
    setConfirming({
      title: `Archivar la cuenta «${account.name}»`,
      description:
        "La cuenta deja de autenticarse y sale de la lista. Su historial de auditoría se conserva. Se borrará automáticamente 3 días después de archivarse.",
      confirmLabel: "Archivar cuenta",
      tone: "danger",
      run: () => archiveNow(account),
    });
  }

  async function archiveNow(account: ServiceAccountView) {
    setActionError(null);
    try {
      await runWithReauth(() =>
        api<ServiceAccountView>(`/service-accounts/${account.id}/archive`, { method: "POST" }),
      );
      reload();
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "reauth_required") {
        setActionError("La cuenta no se archivó. Confirme su contraseña para continuar.");
      } else {
        setActionError(caught instanceof ApiError ? caught.message : "No se pudo archivar la cuenta.");
      }
    }
  }

  function revoke(account: ServiceAccountView) {
    setConfirming({
      title: `Revocar la credencial de «${account.name}»`,
      description:
        "La cuenta deja de autenticarse hasta que se genere una credencial nueva. Esta acción no se puede deshacer.",
      confirmLabel: "Revocar credencial",
      tone: "danger",
      run: () => revokeNow(account),
    });
  }

  async function revokeNow(account: ServiceAccountView) {
    setActionError(null);
    try {
      await api(`/service-accounts/${account.id}/revoke-credential`, { method: "POST" });
      setRotated(null);
      reload();
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : "No se pudo revocar la credencial.");
    }
  }

  function openEdit(account: ServiceAccountView) {
    setEditing(account);
    setEditRole(account.role);
    setEditGrants(account.grants);
    setEditWells(account.well_scope ?? []);
    setEditError(null);
  }

  function closeEdit() {
    if (editBusy) return;
    setEditing(null);
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setEditBusy(true);
    setEditError(null);
    try {
      // Lista vacía de pozos = todos los pozos (el servidor la guarda como alcance nulo).
      await api<ServiceAccountView>(`/service-accounts/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: editRole, grants: editGrants, well_scope: editWells }),
      });
      setEditing(null);
      reload();
    } catch (caught) {
      setEditError(caught instanceof ApiError ? caught.message : "No se pudo guardar la cuenta.");
    } finally {
      setEditBusy(false);
    }
  }

  async function loadWebAccess(account: ServiceAccountView) {
    try {
      const result = await api<WebAccessListView>(`/service-accounts/${account.id}/web-access`);
      setWebUsers(result.users);
      setWebInvitations(result.invitations);
    } catch (caught) {
      setWebError(caught instanceof ApiError ? caught.message : "No se pudieron cargar las personas con acceso.");
    }
  }

  function openWebAccess(account: ServiceAccountView) {
    setWebAccount(account);
    setWebEmail("");
    setWebError(null);
    setWebMessage(null);
    setWebUsers([]);
    setWebInvitations([]);
    void loadWebAccess(account);
  }

  function closeWebAccess() {
    setWebAccount(null);
    setWebRemoving(null);
  }

  async function inviteWebAccess(event: FormEvent) {
    event.preventDefault();
    if (!webAccount) return;
    setWebBusy(true);
    setWebError(null);
    setWebMessage(null);
    try {
      const invitation = await runWithReauth(() =>
        api<InvitationView>(`/service-accounts/${webAccount.id}/web-access`, {
          method: "POST",
          body: JSON.stringify({ email: webEmail.trim() }),
        }),
      );
      setWebMessage(`Invitación enviada a ${invitation.email}. Vence en 72 horas.`);
      setWebEmail("");
      await loadWebAccess(webAccount);
    } catch (caught) {
      setWebError(caught instanceof ApiError ? caught.message : "No se pudo crear la invitación.");
    } finally {
      setWebBusy(false);
    }
  }

  async function resendWebInvitation(item: WebAccessInvitationView) {
    if (!webAccount) return;
    setWebBusy(true);
    setWebError(null);
    setWebMessage(null);
    try {
      const result = await runWithReauth(() =>
        api<InvitationView>(`/invitations/${item.id}/resend`, { method: "POST" }),
      );
      setWebMessage(`Invitación reenviada a ${result.email}. La anterior dejó de ser válida.`);
      await loadWebAccess(webAccount);
    } catch (caught) {
      setWebError(caught instanceof ApiError ? caught.message : "No se pudo reenviar la invitación.");
    } finally {
      setWebBusy(false);
    }
  }

  async function cancelWebInvitation() {
    if (!webAccount || !webCancelling) return;
    setWebBusy(true);
    setWebError(null);
    try {
      await runWithReauth(() => api(`/invitations/${webCancelling.id}/revoke`, { method: "POST" }));
      setWebMessage(`Invitación cancelada para ${webCancelling.email}.`);
      setWebCancelling(null);
      await loadWebAccess(webAccount);
    } catch (caught) {
      setWebError(caught instanceof ApiError ? caught.message : "No se pudo cancelar la invitación.");
    } finally {
      setWebBusy(false);
    }
  }

  async function removeWebAccess() {
    if (!webAccount || !webRemoving) return;
    setWebBusy(true);
    setWebError(null);
    try {
      const result = await runWithReauth(() =>
        api<MessageView>(`/service-accounts/${webAccount.id}/web-access/${webRemoving.id}`, {
          method: "DELETE",
        }),
      );
      setWebMessage(result.message);
      setWebRemoving(null);
      await loadWebAccess(webAccount);
    } catch (caught) {
      setWebError(caught instanceof ApiError ? caught.message : "No se pudo quitar el acceso.");
    } finally {
      setWebBusy(false);
    }
  }

  function runConfirmed() {
    const request = confirming;
    setConfirming(null);
    void request?.run();
  }

  return (
    <div className={styles.stack}>
      {webAccount ? (
        <>
          <ModalDialog titleId="web-access-title" wide busy={webBusy} onClose={closeWebAccess}>
            <h2 id="web-access-title" className={dialogStyles.title}>
              Acceso web a «{webAccount.name}»
            </h2>
            <p className={dialogStyles.text}>
              Las personas invitadas entran a la interfaz web y ven solo los pozos que crea esta cuenta, en modo lectura.
            </p>
            {webError ? <Alert>{webError}</Alert> : null}
            {webMessage ? <Alert tone="ok">{webMessage}</Alert> : null}
            <div className={styles.stack}>
              <span className={styles.groupLabel}>Invitaciones pendientes</span>
              {webInvitations.length > 0 ? (
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <tbody>
                      {webInvitations.map((item) => {
                        const expired = new Date(item.expires_at).getTime() < Date.now();
                        return (
                          <tr key={item.id}>
                            <td className={styles.wrap}>{item.email}</td>
                            <td>
                              <StatusBadge status={expired ? "danger" : "neutral"} label={expired ? "Vencida" : "Pendiente"} />
                            </td>
                            <td className={styles.faint}>Vence {formatDateTime(item.expires_at)}</td>
                            <td>
                              <div className={styles.actions}>
                                <Button size="sm" disabled={webBusy} onClick={() => void resendWebInvitation(item)}>
                                  Reenviar
                                </Button>
                                <Button size="sm" variant="danger" disabled={webBusy} onClick={() => setWebCancelling(item)}>
                                  Cancelar invitación
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className={styles.faint}>No hay invitaciones pendientes.</p>
              )}
              <span className={styles.groupLabel}>Personas con acceso</span>
              {webUsers.length > 0 ? (
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <tbody>
                      {webUsers.map((user) => (
                        <tr key={user.id}>
                          <td className={styles.wrap}>{user.email}</td>
                          <td>
                            <StatusBadge
                              status={user.enabled ? "ok" : "danger"}
                              label={user.enabled ? "Activa" : "Deshabilitada"}
                            />
                          </td>
                          <td>
                            <Button size="sm" variant="danger" disabled={webBusy} onClick={() => setWebRemoving(user)}>
                              Quitar acceso
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className={styles.faint}>Nadie tiene acceso web todavía.</p>
              )}
            </div>
            <form className={dialogStyles.form} onSubmit={inviteWebAccess}>
              <Field label="Correo de la persona" htmlFor="web-access-email" hint="Recibe una invitación que vence en 72 horas.">
                <Input
                  id="web-access-email"
                  type="email"
                  required
                  data-initial-focus
                  value={webEmail}
                  onChange={(event) => setWebEmail(event.target.value)}
                />
              </Field>
              <div className={dialogStyles.actions}>
                <Button variant="ghost" disabled={webBusy} onClick={closeWebAccess}>
                  Cerrar
                </Button>
                <Button type="submit" variant="primary" disabled={webBusy || !webEmail.trim()}>
                  {webBusy ? "Enviando…" : "Invitar"}
                </Button>
              </div>
            </form>
          </ModalDialog>
          {webCancelling ? (
            <ConfirmDialog
              title="Cancelar invitación"
              description={`La invitación enviada a ${webCancelling.email} dejará de ser válida.`}
              confirmLabel="Cancelar invitación"
              tone="danger"
              busy={webBusy}
              onConfirm={() => void cancelWebInvitation()}
              onCancel={() => setWebCancelling(null)}
            />
          ) : null}
          {webRemoving ? (
            <ConfirmDialog
              title="Quitar acceso web"
              description={`${webRemoving.email} dejará de ver los datos de «${webAccount.name}». Sus sesiones se cerrarán.`}
              confirmLabel="Quitar acceso"
              tone="danger"
              busy={webBusy}
              onConfirm={() => void removeWebAccess()}
              onCancel={() => setWebRemoving(null)}
            />
          ) : null}
        </>
      ) : null}

      {rotating ? (
        <ModalDialog titleId="rotate-title" wide busy={rotateBusy} onClose={closeRotate}>
          <h2 id="rotate-title" className={dialogStyles.title}>
            Rotar la credencial de «{rotating.name}»
          </h2>
          <p className={dialogStyles.text}>
            La credencial actual deja de funcionar de inmediato. Déjela vacía para que el servidor
            genere una nueva; esa sí se muestra una sola vez.
          </p>
          {rotateError ? <Alert>{rotateError}</Alert> : null}
          <form className={dialogStyles.form} onSubmit={submitRotate}>
            <Field
              label="Credencial propia (opcional)"
              htmlFor="rotate-credential"
              hint={`15 caracteres mínimo; letras, números, punto, guion y guion bajo. Máximo ${Math.max(0, 56 - rotating.name.length)} para este nombre.`}
            >
              <PasswordInput
                id="rotate-credential"
                data-initial-focus=""
                autoComplete="new-password"
                minLength={15}
                maxLength={Math.max(0, 56 - rotating.name.length)}
                pattern="[A-Za-z0-9._\-]*"
                value={rotateCredential}
                onChange={(event) => setRotateCredential(event.target.value)}
              />
            </Field>
            {rotateCredential ? (
              <Field label="Repetir credencial" htmlFor="rotate-credential-confirm">
                <PasswordInput
                  id="rotate-credential-confirm"
                  autoComplete="new-password"
                  value={rotateConfirm}
                  onChange={(event) => setRotateConfirm(event.target.value)}
                />
              </Field>
            ) : null}
            <div className={dialogStyles.actions}>
              <Button type="button" variant="ghost" onClick={closeRotate} disabled={rotateBusy}>
                Cancelar
              </Button>
              <Button type="submit" variant="primary" disabled={rotateBusy}>
                {rotateBusy ? "Rotando…" : "Rotar credencial"}
              </Button>
            </div>
          </form>
        </ModalDialog>
      ) : null}
      {editing ? (
        <ModalDialog titleId="edit-account-title" wide busy={editBusy} onClose={closeEdit}>
          <h2 id="edit-account-title" className={dialogStyles.title}>
            Editar «{editing.name}»
          </h2>
          <p className={dialogStyles.text}>
            Cambiar el rol, los permisos o el alcance de pozos. Los cambios aplican a las
            próximas peticiones de la cuenta.
          </p>
          {editError ? <Alert>{editError}</Alert> : null}
          <form className={dialogStyles.form} onSubmit={saveEdit}>
            <Field label="Rol" htmlFor="edit-role">
              <Select
                id="edit-role"
                data-initial-focus=""
                value={editRole}
                onChange={(event) => setEditRole(event.target.value)}
              >
                <option value="reader">reader</option>
                <option value="writer">writer</option>
              </Select>
            </Field>
            <div>
              <span className={styles.groupLabel}>Permisos</span>
              <GrantEditor grants={editGrants} onChange={setEditGrants} />
            </div>
            <WellPicker value={editWells} onChange={setEditWells} />
            <div className={dialogStyles.actions}>
              <Button type="button" variant="ghost" onClick={closeEdit} disabled={editBusy}>
                Cancelar
              </Button>
              <Button type="submit" variant="primary" disabled={editBusy}>
                {editBusy ? "Guardando…" : "Guardar cambios"}
              </Button>
            </div>
          </form>
        </ModalDialog>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          title={confirming.title}
          description={confirming.description}
          confirmLabel={confirming.confirmLabel}
          tone={confirming.tone}
          onConfirm={runConfirmed}
          onCancel={() => setConfirming(null)}
        />
      ) : null}
      <PageHeader
        title="Cuentas de servicio"
        description="Identidades WMLS con permisos por objeto y alcance opcional por pozo. Las credenciales se muestran una sola vez."
        actions={<StatusBadge status="neutral" label={`${data?.length ?? 0} cuentas`} />}
      />

      {error ? <Alert>{error.message}</Alert> : null}
      {actionError ? <Alert>{actionError}</Alert> : null}

      {created ? (
        <Alert tone="ok">
          Cuenta <strong>{created.account.name}</strong> creada.{" "}
          {created.credential.secret ? (
            <>
              Guarde ahora la credencial; no volverá a mostrarse.
              <code className={styles.secret}>{created.credential.secret}</code>
            </>
          ) : (
            created.credential.message
          )}
        </Alert>
      ) : null}

      {rotated ? (
        <Alert tone="warn">
          Nueva credencial para <strong>{rotated.name}</strong>. La anterior fue invalidada.
          {rotated.secret ? (
            <code className={styles.secret}>{rotated.secret}</code>
          ) : (
            " Se guardó la credencial que definió el administrador."
          )}
        </Alert>
      ) : null}

      <div className={styles.split}>
        <Card>
          <Section
            title="Cuentas registradas"
            description="Los cambios de estado, rotación y revocación quedan auditados."
            actions={
              <div className={styles.actions}>
                <label className={styles.faint} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <input
                    type="checkbox"
                    checked={showArchived}
                    onChange={(event) => setShowArchived(event.target.checked)}
                  />
                  Mostrar archivadas
                </label>
                <Button size="sm" variant="ghost" onClick={reload}>Actualizar</Button>
              </div>
            }
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
                          </td>
                          <td>{ROLE_LABELS[account.role] ?? account.role}</td>
                          <td>
                            <Tags values={account.grants.map(grantLabel)} />
                          </td>
                          <td>
                            {account.well_scope === null ? (
                              <span className={styles.faint}>Todos los pozos</span>
                            ) : (
                              <Tags values={account.well_scope} />
                            )}
                          </td>
                          <td>
                            <div className={styles.stack}>
                              <StatusBadge
                                status={account.archived_at ? "neutral" : account.enabled ? "ok" : "danger"}
                                label={account.archived_at ? "Archivada" : account.enabled ? "Activa" : "Deshabilitada"}
                              />
                              {account.can_cascade_delete ? (
                                <span className={styles.faint}>Puede borrar en cascada</span>
                              ) : null}
                              {account.replaced_by_id ? (
                                <span className={styles.faint}>
                                  Reemplazada por {data?.find((other) => other.id === account.replaced_by_id)?.name ?? "otra cuenta"}
                                  {account.replacement_expires_at
                                    ? ` · vence ${formatDateTime(account.replacement_expires_at)}`
                                    : ""}
                                </span>
                              ) : null}
                            </div>
                          </td>
                          <td className={styles.faint}>{formatDateTime(account.last_used_at)}</td>
                          <td>
                            {account.archived_at ? (
                              <span className={styles.faint}>
                                Solo lectura{account.purge_at ? ` · se borra el ${formatDateTime(account.purge_at)}` : ""}
                              </span>
                            ) : (
                            <ActionMenu
                              subject={account.name}
                              items={[
                                { label: "Editar", onSelect: () => openEdit(account) },
                                { label: "Acceso web", onSelect: () => openWebAccess(account) },
                                {
                                  label: account.enabled ? "Deshabilitar" : "Habilitar",
                                  onSelect: () => toggle(account),
                                },
                                { label: "Rotar credencial", onSelect: () => rotate(account) },
                                {
                                  label: "Revocar credencial",
                                  danger: true,
                                  onSelect: () => revoke(account),
                                },
                                {
                                  label: "Archivar cuenta",
                                  danger: true,
                                  onSelect: () => archive(account),
                                },
                              ]}
                            />
                            )}
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
              <Field label="Rol" htmlFor="account-role" hint="Solo lectura consulta el Store; lectura y escritura también puede modificarlo.">
                <Select id="account-role" value={role} onChange={(event) => setRole(event.target.value)}>
                  <option value="reader">Solo lectura</option>
                  <option value="writer">Lectura y escritura</option>
                </Select>
              </Field>
              <div>
                <span className={styles.groupLabel}>Permisos</span>
                <GrantEditor grants={grants} onChange={setGrants} />
              </div>
              <div>
                <label className={styles.groupLabel}>
                  <input type="checkbox" checked={allWells} onChange={(event) => setAllWells(event.target.checked)} />{" "}
                  Acceso a todos los pozos
                </label>
                <p className={styles.faint}>
                  {allWells
                    ? "La cuenta ve todos los pozos, incluidos los que se creen después."
                    : "La cuenta solo ve los pozos que ella misma crea. Al inicio no ve ninguno."}
                </p>
              </div>
              <details className={styles.advanced}>
                <summary>Opciones avanzadas</summary>
                <div className={styles.form}>
              <label className={styles.groupLabel}>
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
                label="Credencial (opcional)"
                htmlFor="account-credential"
                hint={`Vacía: el servidor genera una y la muestra una vez. Mínimo 15 caracteres; letras, números, punto, guion y guion bajo. Usuario y credencial juntos: máximo 57 caracteres (${Math.max(0, 56 - name.length)} para este nombre).`}
              >
                <PasswordInput
                  id="account-credential"
                  autoComplete="new-password"
                  minLength={15}
                  maxLength={Math.max(0, 56 - name.length)}
                  pattern="[A-Za-z0-9._\-]*"
                  value={credential}
                  onChange={(event) => setCredential(event.target.value)}
                />
              </Field>
              {credential ? (
                <Field label="Repetir credencial" htmlFor="account-credential-confirm">
                  <PasswordInput
                    id="account-credential-confirm"
                    autoComplete="new-password"
                    value={credentialConfirm}
                    onChange={(event) => setCredentialConfirm(event.target.value)}
                  />
                </Field>
              ) : null}
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
                </div>
              </details>
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
