"""SqlitePolicyStore: componente real de policy/budget para WI-56.

Corte 2 de la ADR-0016: extrae el cluster de SQL de tenant_policies y
run_budgets (4 metodos del Protocol ``PolicyStore``) de ``Storage``.
Mismo SQL, misma semantica, cero ediciones en callers: el facade
conserva delegados con firma explicita y ``policy_store()`` devuelve
la instancia cacheada de este componente.

La conexion es compartida con ``Storage`` (dueno del schema); el
componente no habla de migraciones ni de otras tablas.
"""

from __future__ import annotations

import sqlite3

from skillgraph.platform.ports import StoredBudget
from skillgraph.platform.storage import Storage, _row_to_stored_budget

__all__ = ["SqlitePolicyStore"]


class SqlitePolicyStore:
    """Implementacion real de ``PolicyStore`` sobre la conexion de
    ``Storage``: politicas de redaccion por tenant y presupuestos
    por Run."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    @property
    def _conn(self) -> sqlite3.Connection:
        """Conexion compartida con el ``Storage`` dueno del schema."""
        return self._storage._conn  # composicion interna acordada en ADR-0016

    def get_policy(self, *, tenant_id: str) -> str | None:
        """Devuelve la politica de redaccion del tenant, o None.

        None significa: no hay politica configurada explicitamente;
        el caller debe usar el default seguro ("metadata"). Asi la
        politica se aplica a TODOS los tenants aunque no la hayan
        configurado, sin necesidad de un INSERT en el seed.
        """
        row = self._conn.execute(
            "SELECT redaction_policy FROM tenant_policies WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return None if row is None else str(row["redaction_policy"])

    def upsert_policy(self, *, tenant_id: str, policy: str) -> None:
        """Crea o reemplaza la politica de redaccion del tenant.

        Idempotente (INSERT OR REPLACE sobre la PK). El caller
        debe haber validado `policy` con `validate_policy`
        (storage NO valida la politica; eso vive en el modulo
        `redaction` por la regla "Storage encapsula SQL, no reglas
        de negocio").
        """
        self._conn.execute(
            """
            INSERT OR REPLACE INTO tenant_policies
                (tenant_id, redaction_policy, updated_at)
            VALUES (?, ?, datetime('now'))
            """,
            (tenant_id, policy),
        )

    def upsert_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        max_visits: int | None,
        max_runtime_seconds: int | None,
        max_events: int | None,
    ) -> None:
        """Inserta o reemplaza el budget de un Run (idempotente).

        `None` significa "sin limite" para esa categoria. La PK sobre
        `run_id` + la politica REPLACE garantiza idempotencia aunque
        se llame dos veces con los mismos parametros (UAT-07):
        la UNIQUE constraint rechaza el duplicado si lo hubiera.
        """
        self._conn.execute(
            """
            INSERT OR REPLACE INTO run_budgets
                (run_id, tenant_id, project_id,
                 max_visits, max_runtime_seconds, max_events)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                tenant_id,
                project_id,
                max_visits,
                max_runtime_seconds,
                max_events,
            ),
        )

    def get_budget(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
    ) -> StoredBudget | None:
        """Devuelve el DTO de un RunBudget, o None si no existe.

        No lanza NotFoundError: ausencia de budget significa "sin
        limites" (compat con Runs anteriores a S4).

        WI-38 (R1 strict): devuelve ``StoredBudget`` (frozen + slots)
        en vez de ``dict[str, Any]``.
        """
        row = self._conn.execute(
            "SELECT max_visits, max_runtime_seconds, max_events, "
            "       tenant_id, project_id, run_id "
            "FROM run_budgets "
            "WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
            (tenant_id, project_id, run_id),
        ).fetchone()
        return None if row is None else _row_to_stored_budget(row)
