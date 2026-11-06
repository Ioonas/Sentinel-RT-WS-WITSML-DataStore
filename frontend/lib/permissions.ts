/**
 * Nombres sencillos y descripciones de los permisos administrativos.
 * Las vistas muestran estos textos; el nombre técnico solo se usa internamente.
 */
export type PermissionInfo = { label: string; description: string };

const PERMISSION_INFO: Record<string, PermissionInfo> = {
  "admin.config.write": {
    label: "Cambiar configuración",
    description: "Modificar los datos de contacto y la configuración general del servidor.",
  },
  "admin.identities.write": {
    label: "Gestionar usuarios y cuentas de servicio",
    description:
      "Invitar, editar, deshabilitar y revisar usuarios; crear, rotar, archivar y cerrar sesiones de cuentas de servicio.",
  },
  "admin.audit.read": {
    label: "Ver auditoría",
    description: "Consultar el registro de acciones de usuarios y cuentas de servicio.",
  },
  "admin.objects.read": {
    label: "Ver pozos y datos cargados",
    description: "Consultar el inventario de pozos, sondeos, registros y trayectorias.",
  },
  "admin.objects.write": {
    label: "Crear pozos y sondeos",
    description: "Dar de alta pozos y pozos laterales directamente en el almacén.",
  },
  "admin.objects.delete": {
    label: "Borrar objetos",
    description: "Eliminar pozos, sondeos, registros o trayectorias. Pide motivo y confirmación.",
  },
  "admin.health.read": {
    label: "Ver estado del servicio",
    description: "Consultar si la base de datos, el correo y las demás dependencias funcionan.",
  },
  "admin.roles.read": {
    label: "Ver roles y permisos",
    description: "Consultar qué puede hacer cada rol y qué permisos existen.",
  },
};

export function permissionInfo(name: string): PermissionInfo {
  return PERMISSION_INFO[name] ?? { label: name, description: "Permiso sin descripción." };
}

export function permissionLabel(name: string): string {
  return permissionInfo(name).label;
}
