# Especificación inicial de la interfaz administrativa

- Versión: 0.1 (borrador para implementación)
- Fecha: 2026-11-04
- Producto: Sentinel RT&WS WITSML DataStore 1.0.3
- Fuentes: spec v0.9 §8, ADR 0005, ADR 0008 y frontend Next.js existente en
  `frontend/`
- Estado del código: la UI base ya existe; esta especificación fija el
  comportamiento esperado y las brechas que debe cerrar la fase de interfaz.

## 1. Objetivo y alcance

La interfaz administrativa permite operar y auditar el DataStore sin exponer
WITSML ni PostgreSQL al navegador. Consume exclusivamente
`/admin-api/v1` y presenta las vistas de §8.3.

**Incluido en 1.0.3**

- Inicio y cierre de sesión humana, recuperación de acceso y aceptación de
  invitaciones.
- Resumen operativo, configuración pública, cuentas de servicio, usuarios
  administrativos, roles/acceso, inventario WITSML, borrado administrativo,
  auditoría y perfil propio.
- Visibilidad de acciones según permisos y estados de error/confirmación.

**Fuera de alcance**

- Editar XML, curvas o valores WITSML desde la UI.
- Crear roles personalizados, MFA/TOTP, sesiones ETP o streaming.
- Conversión de unidades.
- Acceso directo a PostgreSQL o al endpoint SOAP desde el navegador.
- Aplicaciones móviles nativas.

## 2. Principios

1. **El backend es la única frontera de seguridad.** Ocultar un botón o una
   ruta no autoriza ni deniega nada; toda acción se revalida en el servidor.
2. **Mínimo privilegio visible.** La UI muestra solo datos y acciones que el
   actor puede ejecutar, pero sigue mostrando el error del servidor cuando una
   acción falla por permisos.
3. **Sin secretos persistentes.** El secreto de una cuenta de servicio y el
   enlace de invitación se muestran una sola vez y no se guardan en
   `localStorage`, `sessionStorage`, URLs ni logs.
4. **Trazabilidad sin datos sensibles.** La auditoría muestra actor, acción,
   objeto, resultado, correlación y duración; nunca contraseñas, tokens,
   cabeceras de autorización ni XML completo.
5. **Identificadores técnicos en monoespaciada.** UID, `uidWell`,
   `uidWellbore`, correlación y valores de estado usan JetBrains Mono.
6. **Español de interfaz y UTC.** Las fechas se muestran en UTC y con formato
   consistente; no se convierten a la zona del navegador en esta versión.

## 3. Arquitectura de la interfaz

| Elemento | Decisión |
| --- | --- |
| Framework | Next.js 15 App Router, React 19 y TypeScript estricto. |
| Estilos | CSS Modules y variables CSS en `frontend/app/globals.css`. Sin Tailwind ni Styled Components. |
| Datos | Cliente `api<T>()` en `frontend/lib/api.ts`; hooks `useApiQuery` para lecturas. |
| Transporte | Rewrite `/admin-api/:path*` → `SENTINEL_API_URL`. El navegador nunca conoce la URL interna del backend. |
| Sesión | Cookie `sentinel_session` `HttpOnly`; el middleware solo comprueba su presencia. |
| CSRF | Cookie `sentinel_csrf` + cabecera `X-CSRF-Token` en cada método no idempotente. |
| Errores | `ApiError` normaliza `{ message, error }`; un `401` redirige a `/admin/login`. |
| Renderizado | Páginas de dashboard como Client Components; no se accede a la base desde el servidor Next.js. |

La UI no comparte código Python, no importa los XSD y no construye XML WITSML.

## 4. Roles y permisos

Los roles humanos y las cuentas de servicio son independientes. Un rol de
cuenta de servicio (`reader`/`writer`) no otorga acceso a esta UI.

| Rol humano | Permisos administrativos | Uso esperado |
| --- | --- | --- |
| `superadministrador` | Todos | Configuración, identidades, objetos, auditoría y salud. |
| `administrador_seguridad` | `admin.identities.write`, `admin.roles.read`, `admin.audit.read`, `admin.health.read` | Cuentas, invitaciones y auditoría; no cambia el contacto ni borra objetos. |
| `auditor` | `admin.audit.read`, `admin.objects.read`, `admin.roles.read` | Consulta de auditoría, inventario y matriz de acceso. |
| `operador` | `admin.objects.read`, `admin.health.read`, `admin.roles.read` | Inventario y salud; sin escrituras ni borrado. |
| `administrador` | Solo los permisos delegados en su cuenta | Operación acotada por delegación explícita. |

