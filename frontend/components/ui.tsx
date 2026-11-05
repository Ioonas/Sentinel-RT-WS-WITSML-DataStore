import { useState } from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import styles from "./ui.module.css";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      className={[styles.button, styles[variant], styles[size], className]
        .filter(Boolean)
        .join(" ")}
    />
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={[styles.card, className].filter(Boolean).join(" ")}>{children}</section>;
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className={styles.pageHeader}>
      <div>
        <h1>{title}</h1>
        {description ? <p className={styles.muted}>{description}</p> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </header>
  );
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <label className={styles.field} htmlFor={htmlFor}>
      <span className={styles.label}>{label}</span>
      {children}
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={[styles.input, props.className].filter(Boolean).join(" ")} />;
}

export function PasswordInput({
  minLength,
  value,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [visible, setVisible] = useState(false);
  const length = typeof value === "string" ? value.length : 0;
  const belowMin = typeof minLength === "number" && length < minLength;
  const counter =
    typeof minLength === "number"
      ? `${length} caracteres · mínimo ${minLength}`
      : `${length} caracteres`;
  return (
    <div className={styles.passwordBlock}>
      <div className={styles.passwordWrap}>
        <Input
          {...props}
          type={visible ? "text" : "password"}
          minLength={minLength}
          value={value}
          autoCapitalize="none"
          spellCheck={false}
        />
        <button
          type="button"
          className={styles.passwordToggle}
          aria-pressed={visible}
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? "Ocultar" : "Mostrar"}
        </button>
      </div>
      <span className={belowMin && length > 0 ? styles.counterWarn : styles.counter}>{counter}</span>
    </div>
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={[styles.input, props.className].filter(Boolean).join(" ")} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={[styles.input, props.className].filter(Boolean).join(" ")} />;
}

export function StatusBadge({
  status,
  label,
}: {
  status: "ok" | "warn" | "danger" | "neutral";
  label: string;
}) {
  return <span className={[styles.badge, styles[status]].join(" ")}>{label}</span>;
}

export function Alert({
  tone = "danger",
  children,
}: {
  tone?: "danger" | "warn" | "ok" | "info";
  children: ReactNode;
}) {
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={[styles.alert, styles[tone]].join(" ")}>
      {children}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className={styles.empty}>{children}</div>;
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className={styles.mono}>{children}</span>;
}

export function Spinner() {
  return <span aria-label="Cargando" className={styles.spinner} />;
}
