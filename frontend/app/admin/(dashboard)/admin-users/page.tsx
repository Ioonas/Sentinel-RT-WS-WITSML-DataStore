"use client";

import { useEffect, useState, type FormEvent } from "react";
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
  type PermissionView,
  type UserView,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import { useReauth } from "@/components/Reauth";
import styles from "../dashboard.module.css";

const HUMAN_ROLES = [
  { value: "superadministrador", label: "Superadministrador" },
  { value: "administrador", label: "Administrador (permisos delegados)" },
  { value: "auditor", label: "Auditor" },
  { value: "operador", label: "Operador" },
  { value: "administrador_seguridad", label: "Administrador de seguridad" },
];

export default function AdminUsersPage() {
  const { runWithReauth } = useReauth();
  const users = useApiQuery<UserView[]>("/admin-users");
  const permissions = useApiQuery<PermissionView[]>("/permissions");
  const pendingInvitations = useApiQuery<InvitationSummaryView[]>("/invitations");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("auditor");
  const [invitePermissions, setInvitePermissions] = useState<string[]>([]);
  const [invitation, setInvitation] = useState<InvitationView | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteBusy, setInviteBusy] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState("auditor");
  const [editName, setEditName] = useState("");
  const [editEnabled, setEditEnabled] = useState(true);
  const [editPermissions, setEditPermissions] = useState<string[]>([]);
  const [editError, setEditError] = useState<string | null>(null);
  const [editBusy, setEditBusy] = useState(false);

  const selected = users.data?.find((user) => user.id === selectedId) ?? null;
  const permissionNames = (permissions.data ?? []).map((item) => item.name);

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
      const result = await api<InvitationView>("/invitations", {
        method: "POST",
        body: JSON.stringify({
          email: inviteEmail,
          role: inviteRole,
          permissions: inviteRole === "administrador" ? invitePermissions : null,
        }),
      });
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
          Invitación creada para <strong>{invitation.email}</strong> (vence {formatDateTime(invitation.expires_at)}).
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
                          <td>{user.role}</td>
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
          <Section title="Invitar usuario" description="El enlace de invitación vence automáticamente.">
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
                  <span className={styles.statLabel}>Permisos delegados</span>
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
          </Section>
        </Card>
      </div>

      <Card>
        <Section
          title="Invitaciones pendientes"
          description="Invitaciones no aceptadas y no vencidas. Los enlaces no se vuelven a mostrar; para reenviar, cree una nueva invitación."
          actions={
            <Button size="sm" variant="ghost" onClick={() => pendingInvitations.reload()}>
              Actualizar
            </Button>
          }
        >
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
                    <th>Creada</th>
                    <th>Vence</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingInvitations.data && pendingInvitations.data.length > 0 ? (
                    pendingInvitations.data.map((item) => (
                      <tr key={item.id}>
                        <td className={styles.wrap}>{item.email}</td>
                        <td>{item.role}</td>
                        <td className={styles.faint}>{formatDateTime(item.created_at)}</td>
                        <td className={styles.faint}>{formatDateTime(item.expires_at)}</td>
                      </tr>
                    ))
                  ) : (
                    <EmptyRow colSpan={4}>No hay invitaciones pendientes.</EmptyRow>
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
                    onChange={(event) => setEditRole(event.target.value)}
                  >
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
                <span className={styles.statLabel}>Permisos efectivos</span>
                <Tags values={selected.permissions} />
              </div>
              {editRole === "administrador" ? (
                <div>
                  <span className={styles.statLabel}>Permisos delegados</span>
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
    </div>
  );
}
