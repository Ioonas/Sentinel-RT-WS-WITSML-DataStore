// Suite E2E de la interfaz administrativa (UI-05; criterios 23, 30, 31 y 32 de docs/ui-spec.md).
//
// Requiere el backend de tests/e2e/server.py (puerto 8100) y la interfaz servida en
// E2E_BASE_URL (por defecto http://localhost:3100). Ver e2e/run-e2e.sh.
// Playwright se carga desde la instalación global del entorno (NODE_PATH).

import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3100";
const ADMIN = {
  email: "admin@example.com",
  password: "Clave-Operativa-2026",
};
const SETUP = {
  contact_email: "ops@example.com",
  contact_phone: "+1 555 0100",
  admin_email: ADMIN.email,
  admin_name: "Administrador",
  admin_password: ADMIN.password,
};

const PRIVATE_ROUTES = [
  "/admin/overview",
  "/admin/server-configuration",
  "/admin/service-accounts",
  "/admin/admin-users",
  "/admin/access",
  "/admin/objects",
  "/admin/audit",
  "/admin/profile",
];

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

let browser;

before(async () => {
  browser = await chromium.launch();
  const status = await fetch(`${BASE}/admin-api/v1/setup/status`).then((r) => r.json());
  if (!status.setup_completed) {
    const response = await fetch(`${BASE}/admin-api/v1/setup`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(SETUP),
    });
    assert.equal(response.status, 201, await response.text());
  }
});

after(async () => {
  await browser?.close();
});

async function loggedInContext() {
  const context = await browser.newContext({ baseURL: BASE });
  const page = await context.newPage();
  await page.goto("/admin/login");
  await page.getByLabel("Correo").fill(ADMIN.email);
  await page.getByLabel("Contraseña").fill(ADMIN.password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await page.waitForURL("**/admin/overview");
  return { context, page };
}

describe("criterio 23: acceso y CSRF", () => {
  test("cada ruta privada sin sesión redirige al login con next", async () => {
    const context = await browser.newContext({ baseURL: BASE });
    const page = await context.newPage();
    for (const route of PRIVATE_ROUTES) {
      await page.goto(route);
      const url = new URL(page.url());
      assert.equal(url.pathname, "/admin/login", `${route} debe redirigir al login`);
      assert.equal(url.searchParams.get("next"), route, `${route} debe conservar next`);
    }
    await context.close();
  });

  test("una mutación sin token CSRF responde 403", async () => {
    const { context } = await loggedInContext();
    const body = { email: "sin-csrf@example.com", role: "auditor" };
    const missing = await context.request.post(`${BASE}/admin-api/v1/invitations`, { data: body });
    assert.equal(missing.status(), 403);

    const wrong = await context.request.post(`${BASE}/admin-api/v1/invitations`, {
      data: body,
      headers: { "x-csrf-token": "no-es-el-token" },
    });
    assert.equal(wrong.status(), 403);
    await context.close();
  });
});

describe("criterio 30: la interfaz solo habla con la API administrativa", () => {
  test("ninguna petición de la interfaz sale de /admin ni llega a PostgreSQL o /witsml", async () => {
    const { context, page } = await loggedInContext();
    const seen = [];
    page.on("request", (request) => seen.push(new URL(request.url())));

    for (const route of PRIVATE_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
    }

    assert.ok(seen.length > 0);
    for (const url of seen) {
      assert.equal(url.origin, BASE, `petición fuera del origen de la interfaz: ${url.href}`);
      assert.ok(!url.pathname.includes("/witsml"), `llamada a /witsml: ${url.href}`);
      assert.ok(
        url.pathname.startsWith("/admin") ||
          url.pathname.startsWith("/_next/") ||
          url.pathname.startsWith("/admin-api/v1/") ||
          url.pathname.startsWith("/favicon"),
        `ruta no permitida: ${url.href}`,
      );
    }
    await context.close();
  });
});

describe("criterio 31: tokens visuales definidos una sola vez", () => {
  test("los colores viven en :root de globals.css y las páginas no los escriben", () => {
    const globals = readFileSync(join(frontendRoot, "app/globals.css"), "utf8");
    const rootBlock = globals.slice(globals.indexOf(":root {"), globals.indexOf("}", globals.indexOf(":root {")));
    assert.equal((globals.match(/--color-bg:/g) ?? []).length, 1, "--color-bg debe definirse una sola vez");
    assert.ok(rootBlock.includes("--color-bg:"), "los tokens de color deben estar en :root");

    const colorLiteral = /#[0-9a-fA-F]{3,8}\b|rgba?\(/;
    const offenders = [];
    for (const file of walk(join(frontendRoot, "app")).concat(walk(join(frontendRoot, "components")))) {
      if (!/\.(css|tsx)$/.test(file) || file.endsWith("globals.css")) continue;
      const text = readFileSync(file, "utf8");
      if (colorLiteral.test(text)) offenders.push(relative(frontendRoot, file));
    }
    assert.deepEqual(offenders, [], "estos archivos escriben colores fuera de los tokens");
  });
});

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

// Cálculo WCAG ejecutado en la página: compone fondos semitransparentes sobre sus ancestros.
const CONTRAST_CHECK = () => {
  const parse = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const luminance = ({ r, g, b }) => {
    const channel = (v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const ratio = (a, b) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const backgroundAt = (element) => {
    const chain = [];
    for (let node = element; node; node = node.parentElement) chain.unshift(node);
    let bg = { r: 255, g: 255, b: 255, a: 1 };
    for (const node of chain) {
      const layer = parse(getComputedStyle(node).backgroundColor);
      if (layer && layer.a > 0) bg = over(layer, bg);
    }
    return bg;
  };

  const failures = [];
  const candidates = document.querySelectorAll("body *");
  for (const element of candidates) {
    if (element.closest("[aria-hidden='true']") || element.closest("button:disabled")) continue;
    const ownText = Array.from(element.childNodes)
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent.trim())
      .join("");
    if (!ownText) continue;
    const style = getComputedStyle(element);
    const fgRaw = parse(style.color);
    if (!fgRaw) continue;
    const bg = backgroundAt(element);
    const fg = over(fgRaw, bg);
    const size = parseFloat(style.fontSize);
    const bold = parseInt(style.fontWeight, 10) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const required = large ? 3 : 4.5;
    const value = ratio(fg, bg);
    if (value < required) {
      failures.push({ text: ownText.slice(0, 50), ratio: Number(value.toFixed(2)), required });
    }
  }
  return failures;
};

describe("criterio 32: contraste WCAG AA en las vistas principales", () => {
  test("login sin sesión cumple 4.5:1 en texto normal", async () => {
    const context = await browser.newContext({ baseURL: BASE });
    const page = await context.newPage();
    await page.goto("/admin/login");
    await page.waitForLoadState("networkidle");
    const failures = await page.evaluate(CONTRAST_CHECK);
    assert.deepEqual(failures, [], "contraste insuficiente en login");
    await context.close();
  });

  test("las vistas privadas cumplen contraste con datos cargados", async () => {
    const { context, page } = await loggedInContext();
    const report = {};
    for (const route of PRIVATE_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      report[route] = await page.evaluate(CONTRAST_CHECK);
    }
    const failing = Object.entries(report).filter(([, list]) => list.length > 0);
    assert.deepEqual(failing, [], "vistas con contraste insuficiente");
    await context.close();
  });
});