Reglas de presentación:

- Las rutas sin permiso de lectura muestran `403` con mensaje del servidor, no
  una página vacía.
- Las acciones de escritura se ocultan o deshabilitan si falta el permiso, pero
  el backend vuelve a comprobarlo.
- El borrado de objetos exige `admin.objects.delete` **y** reautenticación
  reciente.
- La configuración de contacto exige superadministrador.
- Cambiar roles, invitar, rotar o revocar credenciales y cambiar el contacto
  exigen reautenticación reciente (§8.1).

## 5. Mapa de rutas

| Ruta | Vista | Acceso |
| --- | --- | --- |
| `/admin` | Redirección a `/admin/overview`. | Sesión. |
| `/admin/login` | Inicio de sesión y primer arranque. | Público. |
| `/admin/recover` | Solicitud de recuperación. | Público. |
| `/admin/reset-password` | Restablecimiento con token de un uso. | Público. |
| `/admin/accept-invitation` | Aceptación de invitación. | Público. |
| `/admin/overview` | Resumen del servicio. | Sesión. |
| `/admin/server-configuration` | Contacto público y límites. | Sesión; edición solo superadministrador. |
| `/admin/service-accounts` | Cuentas de servicio y credenciales. | `admin.identities.write`. |
| `/admin/admin-users` | Usuarios administrativos e invitaciones. | `admin.identities.write`. |
| `/admin/access` | Roles, permisos y acceso efectivo. | `admin.roles.read`. |
| `/admin/objects` | Inventario y borrado. | `admin.objects.read`; borrado con `admin.objects.delete`. |
| `/admin/audit` | Auditoría. | `admin.audit.read`. |
| `/admin/profile` | Cuenta propia. | Sesión. |

El middleware redirige a `/admin/login?next=<ruta>` cuando falta la cookie de
sesión. La página de login debe respetar `next` y no redirigir siempre a
`/admin/overview`.

## 6. Flujos transversales

### 6.1 Sesión

- El login envía `POST /auth/sessions` y recibe la cookie de sesión y el token
  CSRF.
- El cierre de sesión usa `DELETE /auth/sessions` y limpia el estado local.
- Un `401` en cualquier consulta redirige al login conservando la ruta de
  origen.
- La contraseña cumple la política vigente: **15 caracteres mínimos**, máximo
  de al menos 64 y lista local de comprometidas. Cualquier texto de ayuda debe
  decir 15, no 12.

### 6.2 Reautenticación

Las operaciones sensibles pueden devolver `403` con
`error = "reauth_required"` cuando la sesión supera la ventana de 5 minutos.
La UI debe:

1. Detectar específicamente ese código.
2. Abrir un diálogo que pida la contraseña actual del usuario.
3. Reenviar `POST /auth/sessions` con el correo de la sesión y la contraseña;
   el backend rota la cookie y actualiza `authenticated_at`.
4. Repetir **una sola vez** la operación original y cerrar el diálogo.
5. Si el login falla, mantener la operación cancelada y mostrar el error
   genérico.

El diálogo no debe almacenar la contraseña ni reutilizarla para otras acciones.

### 6.3 Errores, carga y vacío

- `400`/`422`: mensaje del servidor junto al formulario.
- `401`: redirección al login.
- `403`: mensaje de permiso; `reauth_required` sigue el flujo 6.2.
- `404`: mensaje de objeto no encontrado.
- `409`: conflicto de estado (por ejemplo, cuenta ya existente) sin detalles
  internos.
- `429`: aviso de espera; no se reintenta automáticamente.
- `503`: estado degradado visible en el resumen.
- Toda tabla debe distinguir **cargando**, **sin resultados** y **error**.
- Toda mutación deshabilita el botón mientras está en curso y evita envíos
  duplicados.

### 6.4 Confirmaciones

- Borrado administrativo: motivo (5–500 caracteres) y confirmación exacta del
  `uid`; se muestran tipo, UID, pozo, sondeo y dependencias antes de habilitar
  el botón.
- Rotación/revocación de credenciales: confirmación explícita; el secreto nuevo
  se muestra una sola vez con opción de copiar.
