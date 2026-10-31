"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, api, type UserView } from "@/lib/api";
import styles from "../auth.module.css";

export default function AcceptInvitationPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [created, setCreated] = useState<UserView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get("token") ?? "");
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api<UserView>("/invitations/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          password,
          display_name: displayName || null,
        }),
      });
      setCreated(user);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "No se pudo aceptar la invitación.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="invite-title">
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <div>
            <div className={styles.title} id="invite-title">
              Aceptar invitación
            </div>
            <div className={styles.subtitle}>Sentinel RT&amp;WS WITSML DataStore</div>
          </div>
        </div>

        {error ? <Alert>{error}</Alert> : null}
        {created ? (
          <div className={styles.success}>
            <Alert tone="ok">
              Cuenta creada para <strong>{created.email}</strong>. Ya puede iniciar sesión.
            </Alert>
          </div>
        ) : null}

        {!created && !token ? (
          <p className={styles.note}>El enlace no contiene un token de invitación válido.</p>
        ) : null}

        {!created && token ? (
          <form className={styles.form} onSubmit={submit}>
            <Field label="Nombre visible" htmlFor="display-name">
              <Input
                id="display-name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </Field>
            <Field
              label="Contraseña inicial"
              hint="Mínimo 12 caracteres, con mayúsculas, minúsculas y dígitos."
              htmlFor="password"
            >
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? "Creando cuenta…" : "Aceptar invitación"}
            </Button>
          </form>
        ) : null}

        <div className={styles.links}>
          <Link href="/admin/login">Ir al inicio de sesión</Link>
        </div>
      </section>
    </main>
  );
}
