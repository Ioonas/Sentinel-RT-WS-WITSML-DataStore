"use client";

import { permissionLabel } from "@/lib/permissions";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
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
import { EmptyRow, PermissionChecks, Section, Tags } from "@/components/dashboard";
import {
  ApiError,
  api,
  type InvitationSummaryView,
  type InvitationView,
  type MessageView,
  type PermissionView,
  type ProfileSessionView,
  type UserView,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useReauth } from "@/components/Reauth";
import styles from "../dashboard.module.css";

const HUMAN_ROLES = [
  { value: "superadministrador", label: "Superadministrador" },
  { value: "administrador", label: "Administrador (permisos delegados)" },
  { value: "auditor", label: "Auditor" },
  { value: "operador", label: "Operador" },
  { value: "administrador_seguridad", label: "Administrador de seguridad" },
];

/** Rol que solo se asigna al dar acceso web vinculado (no se elige en invitaciones). */
const LINKED_ROLE = { value: "lector_vinculado", label: "Lector vinculado (cuenta de servicio)" };

/** Nombre visible de un rol; si el valor no está en el catálogo se muestra tal cual. */
function roleLabel(value: string) {
  return [...HUMAN_ROLES, LINKED_ROLE].find((item) => item.value === value)?.label ?? value;
}

type ConfirmRequest = {
  title: string;
  description: string;
  confirmLabel: string;
  run: () => Promise<void>;
};

const INVITATION_EXPIRED = (expiresAt: string) => new Date(expiresAt).getTime() <= Date.now();

