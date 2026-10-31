"use client";

import { Alert, Card, PageHeader, Spinner, StatusBadge } from "@/components/ui";
import { EmptyRow, Section, Tags } from "@/components/dashboard";
import {
  type AccessView,
  type Grant,
  type PermissionView,
  type RoleView,
} from "@/lib/api";
import { useApiQuery } from "@/lib/hooks";
import styles from "../dashboard.module.css";

function grantLabel(grant: Grant): string {
  return `${grant.object_type}:${grant.action}${grant.uid_well ? `@${grant.uid_well}` : ""}`;
}

export default function AccessPage() {
  const roles = useApiQuery<RoleView[]>("/roles");
  const permissions = useApiQuery<PermissionView[]>("/permissions");
  const access = useApiQuery<AccessView[]>("/access");

  const error = roles.error ?? permissions.error ?? access.error;

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Roles y acceso"
        description="Matriz de roles, catálogo de permisos y acceso efectivo de cada identidad."
        actions={<StatusBadge status="neutral" label={`${access.data?.length ?? 0} identidades`} />}
      />

      {error ? <Alert>{error.message}</Alert> : null}

      <Card>
        <Section title="Roles del sistema" description="Los permisos del rol administrador son delegados por usuario.">
          {roles.loading ? (
            <Spinner />
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Rol</th>
                    <th>Permisos</th>
                  </tr>
                </thead>
                <tbody>
                  {roles.data && roles.data.length > 0 ? (
                    roles.data.map((role) => (
                      <tr key={role.name}>
                        <td>
                          <strong>{role.name}</strong>
                        </td>
                        <td>
                          <Tags values={role.permissions} />
                        </td>
                      </tr>
                    ))
                  ) : (
                    <EmptyRow colSpan={2}>Sin roles disponibles.</EmptyRow>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </Card>

      <div className={styles.split}>
        <Card>
          <Section title="Acceso efectivo" description="Humanos por rol y permisos; servicios por concesiones WMLS.">
            {access.loading ? (
              <Spinner />
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Identidad</th>
                      <th>Tipo</th>
                      <th>Rol</th>
                      <th>Permisos / concesiones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {access.data && access.data.length > 0 ? (
                      access.data.map((entry) => (
                        <tr key={`${entry.kind}:${entry.identity}`}>
                          <td className={styles.wrap}>{entry.identity}</td>
                          <td>{entry.kind}</td>
                          <td>{entry.role}</td>
                          <td>
                            <Tags
                              values={
                                entry.kind === "service"
                                  ? entry.grants.map(grantLabel)
                                  : entry.permissions
                              }
                            />
                          </td>
                        </tr>
                      ))
                    ) : (
                      <EmptyRow colSpan={4}>Sin identidades registradas.</EmptyRow>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Catálogo de permisos" description="Se deniega por defecto; el superadministrador tiene todos.">
            {permissions.loading ? (
              <Spinner />
            ) : (
              <Tags values={(permissions.data ?? []).map((item) => item.name)} />
            )}
          </Section>
        </Card>
      </div>
    </div>
  );
}
