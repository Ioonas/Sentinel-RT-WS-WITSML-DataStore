import { NextResponse } from "next/server";

// Sesión que el servidor ya no reconoce (cuenta eliminada, sesión revocada o expirada):
// se borran las cookies locales y se lleva al inicio de sesión con un aviso.
export function GET(request: Request) {
  const response = NextResponse.redirect(
    new URL("/admin/login?reason=session_ended", request.url),
  );
  for (const name of ["sentinel_session", "sentinel_csrf"]) {
    response.cookies.set(name, "", { path: "/", maxAge: 0 });
  }
  return response;
}