export default function AdminUsersPage() {
  const { runWithReauth } = useReauth();
  const users = useApiQuery<UserView[]>("/admin-users");
  const permissions = useApiQuery<PermissionView[]>("/permissions");
  const pendingInvitations = useApiQuery<InvitationSummaryView[]>("/invitations");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("auditor");
  const [invitePermissions, setInvitePermissions] = useState<string[]>([]);
  const [accountKind, setAccountKind] = useState<"persona" | "servicio">("persona");
  const [invitation, setInvitation] = useState<InvitationView | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteBusy, setInviteBusy] = useState(false);
  const [actingInvitationId, setActingInvitationId] = useState<string | null>(null);
  const [invitationActionError, setInvitationActionError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<ConfirmRequest | null>(null);
  const [userSessionBusy, setUserSessionBusy] = useState(false);
  const [userSessionError, setUserSessionError] = useState<string | null>(null);
  const [userSessionMessage, setUserSessionMessage] = useState<string | null>(null);
  const [confirmingUserSession, setConfirmingUserSession] = useState<ConfirmRequest | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState("auditor");
  const [editName, setEditName] = useState("");
  const [editEnabled, setEditEnabled] = useState(true);
  const [editPermissions, setEditPermissions] = useState<string[]>([]);
  const [editError, setEditError] = useState<string | null>(null);
  const [editBusy, setEditBusy] = useState(false);

  const selected = users.data?.find((user) => user.id === selectedId) ?? null;
  const permissionNames = (permissions.data ?? []).map((item) => item.name);
  const userSessions = useApiQuery<ProfileSessionView[]>(
    selected ? `/admin-users/${selected.id}/sessions` : null,
  );

  useEffect(() => {
    if (!selected) return;
    setEditRole(selected.role);
    setEditName(selected.display_name);
    setEditEnabled(selected.enabled);
    setEditPermissions(selected.permissions);
    setEditError(null);
  }, [selected]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    setInviteBusy(true);
    setInviteError(null);
    setInvitation(null);
    try {
      const result = await runWithReauth(() =>
        api<InvitationView>("/invitations", {
          method: "POST",
          body: JSON.stringify({
            email: inviteEmail,
            role: inviteRole,
            permissions: inviteRole === "administrador" ? invitePermissions : null,
          }),
        }),
      );
      setInvitation(result);
      setInviteEmail("");
      setInvitePermissions([]);
      users.reload();
      pendingInvitations.reload();
    } catch (caught) {
      setInviteError(caught instanceof ApiError ? caught.message : "No se pudo crear la invitación.");
    } finally {
      setInviteBusy(false);
    }
  }

  function describeActionError(caught: unknown, fallback: string, reauthMessage: string): string {
    if (caught instanceof ApiError) {
      return caught.code === "reauth_required" ? reauthMessage : caught.message;
    }
    return fallback;
  }

  async function resendInvitation(item: InvitationSummaryView) {
    setActingInvitationId(item.id);
    setInvitationActionError(null);
    try {
      const result = await runWithReauth(() =>
        api<InvitationView>(`/invitations/${item.id}/resend`, { method: "POST" }),
      );
      setInvitation(result);
      pendingInvitations.reload();
    } catch (caught) {
      setInvitationActionError(
        describeActionError(
          caught,
          "No se pudo reenviar la invitación.",
          "La invitación no se reenvió. Confirme su contraseña para continuar.",
        ),
      );
    } finally {
      setActingInvitationId(null);
    }
  }

  async function revokeInvitation(item: InvitationSummaryView) {
    setActingInvitationId(item.id);
    setInvitationActionError(null);
    try {
      await runWithReauth(() => api(`/invitations/${item.id}/revoke`, { method: "POST" }));
      pendingInvitations.reload();
    } catch (caught) {
      setInvitationActionError(
        describeActionError(
          caught,
          "No se pudo cancelar la invitación.",
          "La invitación no se canceló. Confirme su contraseña para continuar.",
        ),
      );
    } finally {
      setActingInvitationId(null);
    }
  }

  function askCancelInvitation(item: InvitationSummaryView) {
    setConfirming({
      title: "Cancelar invitación",
      description: `El enlace enviado a ${item.email} dejará de aceptarse. Si necesita invitarlo de nuevo, cree una invitación nueva.`,
      confirmLabel: "Cancelar invitación",
      run: () => revokeInvitation(item),
    });
  }

  function runConfirmed() {
    const request = confirming;
    // Se cierra primero para que la reautenticación no quede apilada sobre la confirmación.
    setConfirming(null);
    void request?.run();
  }

  async function closeUserSession(reference: string) {
    if (!selected) return;
    setUserSessionBusy(true);
    setUserSessionError(null);
    setUserSessionMessage(null);
    try {
      await runWithReauth(() =>
        api(`/admin-users/${selected.id}/sessions/${reference}`, { method: "DELETE" }),
      );
      setUserSessionMessage("Sesión cerrada. Se avisó al usuario por correo.");
      userSessions.reload();
    } catch (caught) {
      setUserSessionError(
        describeActionError(
          caught,
          "No se pudo cerrar la sesión.",
          "La sesión no se cerró. Confirme su contraseña para continuar.",
        ),
      );
    } finally {
      setUserSessionBusy(false);
    }
  }

  async function closeAllUserSessions() {
    if (!selected) return;
    setUserSessionBusy(true);
    setUserSessionError(null);
    setUserSessionMessage(null);
    try {
      const result = await runWithReauth(() =>
        api<MessageView>(`/admin-users/${selected.id}/sessions/revoke-all`, { method: "POST" }),
      );
      setUserSessionMessage(result.message);
      userSessions.reload();
    } catch (caught) {
      setUserSessionError(
        describeActionError(
          caught,
          "No se pudieron cerrar las sesiones.",
          "Las sesiones no se cerraron. Confirme su contraseña para continuar.",
        ),
      );
    } finally {
      setUserSessionBusy(false);
    }
  }

  function askCloseUserSession(reference: string) {
    setConfirmingUserSession({
      title: "Cerrar sesión del usuario",
      description: `La sesión de ${selected?.email ?? "este usuario"} dejará de funcionar de inmediato. Se le avisará por correo.`,
      confirmLabel: "Cerrar sesión",
      run: () => closeUserSession(reference),
    });
  }

  function askCloseAllUserSessions() {
    const count = (userSessions.data ?? []).filter((item) => !item.current).length;
    setConfirmingUserSession({
      title: "Cerrar todas las sesiones",
      description: `Se cerrarán ${count} sesión(es) de ${selected?.email ?? "este usuario"}. Se le avisará por correo.`,
      confirmLabel: "Cerrar todas",
      run: closeAllUserSessions,
    });
  }

  function runConfirmedUserSession() {
    const request = confirmingUserSession;
    // Se cierra primero para no apilar la confirmación con la reautenticación.
    setConfirmingUserSession(null);
    void request?.run();
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setEditBusy(true);
    setEditError(null);
    try {
      await runWithReauth(() =>
        api<UserView>(`/admin-users/${selected.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            enabled: editEnabled,
            role: editRole,
            display_name: editName,
            permissions: editRole === "administrador" ? editPermissions : null,
          }),
        }),
      );
      users.reload();
    } catch (caught) {
      setEditError(caught instanceof ApiError ? caught.message : "No se pudo actualizar el usuario.");
    } finally {
      setEditBusy(false);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Usuarios administrativos"
        description="Cuentas humanas con roles fijos o permisos delegados. Las invitaciones son de un solo uso."
        actions={<StatusBadge status="neutral" label={`${users.data?.length ?? 0} usuarios`} />}
      />

      {users.error ? <Alert>{users.error.message}</Alert> : null}

      {invitation ? (
        <Alert tone="ok">
          Invitación generada para <strong>{invitation.email}</strong> (vence {formatDateTime(invitation.expires_at)}).
          {invitation.token ? (
            <>
              {" "}Enlace de desarrollo:{" "}
              <a href={`/admin/accept-invitation?token=${encodeURIComponent(invitation.token)}`}>
                aceptar invitación
              </a>
              <code className={styles.secret}>{invitation.token}</code>
            </>
          ) : (
            " Se envió por correo."
          )}
        </Alert>
      ) : null}

      <div className={styles.split}>
        <Card>
          <Section
            title="Cuentas"
            description="Seleccione una cuenta para editar su rol, estado y permisos delegados."
            actions={<Button size="sm" variant="ghost" onClick={users.reload}>Actualizar</Button>}
          >
            {users.loading ? (
              <Spinner />
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Correo</th>
                      <th>Rol</th>
                      <th>Estado</th>
                      <th>Último acceso</th>
                      <th>Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.data && users.data.length > 0 ? (
                      users.data.map((user) => (
                        <tr key={user.id}>
                          <td>
                            <strong>{user.display_name}</strong>
                            {user.must_change_password ? (
                              <div className={styles.faint}>Debe cambiar contraseña</div>
                            ) : null}
                          </td>
                          <td className={styles.wrap}>{user.email}</td>
                          <td>{roleLabel(user.role)}</td>
                          <td>
                            <StatusBadge
                              status={user.enabled ? "ok" : "danger"}
                              label={user.enabled ? "Activo" : "Deshabilitado"}
                            />
                          </td>
                          <td className={styles.faint}>{formatDateTime(user.last_login_at)}</td>
                          <td>
                            <Button size="sm" onClick={() => setSelectedId(user.id)}>
                              Editar
                            </Button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={6}>No hay usuarios administrativos.</EmptyRow>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </Card>

        <Card>
          <Section
            title="Nueva cuenta"
            description={
              accountKind === "persona"
                ? "Se envía una invitación por correo. El enlace vence automáticamente."
                : "Las cuentas de servicio las usan programas, no personas."
            }
          >
            <fieldset className={styles.form} style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className={styles.groupLabel}>Tipo de cuenta</legend>
              <label className={styles.faint} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="radio"
                  name="account-kind"
                  checked={accountKind === "persona"}
                  onChange={() => setAccountKind("persona")}
                />
                Persona (entra a la aplicación web)
              </label>
              <label className={styles.faint} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="radio"
                  name="account-kind"
                  checked={accountKind === "servicio"}
                  onChange={() => setAccountKind("servicio")}
                />
                Cuenta de servicio (usa un programa)
              </label>
            </fieldset>
            {accountKind === "servicio" ? (
              <div className={styles.form}>
                <p className={styles.faint}>
                  Se crean en su propia pantalla, donde se define el acceso y la credencial.
                </p>
                <div className={styles.actions}>
                  <Link href="/admin/service-accounts" className={styles.quickLink}>
                    Ir a cuentas de servicio
                  </Link>
                </div>
              </div>
            ) : null}
            {accountKind === "persona" ? (
            <>
            {inviteError ? <Alert>{inviteError}</Alert> : null}
            <form className={styles.form} onSubmit={invite}>
              <Field label="Correo" htmlFor="invite-email">
                <Input
                  id="invite-email"
                  type="email"
                  required
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                />
              </Field>
              <Field label="Rol" htmlFor="invite-role">
                <Select
                  id="invite-role"
                  value={inviteRole}
                  onChange={(event) => setInviteRole(event.target.value)}
                >
                  {HUMAN_ROLES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </Field>
              {inviteRole === "administrador" ? (
                <div>
                  <span className={styles.groupLabel}>Permisos delegados</span>
                  <PermissionChecks
                    options={permissionNames}
                    selected={invitePermissions}
                    onChange={setInvitePermissions}
                  />
                </div>
              ) : null}
              <Button type="submit" variant="primary" disabled={inviteBusy}>
                {inviteBusy ? "Invitando…" : "Crear invitación"}
              </Button>
            </form>
            </>
            ) : null}
          </Section>
        </Card>
      </div>

      <Card>
        <Section
          title="Invitaciones pendientes"
          description="Invitaciones no aceptadas ni canceladas. Reenviar genera un enlace nuevo e invalida el anterior."
          actions={
            <Button size="sm" variant="ghost" onClick={() => pendingInvitations.reload()}>
              Actualizar
            </Button>
          }
        >
          {invitationActionError ? <Alert>{invitationActionError}</Alert> : null}
          {pendingInvitations.loading ? (
            <Spinner />
          ) : pendingInvitations.error ? (
            <Alert>{pendingInvitations.error.message}</Alert>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Correo</th>
                    <th>Rol</th>
                    <th>Estado</th>
                    <th>Creada</th>
                    <th>Vence</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingInvitations.data && pendingInvitations.data.length > 0 ? (
                    pendingInvitations.data.map((item) => {
                      const expired = INVITATION_EXPIRED(item.expires_at);
                      const acting = actingInvitationId === item.id;
                      return (
                        <tr key={item.id}>
                          <td className={styles.wrap}>{item.email}</td>
                          <td>{roleLabel(item.role)}</td>
                          <td>
                            <StatusBadge
                              status={expired ? "danger" : "neutral"}
                              label={expired ? "Vencida" : "Pendiente"}
                            />
                          </td>
                          <td className={styles.faint}>{formatDateTime(item.created_at)}</td>
                          <td className={styles.faint}>{formatDateTime(item.expires_at)}</td>
                          <td>
                            <div className={styles.actions}>
                              <Button
                                size="sm"
                                onClick={() => void resendInvitation(item)}
                                disabled={actingInvitationId !== null}
                              >
                                {acting ? "Reenviando…" : "Reenviar"}
                              </Button>
                              <Button
                                size="sm"
                                variant="danger"
                                onClick={() => askCancelInvitation(item)}
                                disabled={actingInvitationId !== null}
                              >
                                Cancelar invitación
                              </Button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <EmptyRow colSpan={6}>No hay invitaciones pendientes.</EmptyRow>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </Card>

      {selected ? (
        <Card>
          <Section
            title={`Editar ${selected.email}`}
            description="Los cambios de rol o estado requieren autenticación reciente y quedan auditados."
            actions={
              <Button size="sm" variant="ghost" onClick={() => setSelectedId(null)}>
                Cerrar
              </Button>
            }
          >
            {editError ? <Alert>{editError}</Alert> : null}
            <form className={styles.form} onSubmit={save}>
              <div className={styles.formRow}>
                <Field label="Nombre visible" htmlFor="edit-name">
                  <Input
                    id="edit-name"
                    maxLength={255}
                    value={editName}
                    onChange={(event) => setEditName(event.target.value)}
                  />
                </Field>
                <Field label="Rol" htmlFor="edit-role">
                  <Select
                    id="edit-role"
                    value={editRole}
                    disabled={editRole === LINKED_ROLE.value}
                    onChange={(event) => setEditRole(event.target.value)}
                  >
                    {editRole === LINKED_ROLE.value ? (
                      <option value={LINKED_ROLE.value}>{LINKED_ROLE.label}</option>
                    ) : null}
                    {HUMAN_ROLES.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Estado" htmlFor="edit-enabled">
                  <Select
                    id="edit-enabled"
                    value={editEnabled ? "enabled" : "disabled"}
                    onChange={(event) => setEditEnabled(event.target.value === "enabled")}
                  >
                    <option value="enabled">Activo</option>
                    <option value="disabled">Deshabilitado</option>
                  </Select>
                </Field>
              </div>
              <div>
                <span className={styles.groupLabel}>Permisos efectivos</span>
                <Tags values={selected.permissions.map(permissionLabel)} />
              </div>
              {editRole === "administrador" ? (
                <div>
                  <span className={styles.groupLabel}>Permisos delegados</span>
                  <PermissionChecks
                    options={permissionNames}
                    selected={editPermissions}
                    onChange={setEditPermissions}
                  />
                </div>
              ) : null}
              <div className={styles.actions}>
                <Button type="submit" variant="primary" disabled={editBusy}>
                  {editBusy ? "Guardando…" : "Guardar cambios"}
                </Button>
              </div>
            </form>
          </Section>
        </Card>
      ) : null}

      {selected ? (
        <Card>
          <Section
            title="Sesiones activas"
            description={`Sesiones abiertas de ${selected.email}. Cerrarlas requiere reautenticación; se avisa al usuario por correo y queda auditado.`}
            actions={
              <Button size="sm" variant="ghost" onClick={userSessions.reload}>
                Actualizar
              </Button>
            }
          >
            {userSessionError ? <Alert>{userSessionError}</Alert> : null}
            {userSessionMessage ? <Alert tone="ok">{userSessionMessage}</Alert> : null}
            {userSessions.loading ? (
              <Spinner />
            ) : userSessions.error ? (
              <Alert>{userSessions.error.message}</Alert>
            ) : (
              <>
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Iniciada</th>
                        <th>Última autenticación</th>
                        <th>Vence</th>
                        <th>Estado</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {userSessions.data && userSessions.data.length > 0 ? (
                        userSessions.data.map((item) => (
                          <tr key={item.reference}>
                            <td className={styles.faint}>{formatDateTime(item.created_at)}</td>
                            <td className={styles.faint}>{formatDateTime(item.authenticated_at)}</td>
                            <td className={styles.faint}>{formatDateTime(item.expires_at)}</td>
                            <td>
                              <StatusBadge
                                status={item.current ? "ok" : "neutral"}
                                label={item.current ? "Esta sesión" : "Activa"}
                              />
                            </td>
                            <td>
                              {item.current ? (
                                <span className={styles.faint}>Use «Cerrar sesión» en su perfil</span>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="danger"
                                  disabled={userSessionBusy}
                                  onClick={() => askCloseUserSession(item.reference)}
                                >
                                  Cerrar
                                </Button>
                              )}
                            </td>
                          </tr>
                        ))
                      ) : (
                        <EmptyRow colSpan={5}>Sin sesiones activas.</EmptyRow>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className={styles.actions} style={{ marginTop: "var(--space-4)" }}>
                  <Button
                    variant="danger"
                    disabled={
                      userSessionBusy ||
                      !(userSessions.data ?? []).some((item) => !item.current)
                    }
                    onClick={askCloseAllUserSessions}
                  >
                    Cerrar todas las sesiones
                  </Button>
                </div>
              </>
            )}
          </Section>
        </Card>
      ) : null}

      {confirmingUserSession ? (
        <ConfirmDialog
          title={confirmingUserSession.title}
          description={confirmingUserSession.description}
          confirmLabel={confirmingUserSession.confirmLabel}
          tone="danger"
          busy={userSessionBusy}
          onConfirm={runConfirmedUserSession}
          onCancel={() => setConfirmingUserSession(null)}
        />
      ) : null}

      {confirming ? (
        <ConfirmDialog
          title={confirming.title}
          description={confirming.description}
          confirmLabel={confirming.confirmLabel}
          tone="danger"
          busy={actingInvitationId !== null}
          onConfirm={runConfirmed}
          onCancel={() => setConfirming(null)}
        />
      ) : null}
    </div>
  );
}
