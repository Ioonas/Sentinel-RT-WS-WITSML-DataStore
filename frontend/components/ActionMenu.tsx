"use client";

import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import styles from "./ActionMenu.module.css";

export type ActionMenuItem = {
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
};

type Placement = { top?: number; bottom?: number; right: number };

/**
 * Menú de acciones de una fila.
 * Teclado: Enter o Espacio abren; flechas, Inicio y Fin se mueven; Escape cierra
 * y devuelve el foco al botón; Tab cierra y deja que el foco siga su curso.
 * Las acciones destructivas van al final, separadas por una línea.
 */
export function ActionMenu({
  label = "Acciones",
  subject,
  items,
}: {
  label?: string;
  /** Nombre del objeto afectado, para que el menú se anuncie con contexto. */
  subject?: string;
  items: ActionMenuItem[];
}) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  function options(): HTMLButtonElement[] {
    return Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>("button[role='menuitem']:not([disabled])") ?? [],
    );
  }

  function openMenu() {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPlacement({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
    setOpen(true);
  }

  function close(returnFocus: boolean) {
    setOpen(false);
    if (returnFocus) buttonRef.current?.focus();
  }

  // Si no hay espacio debajo del botón, el menú se abre hacia arriba. Se mide antes de pintar.
  useLayoutEffect(() => {
    if (!open || !buttonRef.current || !menuRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const height = menuRef.current.offsetHeight;
    const spaceBelow = window.innerHeight - rect.bottom;
    if (spaceBelow < height + 8 && rect.top > height + 8) {
      setPlacement({ bottom: window.innerHeight - rect.top + 4, right: window.innerWidth - rect.right });
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    options()[0]?.focus();
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    // El menú es de posición fija: al desplazarse o cambiar el tamaño, se cierra.
    function onMove() {
      setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open]);

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    }
    if (event.key === "Tab") {
      close(false);
      return;
    }
    const list = options();
    if (list.length === 0) return;
    const current = list.indexOf(document.activeElement as HTMLButtonElement);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = (current + 1) % list.length;
    if (event.key === "ArrowUp") next = (current - 1 + list.length) % list.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = list.length - 1;
    if (next === null) return;
    event.preventDefault();
    list[next].focus();
  }

  // Las acciones destructivas se separan del resto con una línea.
  const firstDangerIndex = items.findIndex((item) => item.danger);

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={styles.trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            openMenu();
          }
        }}
      >
        {label}
        <svg className={styles.chevron} width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <path
            d="M3 4.5 6 7.5 9 4.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {open && placement ? (
        <div
          className={styles.menu}
          role="menu"
          aria-label={subject ? `${label} de ${subject}` : label}
          ref={menuRef}
          onKeyDown={onMenuKeyDown}
          style={{
            right: placement.right,
            ...(placement.top !== undefined ? { top: placement.top } : { bottom: placement.bottom }),
          }}
        >
          {items.map((item, index) => (
            <Fragment key={item.label}>
              {index === firstDangerIndex && index > 0 ? (
                <div role="separator" className={styles.divider} />
              ) : null}
              <button
                type="button"
                role="menuitem"
                className={item.danger ? styles.itemDanger : styles.item}
                disabled={item.disabled}
                onClick={() => {
                  close(false);
                  item.onSelect();
                }}
              >
                {item.label}
              </button>
            </Fragment>
          ))}
        </div>
      ) : null}
    </div>
  );
}
