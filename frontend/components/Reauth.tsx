"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import styles from "./Reauth.module.css";

type ReauthContextValue = {
  runWithReauth: <T>(action: () => Promise<T>) => Promise<T>;
};

const ReauthContext = createContext<ReauthContextValue | null>(null);

/**
 * Ejecuta una operación sensible. Si el servidor responde `reauth_required`,
 * pide la contraseña, renueva la ventana de reautenticación y reintenta una vez.
 */
export function ReauthProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef<((ok: boolean) => void) | null>(null);

  const askPassword = useCallback(
    () =>
      new Promise<boolean>((resolve) => {
        pending.current = resolve;
        setPassword("");
        setError(null);
        setOpen(true);
      }),
    [],
  );

  const runWithReauth = useCallback(
    async function run<T>(action: () => Promise<T>): Promise<T> {
      try {
        return await action();
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.code !== "reauth_required") {
          throw caught;
        }
        const confirmed = await askPassword();
        if (!confirmed) throw caught;
        return action();
      }
    },
    [askPassword],
  );

  function finish(ok: boolean) {
    setOpen(false);
    pending.current?.(ok);
    pending.current = null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/reauthentication", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      finish(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "No se pudo reautenticar.");
    } finally {
      setBusy(false);
    }
  }

  const value = useMemo(() => ({ runWithReauth }), [runWithReauth]);

  return (
    <ReauthContext.Provider value={value}>
      {children}
      {open ? (
        <div className={styles.overlay} role="presentation">
          <form
            className={styles.dialog}
            role="dialog"
            aria-modal="true"
            aria-labelledby="reauth-title"
            onSubmit={submit}
          >
            <h2 id="reauth-title" className={styles.title}>
              Confirme su contraseña
            </h2>
            <p className={styles.text}>Esta operación requiere reautenticación reciente.</p>
            {error ? <Alert tone="danger">{error}</Alert> : null}
            <Field label="Contraseña" htmlFor="reauth-password">
              <Input
                id="reauth-password"
                type="password"
                autoComplete="current-password"
                required
                autoFocus
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <div className={styles.actions}>
              <Button type="button" variant="ghost" onClick={() => finish(false)}>
                Cancelar
              </Button>
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "Confirmando…" : "Confirmar"}
              </Button>
            </div>
          </form>
        </div>
      ) : null}
    </ReauthContext.Provider>
  );
}

export function useReauth(): ReauthContextValue {
  const context = useContext(ReauthContext);
  if (!context) throw new Error("useReauth requiere ReauthProvider.");
  return context;
}
