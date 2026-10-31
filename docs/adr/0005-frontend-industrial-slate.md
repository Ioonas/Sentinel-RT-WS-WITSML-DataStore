# ADR 0005 — Interfaz administrativa Next.js e Industrial Slate

- Estado: aceptado
- Fecha: 2026-10-31
- Contexto: spec §7 y §9 (UI de administración)

## Decisión

- La interfaz vive en `frontend/` como aplicación **Next.js App Router** con
  React Server/Client Components, CSS Modules y TypeScript estricto.
- La UI consume exclusivamente la API administrativa `/admin-api/v1` a través
  del rewrite de Next.js (`/admin-api/:path*` → `SENTINEL_API_URL`). No accede
  a PostgreSQL ni comparte código del núcleo Python.
- La autenticación usa la cookie de sesión `HttpOnly` emitida por el backend.
  El middleware solo comprueba su presencia para redirigir; la autorización
  real se valida en el servidor. El token CSRF se lee de la cookie
  `sentinel_csrf` y se envía como `X-CSRF-Token` en cada mutación.
- La identidad visual usa los tokens **Industrial Slate v1.1**: fondo grafito,
  superficies elevadas, acento naranja industrial, tipografía Roboto Flex y
  JetBrains Mono para identificadores, estados y valores técnicos.
- Las páginas cubren: resumen, configuración, cuentas de servicio, usuarios
  administrativos, roles/acceso, inventario WITSML, auditoría y perfil.
- Las credenciales de servicio se muestran una sola vez; la UI no las persiste
  ni las vuelve a solicitar.

## Consecuencias

- El frontend es desplegable de forma independiente y puede apuntar a otra
  instancia del backend mediante `SENTINEL_API_URL`.
- Los errores de la API se muestran con mensajes del servidor; un `401`
  redirige al inicio de sesión.
- Los formularios reflejan permisos, pero **nunca** sustituyen la autorización
  del backend.
- En producción la UI y la API deben servirse bajo HTTPS para que la cookie
  `Secure` funcione.

## Alternativas descartadas

- SPA con JWT en `localStorage`: expone el token a JavaScript y complica la
  revocación.
- Renderizado del lado del servidor con acceso directo a la base: duplicaría
  reglas de autorización y rompería la arquitectura hexagonal.
- Framework CSS utilitario sin tokens: dificulta mantener la identidad
  Industrial Slate y la consistencia entre páginas.
