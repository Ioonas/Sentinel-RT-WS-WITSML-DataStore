"use client";

import type { ReactNode } from "react";
import { Button, Input, Select } from "./ui";
import type { Grant } from "@/lib/api";
import styles from "@/app/admin/(dashboard)/dashboard.module.css";
import { permissionInfo } from "@/lib/permissions";

const OBJECT_TYPES = ["*", "well", "wellbore", "log", "trajectory"] as const;
const ACTIONS = ["read", "write", "delete"] as const;

export function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={styles.statValue}>{value}</span>
      {hint ? <span className={styles.statHint}>{hint}</span> : null}
    </div>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <div className={styles.sectionTitle}>
        <div>
          <h2>{title}</h2>
          {description ? <p className={styles.faint}>{description}</p> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function EmptyRow({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className={styles.muted}>
        {children}
      </td>
    </tr>
  );
}

export function PermissionList({ names }: { names: string[] }) {
  if (names.length === 0) return <span className={styles.faint}>—</span>;
  return (
    <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 8 }}>
      {names.map((name) => {
        const info = permissionInfo(name);
        return (
          <li key={name}>
            <strong>{info.label}</strong>
            <span className={styles.faint}> — {info.description}</span>
          </li>
        );
      })}
    </ul>
  );
}

export function Tags({ values }: { values: string[] }) {
  if (values.length === 0) return <span className={styles.faint}>—</span>;
  return (
    <span className={styles.tags}>
      {values.map((value) => (
        <span key={value} className={styles.tag}>
          {value}
        </span>
      ))}
    </span>
  );
}

export function GrantEditor({
  grants,
  onChange,
}: {
  grants: Grant[];
  onChange: (grants: Grant[]) => void;
}) {
  function update(index: number, patch: Partial<Grant>) {
    onChange(grants.map((grant, position) => (position === index ? { ...grant, ...patch } : grant)));
  }

  return (
    <div className={styles.form}>
      {grants.map((grant, index) => (
        <div key={index} className={styles.formRow}>
          <Select
            aria-label={`Tipo de objeto del permiso ${index + 1}`}
            value={grant.object_type}
            onChange={(event) => update(index, { object_type: event.target.value })}
          >
            {OBJECT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type === "*" ? "Todos los objetos" : type}
              </option>
            ))}
          </Select>
          <Select
            aria-label={`Acción del permiso ${index + 1}`}
            value={grant.action}
            onChange={(event) =>
              update(index, { action: event.target.value as Grant["action"] })
            }
          >
            {ACTIONS.map((action) => (
              <option key={action} value={action}>
                {action}
              </option>
            ))}
          </Select>
          <Input
            aria-label={`Pozo del permiso ${index + 1}`}
            placeholder="uidWell opcional"
            value={grant.uid_well ?? ""}
            onChange={(event) =>
              update(index, { uid_well: event.target.value.trim() || null })
            }
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange(grants.filter((_, position) => position !== index))}
            disabled={grants.length <= 1}
          >
            Quitar
          </Button>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onChange([...grants, { object_type: "well", action: "read", uid_well: null }])}
        >
          Añadir permiso
        </Button>
      </div>
    </div>
  );
}

export function PermissionChecks({
  options,
  selected,
  onChange,
}: {
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
}) {
  function toggle(permission: string) {
    onChange(
      selected.includes(permission)
        ? selected.filter((item) => item !== permission)
        : [...selected, permission],
    );
  }

  return (
    <div className={styles.checks}>
      {options.map((permission) => {
        const info = permissionInfo(permission);
        return (
          <label key={permission} className={styles.check}>
            <input
              type="checkbox"
              checked={selected.includes(permission)}
              onChange={() => toggle(permission)}
            />
            <span>
              <strong>{info.label}</strong>
              <span className={styles.faint}> — {info.description}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