- Deshabilitar una cuenta o usuario: confirmación con el nombre visible.
- Cambio de contacto: confirmación y reautenticación; el valor nuevo se refleja
  al recargar `GetCap`.

## 7. Especificación por vista

### 7.1 Resumen (`/admin/overview`)

**Datos:** `/profile`, `/server-config`, `/health/dependencies`,
`/mail-outbox/pending`.

**Contenido**

- Saludo con el nombre del usuario y estado general de dependencias.
- Indicadores: producto y versión, API WMLS, estado de configuración inicial y
  correo pendiente.
- Tabla de dependencias con estado y detalle técnico.
- Contacto público expuesto en `GetCap`.
- Accesos rápidos a las vistas principales.

**Reglas**

- Sin gráficos de series temporales ni estado ETP.
- Un error de `/health/dependencies` por permiso se muestra como «sin permiso»,
  no como caída del servicio.
- El estado nunca se etiqueta como «streaming».

### 7.2 Configuración del servidor (`/admin/server-configuration`)

**Datos:** `GET /server-config`, `PUT /server-config/contact`.

**Contenido**

- Correo y teléfono editables.
- Nombre del producto, vendor, descripción, versión, versión de esquema y API
  en solo lectura.
- Límites publicados en `GetCap` en solo lectura: nodos, puntos, crecimiento,
  detección de cambios, últimos valores y cascada.

**Reglas**

- Solo superadministrador puede guardar; el resto ve la vista en lectura.
- Validar correo y teléfono en cliente, sin sustituir la validación del
  servidor.
- Tras guardar, recargar la configuración y mostrar el valor persistido.
- La operación exige reautenticación reciente.

### 7.3 Cuentas de servicio (`/admin/service-accounts`)

**Datos:** `GET/POST /service-accounts`,
`GET/PATCH /service-accounts/{id}`,
`POST /service-accounts/{id}/rotate-credential`,
`POST /service-accounts/{id}/revoke-credential`.

**Contenido**

- Lista con nombre, rol, estado, alcance por pozo y última utilización.
- Alta con rol `reader`/`writer`, permisos por tipo de objeto y alcance
  opcional por pozo.
- Edición de permisos y estado.
- Rotación y revocación de credencial.

**Reglas**

- El secreto se muestra una sola vez, en un panel que no se puede recuperar al
  recargar.
- No se muestran hashes, tokens ni credenciales anteriores.
- Una cuenta deshabilitada conserva su historial pero no puede autenticarse.
- El alcance por pozo se presenta como lista de UID de pozo; vacío significa
  todos los pozos permitidos por los grants.

### 7.4 Usuarios administrativos (`/admin/admin-users`)

**Datos:** `GET /admin-users`, `GET/PATCH /admin-users/{id}`,
`POST /invitations`, `POST /invitations/accept`.

**Contenido**

- Lista de usuarios con correo, nombre, rol, estado y último acceso.
- Invitación por correo y rol predefinido.
- Cambio de rol, deshabilitación y detalle.

**Reglas**

- No se puede cambiar el rol propio.
- El enlace/token de invitación se muestra una sola vez si la respuesta lo
  incluye; no se registra en la UI.
- El rol `administrador` solo muestra los permisos delegados; no se inventan
  permisos por defecto.
- La aceptación de invitación es una ruta pública y de un solo uso.

### 7.5 Roles y acceso (`/admin/access`)

**Datos:** `GET /roles`, `GET /permissions`, `GET /access`.

**Contenido**

- Matriz de permisos por rol predefinido.
- Acceso efectivo por identidad: rol, permisos y grants WITSML.
- Leyenda de permisos administrativos y de acciones WITSML.

**Reglas**

- Solo lectura; no se crean roles personalizados.
- Los permisos se muestran con su nombre técnico y una descripción breve.
- El alcance por pozo se muestra explícitamente cuando existe.

### 7.6 Objetos WITSML (`/admin/objects`)

**Datos:** `GET /objects`, `GET /objects/{type}/{uid}`,
`GET /objects/{type}/{uid}/dependencies`,
`POST /objects/{type}/{uid}/delete`.

**Contenido**

- Filtros por tipo (`well`, `wellbore`, `log`, `mudLog`, `trajectory`),
  `uidWell`, `uidWellbore` y nombre; límite de 200 por consulta.
- Tabla con UID, nombre, jerarquía, fecha de cambio y estado `growing`.
- Detalle de metadatos autorizados y dependencias.
- Borrado explícito con motivo y confirmación exacta.

