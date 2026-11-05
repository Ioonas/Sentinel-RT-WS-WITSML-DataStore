"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Spinner,
  StatusBadge,
} from "@/components/ui";
import { Section, Tags } from "@/components/dashboard";
import { ApiError, api, type MessageView, type SessionView } from "@/lib/api";
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
                <Tags values={user.permissions} />
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
                  <Input
                    id="current-password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                  />
                </Field>
                <Field
                  label="Nueva contraseña"
                  hint="Mínimo 15 caracteres, con al menos un dígito."
                  htmlFor="new-password"
                >
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={15}
                    required
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </Field>
                <Field label="Confirmar nueva contraseña" htmlFor="confirm-password">
                  <Input
                    id="confirm-password"
                    type="password"
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
    </div>
  );
}
