"use client";

import { useId, useMemo, useState } from "react";
import { Alert, Input } from "@/components/ui";
import { type ObjectView } from "@/lib/api";
import { useApiQuery } from "@/lib/hooks";
import styles from "./WellPicker.module.css";

type Props = {
  value: string[];
  onChange: (next: string[]) => void;
};

// Lista de pozos del inventario con búsqueda. El alcance guarda solo uid de pozo.
export function WellPicker({ value, onChange }: Props) {
  const wells = useApiQuery<ObjectView[]>("/objects?objectType=well&limit=1000");
  const [query, setQuery] = useState("");
  const legendId = useId();
  const searchId = useId();

  const options = useMemo(() => {
    const term = query.trim().toLowerCase();
    const all = wells.data ?? [];
    if (!term) return all;
    return all.filter(
      (well) =>
        well.uid.toLowerCase().includes(term) || (well.name ?? "").toLowerCase().includes(term),
    );
  }, [wells.data, query]);

  function toggle(uid: string) {
    onChange(value.includes(uid) ? value.filter((item) => item !== uid) : [...value, uid]);
  }

  return (
    <fieldset className={styles.picker} aria-labelledby={legendId}>
      <legend id={legendId} className={styles.legend}>
        Alcance por pozo. Sin selección, la cuenta no tiene restricción.
      </legend>

      {wells.error ? <Alert>{wells.error.message}</Alert> : null}

      <div className={styles.selected} aria-live="polite">
        {value.length === 0 ? (
          <span className={styles.legend}>Ningún pozo seleccionado.</span>
        ) : (
          value.map((uid) => (
            <span key={uid} className={styles.chip}>
              {uid}
              <button
                type="button"
                aria-label={`Quitar ${uid}`}
                onClick={() => onChange(value.filter((item) => item !== uid))}
              >
                ×
              </button>
            </span>
          ))
        )}
      </div>

      <label htmlFor={searchId} className={styles.legend}>
        Buscar pozo
      </label>
      <Input
        id={searchId}
        type="search"
        placeholder="Nombre o uid"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      <div className={styles.list}>
        {wells.loading ? (
          <div className={styles.empty}>Cargando pozos…</div>
        ) : (wells.data ?? []).length === 0 ? (
          <div className={styles.empty}>
            No hay pozos en el inventario. Cree los pozos antes de limitar una cuenta a ellos.
          </div>
        ) : options.length === 0 ? (
          <div className={styles.empty}>Ningún pozo coincide con la búsqueda.</div>
        ) : (
          options.map((well) => (
            <label key={well.uid} className={styles.row}>
              <input
                type="checkbox"
                checked={value.includes(well.uid)}
                onChange={() => toggle(well.uid)}
              />
              <span>
                {well.name ?? well.uid}
                <small>{well.uid}</small>
              </span>
            </label>
          ))
        )}
      </div>
    </fieldset>
  );
}
