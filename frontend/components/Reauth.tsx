"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Alert, Button, Field, PasswordInput } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import styles from "./Reauth.module.css";

type ReauthContextValue = {
  runWithReauth: <T>(action: () => Promise<T>) => Promise<T>;
};

const ReauthContext = createContext<ReauthContextValue | null>(null);

// El botón que abrió el diálogo puede seguir deshabilitado mientras la operación termina;
// se reintenta hasta que vuelva a estar disponible para no perder el foco.
function restoreFocus(element: HTMLElement | null, attempts = 20): void {
  if (!element) return;
  if (!element.isConnected) return;
  if ((element as HTMLButtonElement).disabled) {
    if (attempts > 0) setTimeout(() => restoreFocus(element, attempts - 1), 25);
    return;
  }
  element.focus();
}

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
  const dialogRef = useRef<HTMLFormElement | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const askPassword = useCallback(
    (origin: HTMLElement | null) =>
      new Promise<boolean>((resolve) => {
        pending.current = resolve;
        // Recordar quién tenía el foco para devolverlo al cerrar (ui-spec §9).
        // Devolver el foco a quien inició la acción (ui-spec §9).
        returnFocus.current = origin;
        setPassword("");
        setError(null);
        setOpen(true);
      }),
    [],
  );

  const runWithReauth = useCallback(
    async function run<T>(action: () => Promise<T>): Promise<T> {
      // Se captura antes de ejecutar: el botón puede deshabilitarse y perder el foco.
      const origin = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      try {
        return await action();
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.code !== "reauth_required") {
          throw caught;
        }
        const confirmed = await askPassword(origin);
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
    restoreFocus(returnFocus.current);
    returnFocus.current = null;
  }

  // Escape cancela y Tab no sale del diálogo mientras está abierto.
  function onDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      finish(false);
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(
        'input:not([disabled]), button:not([disabled]), [href], select:not([disabled]), textarea:not([disabled])',
      ),
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !dialogRef.current.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) {
      event.preventDefault();
      first.focus();
    }
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
        <div className={styles.overlay} role="presentation" onKeyDown={onDialogKeyDown}>
          <form
            ref={dialogRef}
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
              <PasswordInput
                id="reauth-password"
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
