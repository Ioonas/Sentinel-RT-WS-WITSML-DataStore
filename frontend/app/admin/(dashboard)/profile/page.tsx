"use client";

import { permissionLabel } from "@/lib/permissions";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, PageHeader, Spinner, StatusBadge, PasswordInput } from "@/components/ui";
import { EmptyRow, Section, Tags } from "@/components/dashboard";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ApiError, api, type MessageView, type ProfileSessionView, type SessionView } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

export default function ProfilePage() {
  const router = useRouter();
  const { data, error, loading } = useApiQuery<SessionView>("/profile");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const sessions = useApiQuery<ProfileSessionView[]>("/profile/sessions");
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);
  const [confirmingSession, setConfirmingSession] = useState<{
    title: string;
    description: string;
    confirmLabel: string;
    run: () => Promise<void>;
  } | null>(null);
  const otherSessions = (sessions.data ?? []).filter((item) => !item.current);

  const user = data?.user;

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setFormError("La confirmación no coincide con la nueva contraseña.");
      return;
    }
    setBusy(true);
    setFormError(null);
    setMessage(null);
    try {
      const result = await api<MessageView>("/profile/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setMessage(result.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      window.setTimeout(() => {
        router.push("/admin/login");
        router.refresh();
      }, 2200);
    } catch (caught) {
      setFormError(caught instanceof ApiError ? caught.message : "No se pudo cambiar la contraseña.");
    } finally {
      setBusy(false);
    }
  }

  async function closeSession(reference: string) {
    setSessionBusy(true);
    setSessionError(null);
    setSessionMessage(null);
    try {
      await api(`/profile/sessions/${reference}`, { method: "DELETE" });
      setSessionMessage("Sesión cerrada. Se envió un aviso a su correo.");
      sessions.reload();
    } catch (caught) {
      setSessionError(caught instanceof ApiError ? caught.message : "No se pudo cerrar la sesión.");
    } finally {
      setSessionBusy(false);
    }
  }

  async function closeOtherSessions() {
    setSessionBusy(true);
    setSessionError(null);
    setSessionMessage(null);
    try {
      const result = await api<MessageView>("/profile/sessions/revoke-others", { method: "POST" });
      setSessionMessage(result.message);
      sessions.reload();
    } catch (caught) {
      setSessionError(caught instanceof ApiError ? caught.message : "No se pudieron cerrar las sesiones.");
    } finally {
      setSessionBusy(false);
    }
  }

  function askCloseSession(reference: string) {
    setConfirmingSession({
      title: "Cerrar sesión",
      description: "Esa sesión dejará de funcionar de inmediato. Se enviará un aviso a su correo.",
      confirmLabel: "Cerrar esa sesión",
      run: () => closeSession(reference),
    });
  }

  function askCloseOtherSessions() {
    setConfirmingSession({
      title: "Cerrar las demás sesiones",
      description: `Se cerrarán ${otherSessions.length} sesión(es) activa(s) excepto esta. Se enviará un aviso a su correo.`,
      confirmLabel: "Cerrar las demás",
      run: closeOtherSessions,
    });
  }

  function runConfirmedSession() {
    const request = confirmingSession;
    // Se cierra primero para no apilar la confirmación con la reautenticación.
    setConfirmingSession(null);
    void request?.run();
  }

  async function logout() {
    try {
      await api("/auth/sessions", { method: "DELETE" });
    } catch (caught) {
      if (!(caught instanceof ApiError)) throw caught;
    } finally {
      router.push("/admin/login");
      router.refresh();
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Mi cuenta"
        description="Datos de la sesión actual y cambio de contraseña."
        actions={
          <Button variant="secondary" onClick={logout}>
            Cerrar sesión
          </Button>
        }
      />

      {error ? <Alert>{error.message}</Alert> : null}
      {loading ? <Spinner /> : null}

      {user ? (
        <div className={styles.split}>
          <Card>
            <Section title="Perfil">
              <dl className={styles.detailsGrid}>
                <dt>Nombre</dt>
                <dd>{user.display_name}</dd>
                <dt>Correo</dt>
                <dd>{user.email}</dd>
                <dt>Rol</dt>
                <dd>{user.role}</dd>
                <dt>Estado</dt>
                <dd>
                  <StatusBadge status={user.enabled ? "ok" : "danger"} label={user.enabled ? "Activo" : "Deshabilitado"} />
                </dd>
                <dt>Creado</dt>
                <dd>{formatDateTime(user.created_at)}</dd>
                <dt>Último acceso</dt>
                <dd>{formatDateTime(user.last_login_at)}</dd>
                <dt>Sesión vence</dt>
                <dd>{formatDateTime(data?.expires_at)}</dd>
              </dl>
              <div style={{ marginTop: "var(--space-4)" }}>
                <span className={styles.statLabel}>Permisos</span>
                <Tags values={user.permissions.map(permissionLabel)} />
              </div>
            </Section>
          </Card>

          <Card>
            <Section
              title="Cambiar contraseña"
              description="Al cambiarla se cerrarán las sesiones y deberá iniciar sesión de nuevo."
            >
              {message ? <Alert tone="ok">{message}</Alert> : null}
              {formError ? <Alert>{formError}</Alert> : null}
              <form className={styles.form} onSubmit={changePassword}>
                <Field label="Contraseña actual" htmlFor="current-password">
                  <PasswordInput
                    id="current-password"
                    autoComplete="current-password"
                    required
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                  />
                </Field>
                <Field
                  label="Nueva contraseña"
                  hint="Mínimo 15 caracteres."
                  htmlFor="new-password"
                >
                  <PasswordInput
                    id="new-password"
                    autoComplete="new-password"
                    minLength={15}
                    required
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </Field>
                <Field label="Confirmar nueva contraseña" htmlFor="confirm-password">
                  <PasswordInput
                    id="confirm-password"
                    autoComplete="new-password"
                    minLength={15}
                    required
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </Field>
                <Button type="submit" variant="primary" disabled={busy}>
                  {busy ? "Guardando…" : "Cambiar contraseña"}
                </Button>
              </form>
            </Section>
          </Card>
        </div>
      ) : null}

      <Card>
        <Section
          title="Sesiones activas"
          description="Sesiones abiertas con esta cuenta. Al cerrar otras sesiones se le avisa por correo."
          actions={
            <Button size="sm" variant="ghost" onClick={sessions.reload}>
              Actualizar
            </Button>
          }
        >
          {sessionError ? <Alert>{sessionError}</Alert> : null}
          {sessionMessage ? <Alert tone="ok">{sessionMessage}</Alert> : null}
          {sessions.loading ? (
            <Spinner />
          ) : sessions.error ? (
            <Alert>{sessions.error.message}</Alert>
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
                    {sessions.data && sessions.data.length > 0 ? (
                      sessions.data.map((item) => (
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
                              <span className={styles.faint}>—</span>
                            ) : (
                              <Button
                                size="sm"
                                variant="danger"
                                disabled={sessionBusy}
                                onClick={() => askCloseSession(item.reference)}
                              >
                                Cerrar
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={5}>No hay sesiones activas.</EmptyRow>
                    )}
                  </tbody>
                </table>
              </div>
              <div className={styles.actions} style={{ marginTop: "var(--space-4)" }}>
                <Button
                  variant="danger"
                  disabled={sessionBusy || otherSessions.length === 0}
                  onClick={askCloseOtherSessions}
                >
                  Cerrar las demás sesiones
                </Button>
              </div>
            </>
          )}
        </Section>
      </Card>

      {confirmingSession ? (
        <ConfirmDialog
          title={confirmingSession.title}
          description={confirmingSession.description}
          confirmLabel={confirmingSession.confirmLabel}
          tone="danger"
          busy={sessionBusy}
          onConfirm={runConfirmedSession}
          onCancel={() => setConfirmingSession(null)}
        />
      ) : null}
    </div>
  );
}
