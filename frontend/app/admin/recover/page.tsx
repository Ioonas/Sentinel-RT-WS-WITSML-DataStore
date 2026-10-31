"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import styles from "../auth.module.css";

export default function RecoverPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ message: string }>("/auth/recovery", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setMessage(result.message);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "No se pudo procesar la solicitud.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="recover-title">
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <div>
            <div className={styles.title} id="recover-title">
              Recuperar acceso
            </div>
            <div className={styles.subtitle}>Sentinel RT&amp;WS WITSML DataStore</div>
          </div>
        </div>

        {error ? <Alert>{error}</Alert> : null}
        {message ? (
          <div className={styles.success}>
            <Alert tone="ok">{message}</Alert>
          </div>
        ) : null}

        {!message ? (
          <form className={styles.form} onSubmit={submit}>
            <Field label="Correo de la cuenta" htmlFor="email">
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? "Enviando…" : "Solicitar enlace"}
            </Button>
          </form>
        ) : null}

        <div className={styles.links}>
          <Link href="/admin/login">Volver al inicio de sesión</Link>
        </div>
        <p className={styles.note}>
          La respuesta es siempre genérica para no permitir enumerar cuentas.
        </p>
      </section>
    </main>
  );
}
