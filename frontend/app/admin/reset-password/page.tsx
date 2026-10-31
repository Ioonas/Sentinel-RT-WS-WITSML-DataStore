"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import styles from "../auth.module.css";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
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
      const result = await api<{ message: string }>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "No se pudo restablecer la contraseña.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="reset-title">
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <div>
            <div className={styles.title} id="reset-title">
              Restablecer contraseña
            </div>
            <div className={styles.subtitle}>Enlace de un solo uso</div>
          </div>
        </div>

        {error ? <Alert>{error}</Alert> : null}
        {message ? (
          <div className={styles.success}>
            <Alert tone="ok">{message}</Alert>
          </div>
        ) : null}

        {!message && !token ? (
          <p className={styles.note}>El enlace no contiene un token válido.</p>
        ) : null}

        {!message && token ? (
          <form className={styles.form} onSubmit={submit}>
            <Field
              label="Nueva contraseña"
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
              {busy ? "Guardando…" : "Guardar contraseña"}
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
