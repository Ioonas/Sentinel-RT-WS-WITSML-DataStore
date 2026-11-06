"use client";

import { ModalDialog } from "@/components/Dialog";
import { Button } from "@/components/ui";
import styles from "./Dialog.module.css";

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
 * El foco inicial va a "Cancelar" para que un Enter accidental no ejecute la acción.
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
  return (
    <ModalDialog
      titleId="confirm-title"
      descriptionId="confirm-description"
      role="alertdialog"
      tone={tone}
      busy={busy}
      onClose={onCancel}
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
    </ModalDialog>
  );
}
