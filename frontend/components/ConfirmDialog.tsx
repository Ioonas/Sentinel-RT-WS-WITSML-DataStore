"use client";

import { useEffect, useRef, type KeyboardEvent } from "react";
import { Button } from "@/components/ui";
import styles from "./ConfirmDialog.module.css";

type ConfirmDialogProps = {
  title: string;
  description: string;
  confirmLabel: string;
  tone: "warn" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * Confirmación de una acción sensible dentro de la aplicación (sustituye window.confirm).
 * El foco inicial va a "Cancelar" para que un Enter accidental no ejecute la acción,
 * Escape cancela, Tab no sale del diálogo, y al cerrar se devuelve el foco a quien lo abrió.
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  tone,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const origin = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.querySelector<HTMLElement>('[data-initial-focus]')?.focus();
    return () => {
      if (origin && origin.isConnected) origin.focus();
    };
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!busy) onCancel();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled])"),
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

  return (
    <div className={styles.overlay} role="presentation" onKeyDown={onKeyDown}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        data-tone={tone}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-description"
      >
        <h2 id="confirm-title" className={styles.title}>
          {title}
        </h2>
        <p id="confirm-description" className={styles.text}>
          {description}
        </p>
        <div className={styles.actions}>
          <Button
            type="button"
            variant="ghost"
            data-initial-focus=""
            onClick={onCancel}
            disabled={busy}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Procesando…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
