# ADR 0004 — Identidad, sesiones y credenciales

- Estado: aceptado
- Fecha: 2026-10-31
- Contexto: spec §5 y §8

## Decisión

- Los roles humanos y las cuentas de servicio son independientes.
- Las cuentas de servicio usan HTTP Basic y contraseñas Argon2id; el secreto se
  muestra una sola vez al crearlo o rotarlo.
- Las sesiones humanas usan un token aleatorio en cookie `HttpOnly`,
  `Secure` (en producción), `SameSite=Lax`; en base de datos solo se guarda su
  SHA-256. La mutación exige CSRF double-submit (`cookie` + `X-CSRF-Token`).
- Invitaciones y recuperación usan tokens de un solo uso con caducidad y hash
  SHA-256.
- La autorización se evalúa en el servidor en cada endpoint y en cada operación
  WMLS. Se deniega por defecto. El alcance por pozo (`well_scope`) filtra
  también las consultas globales.
- Cambiar contraseña o deshabilitar un usuario revoca sus sesiones.

## Consecuencias

- La UI nunca es una frontera de seguridad; ocultar un botón no autoriza nada.
- Los logs y la auditoría no contienen contraseñas, tokens, cookies ni XML.
- El primer arranque no tiene credenciales predeterminadas: exige `/setup`.

## Alternativas descartadas

- JWT en el navegador: expone el token a JavaScript y complica la revocación.
- Guardar tokens en claro: un volcado de base permitiría suplantar sesiones.