**Reglas**

- El borrado no es en cascada. Si el objeto conserva hijos, el backend responde
  con el error de dependencias y la UI indica el orden de eliminación.
- El actor solo ve objetos dentro de su alcance; un objeto fuera de alcance se
  comporta como no encontrado.
- No se muestran curvas, XML ni valores de muestra.
- `mudLog` debe estar disponible en el selector: es un objeto de primera clase.

### 7.7 Auditoría (`/admin/audit`)

**Datos:** `GET /audit-events` con paginación por cursor.

**Filtros:** fecha inicial/final, actor, acción, tipo de objeto, UID de objeto,
resultado y correlación.

**Contenido**

- Tabla con hora UTC, actor, canal, acción, objeto, resultado, duración y
  correlación.
- Detalle de `details` redactado por el backend.

**Reglas**

- Solo lectura.
- No se muestran contraseñas, tokens, cabeceras ni XML.
- La paginación usa `next_cursor`; no se ofrece saltar a una página arbitraria.
- Un rango vacío muestra un estado vacío explícito, no una tabla en blanco.

### 7.8 Perfil (`/admin/profile`)

**Datos:** `GET /profile`, `POST /profile/password`,
`DELETE /profile/session`.

**Contenido**

- Correo, nombre, rol y permisos efectivos.
- Cambio de contraseña con contraseña actual y confirmación.
- Cierre de sesión propio.

**Reglas**

- No se puede cambiar el propio rol.
- Tras cambiar la contraseña se cierra la sesión y se redirige al login.
- La nueva contraseña cumple la política de 15 caracteres mínimos.

### 7.9 Vistas públicas de acceso

- **Login:** mensajes genéricos; no confirma si un correo existe. En el primer
  arranque captura contacto y primer superadministrador.
- **Recuperación:** solicitud siempre genérica; no revela cuentas.
- **Restablecimiento:** token de un solo uso, 30 minutos; valida la política de
  contraseña.
- **Aceptación de invitación:** token de un solo uso, 72 horas; establece
  contraseña y nombre visible.

## 8. Componentes y diseño visual

Tokens únicos en `:root` de `frontend/app/globals.css` (Industrial Slate v1.1):

- Fondo grafito `#0d1216`, superficies `#151d23`/`#1c262e`, acento naranja
  `#e07a2f`, estados ok/warn/danger y foco `#7fc4ff`.
- Tipografía Roboto Flex para interfaz y JetBrains Mono para identificadores.
- Radios 4/8/14 px, espaciado en escala de 4 px y transición de 140 ms.

Primitivas existentes que deben reutilizarse:

| Componente | Uso |
| --- | --- |
| `Button` | Acciones primarias, secundarias, ghost y peligro. |
| `Card`, `Section`, `Stat` | Contenedores y métricas. |
| `Field`, `Input`, `Select`, `Textarea` | Formularios accesibles con etiqueta. |
| `StatusBadge` | Estado de servicio, objeto y resultado. |
| `Alert` | Errores, avisos y confirmaciones. |
| `Spinner`, `EmptyState`, `EmptyRow` | Carga y vacío. |
| `Tags`, `Mono` | Listas cortas e identificadores. |
| `GrantEditor`, `PermissionChecks` | Permisos WITSML y administrativos. |

Reglas visuales:

- Un solo `h1` por página mediante `PageHeader`.
- No se usan colores fuera de los tokens.
- Las tablas permiten desplazamiento horizontal en pantallas estrechas.
- El foco visible nunca se elimina.
- Los formularios muestran errores junto al campo y un resumen al inicio.

## 9. Accesibilidad y responsive

- Contraste mínimo WCAG AA (4.5:1 para texto normal y 3:1 para texto grande).
- Navegación completa por teclado; orden de tabulación lógico.
- Diálogos con `role="dialog"`, `aria-modal`, título asociado y retorno del
  foco al elemento que los abrió.
- Mensajes de error anunciados con `role="alert"` o `aria-live="polite"`.
- Etiquetas explícitas en todos los controles; los identificadores técnicos no
  sustituyen a la etiqueta.
- Ancho mínimo soportado: 360 px. La barra lateral se colapsa y las tablas se
  desplazan sin romper el layout.
- Respeto de `prefers-reduced-motion` para transiciones no esenciales.

