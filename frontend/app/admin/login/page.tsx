"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, api, type SetupStatus } from "@/lib/api";
import styles from "../auth.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [setupCompleted, setSetupCompleted] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    email: "",
    password: "",
    contact_email: "",
    contact_phone: "",
    admin_name: "",
    admin_password: "",
    server_name: "",
    server_description: "",
  });

  useEffect(() => {
    api<SetupStatus>("/setup/status")
      .then((status) => setSetupCompleted(status.setup_completed))
      .catch((caught: unknown) =>
        setError(caught instanceof ApiError ? caught.message : "No se pudo consultar el estado."),
      );
  }, []);

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (setupCompleted === false) {
        await api("/setup", {
          method: "POST",
          body: JSON.stringify({
            contact_email: form.contact_email,
            contact_phone: form.contact_phone,
            admin_email: form.email,
            admin_name: form.admin_name,
            admin_password: form.admin_password,
            server_name: form.server_name || undefined,
            server_description: form.server_description || undefined,
          }),
        });
      } else {
        await api("/auth/sessions", {
          method: "POST",
          body: JSON.stringify({ email: form.email, password: form.password }),
        });
      }
      router.push("/admin/overview");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "No se pudo iniciar sesión.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <section className={styles.panel} aria-labelledby="login-title">
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <div>
            <div className={styles.title} id="login-title">
              Sentinel RT&amp;WS WITSML DataStore
            </div>
            <div className={styles.subtitle}>Administración</div>
          </div>
        </div>

        {setupCompleted === null && !error ? <p className={styles.note}>Comprobando configuración…</p> : null}

        {error ? <Alert>{error}</Alert> : null}

        <form className={styles.form} onSubmit={submit}>
          {setupCompleted === false ? (
            <>
              <Alert tone="info">
                Primer arranque: configure el contacto público y el primer superadministrador.
                El servidor exige SMTP configurado en su despliegue; si falta o no autentica, el setup se rechaza.
              </Alert>
              <div className={styles.row}>
                <Field label="Correo de contacto" htmlFor="contact-email">
                  <Input
                    id="contact-email"
                    type="email"
                    required
                    value={form.contact_email}
                    onChange={(event) => update("contact_email", event.target.value)}
                  />
                </Field>
                <Field label="Teléfono de contacto" htmlFor="contact-phone">
                  <Input
                    id="contact-phone"
                    required
                    value={form.contact_phone}
                    onChange={(event) => update("contact_phone", event.target.value)}
                  />
                </Field>
              </div>
              <div className={styles.row}>
                <Field
                  label="Nombre del servicio"
                  hint="Opcional. Por defecto: Sentinel RT&WS WITSML DataStore."
                  htmlFor="server-name"
                >
                  <Input
                    id="server-name"
                    maxLength={255}
                    value={form.server_name}
                    onChange={(event) => update("server_name", event.target.value)}
                  />
                </Field>
                <Field label="Descripción del servicio" hint="Opcional." htmlFor="server-description">
                  <Input
                    id="server-description"
                    maxLength={512}
                    value={form.server_description}
                    onChange={(event) => update("server_description", event.target.value)}
                  />
                </Field>
              </div>
              <Field label="Nombre del administrador" htmlFor="admin-name">
                <Input
                  id="admin-name"
                  required
                  value={form.admin_name}
                  onChange={(event) => update("admin_name", event.target.value)}
                />
              </Field>
              <Field label="Correo del administrador" htmlFor="email">
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={form.email}
                  onChange={(event) => update("email", event.target.value)}
                />
              </Field>
              <Field
                label="Contraseña inicial"
                hint="Mínimo 15 caracteres, con al menos un dígito."
                htmlFor="password"
              >
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={15}
                  value={form.admin_password}
                  onChange={(event) => update("admin_password", event.target.value)}
                />
              </Field>
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "Configurando…" : "Completar configuración"}
              </Button>
            </>
          ) : setupCompleted ? (
            <>
              <Field label="Correo" htmlFor="email">
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={form.email}
                  onChange={(event) => update("email", event.target.value)}
                />
              </Field>
              <Field label="Contraseña" htmlFor="password">
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={form.password}
                  onChange={(event) => update("password", event.target.value)}
                />
              </Field>
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "Ingresando…" : "Iniciar sesión"}
              </Button>
            </>
          ) : null}
        </form>

        {setupCompleted ? (
          <div className={styles.links}>
            <Link href="/admin/recover">Recuperar acceso</Link>
            <Link href="/admin/accept-invitation">Aceptar invitación</Link>
          </div>
        ) : null}
        <p className={styles.note}>
          Los mensajes de credenciales son genéricos y no confirman la existencia de cuentas.
        </p>
      </section>
    </main>
  );
}
