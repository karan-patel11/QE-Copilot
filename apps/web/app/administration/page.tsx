"use client";

import { useCallback } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/RequestState";
import { apiClient } from "@/lib/api-client";
import { useApi } from "@/lib/use-api";

export default function AdministrationPage() {
  const loadUsers = useCallback(() => apiClient.users(), []);
  const loadOrganisations = useCallback(() => apiClient.organisations(), []);

  const users = useApi(loadUsers);
  const organisations = useApi(loadOrganisations);
  const organisation = organisations.data?.[0] ?? null;

  return (
    <section>
      <h1 className="text-2xl font-semibold text-ink">Administration</h1>
      <p className="mt-2 max-w-2xl text-ink-muted">
        Manage organisations, users, roles, and projects.
      </p>

      <div className="mt-6 flex flex-col gap-8">
        <div>
          <h2 className="text-sm font-medium text-ink">Organisation</h2>
          <div className="mt-3">
            {organisations.loading ? (
              <LoadingState label="organisation" />
            ) : organisation ? (
              <div className="rounded-lg border border-rule p-4">
                <p className="text-sm text-ink">{organisation.name}</p>
                <p className="font-mono text-xs text-ink-subtle">
                  {organisation.slug}
                </p>
              </div>
            ) : (
              <ErrorState
                message={organisations.error ?? "No organisation was returned."}
                onRetry={organisations.reload}
              />
            )}
          </div>
        </div>

        <div>
          <h2 className="text-sm font-medium text-ink">Users</h2>
          <div className="mt-3">
            {users.loading ? (
              <LoadingState label="users" />
            ) : users.status === 403 ? (
              // Not an error to retry: this role simply cannot read users.
              <EmptyState message="Your role does not include permission to view users." />
            ) : users.error ? (
              <ErrorState message={users.error} onRetry={users.reload} />
            ) : users.data && users.data.items.length > 0 ? (
              <div className="overflow-x-auto rounded-lg border border-rule">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-rule bg-surface-raised text-xs uppercase tracking-wide text-ink-subtle">
                    <tr>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Email
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Name
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Roles
                      </th>
                      <th scope="col" className="px-4 py-2 font-medium">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.data.items.map((user) => (
                      <tr
                        key={user.id}
                        data-testid="admin-user-row"
                        className="border-b border-rule-subtle last:border-b-0"
                      >
                        <td className="px-4 py-2 text-ink">{user.email}</td>
                        <td className="px-4 py-2 text-ink-muted">
                          {user.full_name ?? "—"}
                        </td>
                        <td className="px-4 py-2 text-ink-muted">
                          {user.roles.length > 0
                            ? user.roles.join(", ").replaceAll("_", " ")
                            : "—"}
                        </td>
                        <td className="px-4 py-2 text-ink-muted">
                          {user.is_active ? "Active" : "Deactivated"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState message="No users in this organisation yet." />
            )}
          </div>
        </div>

        <p className="text-xs text-ink-subtle">
          Creating and editing users is available through the API; the management
          UI arrives with the administration console.
        </p>
      </div>
    </section>
  );
}
