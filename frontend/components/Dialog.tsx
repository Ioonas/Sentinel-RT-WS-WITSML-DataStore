"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import styles from "./Dialog.module.css";

const FOCUSABLE =
  'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href]';

type ModalDialogProps = {
  titleId: string;
  descriptionId?: string;
  role?: "dialog" | "alertdialog";
  tone?: "warn" | "danger";
  wide?: boolean;
  busy?: boolean;
  onClose: () => void;
  children: ReactNode;
};

/**
 * Diálogo modal accesible: foco inicial en el elemento con `data-initial-focus`
 * (o el primero enfocable), Escape cierra salvo mientras hay una operación en curso,
 * Tab no sale del diálogo y al cerrar se devuelve el foco a quien lo abrió.
 */
export function ModalDialog({
  titleId,
  descriptionId,
  role = "dialog",
  tone,
  wide = false,
  busy = false,
  onClose,
  children,
}: ModalDialogProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const origin = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const initial =
      dialogRef.current?.querySelector<HTMLElement>("[data-initial-focus]") ??
      dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    initial?.focus();
    return () => {
      if (origin && origin.isConnected) origin.focus();
    };
  }, []);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!busy) onClose();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
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

  const className = [styles.dialog, wide ? styles.wide : ""].filter(Boolean).join(" ");

  return (
    <div className={styles.overlay} role="presentation" onKeyDown={onKeyDown}>
      <div
        ref={dialogRef}
        className={className}
        data-tone={tone}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        {children}
      </div>
    </div>
  );
}