## 10. Contrato con la API administrativa

| Vista | Endpoint principal |
| --- | --- |
| Arranque | `GET /setup/status`, `POST /setup` |
| Sesión | `POST/DELETE /auth/sessions` |
| Recuperación | `POST /auth/recovery`, `POST /auth/reset-password` |
| Invitación | `POST /invitations`, `POST /invitations/accept` |
| Perfil | `GET /profile`, `POST /profile/password`, `DELETE /profile/session` |
| Configuración | `GET /server-config`, `PUT /server-config/contact` |
| Cuentas de servicio | `GET/POST /service-accounts`, `GET/PATCH /service-accounts/{id}`, `POST .../rotate-credential`, `POST .../revoke-credential` |
| Usuarios | `GET /admin-users`, `GET/PATCH /admin-users/{id}` |
| Acceso | `GET /roles`, `GET /permissions`, `GET /access` |
| Objetos | `GET /objects`, `GET /objects/{type}/{uid}`, `GET .../dependencies`, `POST .../delete` |
| Auditoría | `GET /audit-events` |
| Salud | `GET /health`, `GET /health/ready`, `GET /health/dependencies` |

Todos los errores usan `{ message, error }`. Las mutaciones requieren CSRF. La
UI no asume campos que el backend no devuelva.

## 11. Brechas conocidas y trabajo de la fase UI

| ID | Brecha | Prioridad | Criterio de cierre |
| --- | --- | --- | --- |
| UI-01 | El selector de objetos no incluye `mudLog`. | Alta | `mudLog` aparece y el inventario/dependencias funcionan. |
| UI-02 | No existe diálogo de reautenticación para `403 reauth_required`. | Alta | Borrado, invitación, roles, credenciales y contacto se reintentan tras reautenticar. |
| UI-03 | El login ignora `?next=` y siempre va a `/admin/overview`. | Media | Tras autenticarse se abre la ruta solicitada. |
| UI-04 | La ayuda del login dice 12 caracteres; la política vigente es 15. | Alta | Texto y validación alineados con §8.1. |
| UI-05 | No hay pruebas E2E de rutas, permisos, CSRF ni contraste. | Alta | Suite de interfaz con evidencia para los criterios 23, 30, 31 y 32. |
| UI-06 | No se listan invitaciones pendientes (solo se crean). | Media | Decidir si se añade `GET /invitations` o se documenta la limitación. |
| UI-07 | El alcance por pozo se captura como texto libre. | Media | Selector con búsqueda de pozos y validación contra el inventario. |
| UI-08 | No se muestra el resultado de la auditoría en detalle expandible. | Baja | Fila expandible con `details` ya redactado por el backend. |

## 12. Pruebas y criterios de aceptación

| Criterio | Verificación |
| --- | --- |
| 23 | Una petición sin sesión a cada ruta privada redirige al login; una mutación sin CSRF falla con `403`. |
| 24 | La vista de auditoría no contiene contraseñas, tokens, cabeceras ni XML. |
| 30 | La UI solo llama a `/admin-api/v1`; una prueba de red no detecta PostgreSQL ni `/witsml`. |
| 31 | Los tokens visuales existen una sola vez en `:root` y las páginas los consumen. |
| 32 | Prueba automatizada de contraste WCAG AA sobre las vistas principales. |
| §8.5 | El borrado exige motivo, confirmación, permiso y reautenticación; un padre con hijos no se elimina. |
| §8.6 | Las cookies son `HttpOnly`/`SameSite`; el cierre de sesión y el cambio de contraseña revocan la sesión. |

Pruebas mínimas por vista:

1. Render con datos, vacío y error.
2. Permiso denegado y `401`.
3. Mutación correcta y mutación rechazada.
4. Reautenticación cuando aplique.
5. Navegación por teclado y foco visible.

## 13. Plan de entrega

1. **Base y seguridad:** corregir UI-02, UI-03 y UI-04; añadir el diálogo de
   reautenticación y la gestión uniforme de errores.
2. **Cobertura funcional:** UI-01, UI-06, UI-07 y UI-08; completar formularios y
   estados de las ocho vistas.
3. **Calidad:** pruebas E2E, contraste, teclado y responsive; evidencia para los
   criterios 23, 24, 30, 31 y 32.
4. **Cierre:** revisión de diseño contra Industrial Slate v1.1 y actualización
   de ADR/README con las decisiones finales.
