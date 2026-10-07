"""``SqliteRevisionRegistry``: la implementación del puerto de revisiones.

R0 lo sacó del dominio. Los helpers vivían en
`knowledge/graph.py` como funciones libres que recibían un `cursor`, y
`platform/` los importaba —la frontera estaba invertida—.

Aquí viven como **un objeto** que recibe la conexión, que es donde puede
hablar SQL sin que el dominio sepa que existe.

# POR QUÉ UN `AUTOINCREMENT` Y NO UN MAX+1

Con `MAX(seq)+1`, dos conexiones que registraran revisiones a la vez
podrían leer el mismo máximo y escribir el mismo `seq`; entonces dos
ventanas distintas dirían lo mismo sobre el mismo instante, que es peor
que no tener orden. El `UNIQUE` sobre `revision` evita el otro extremo,
que es dos filas con la misma revisión y distinto `seq`.

# POR QUÉ `registrar` DEVUELVE UN `int` Y NO UN `str`

El `seq` es lo que se compara; la revisión es lo que se guarda.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SqliteRevisionRegistry:
    """Implementacion SQLite de :class:`RevisionRegistry`.

    **NO ES UN ACUMULADOR**: es una fachada stateless sobre la tabla
    `revision_registro`. Se puede construir dos veces con la misma conexión
    y obtener el mismo resultado, que es lo que hace falta para que la
    comparacion de ventanas de vigencia sea pura.
    """

    conn: sqlite3.Connection

    def registrar(self, revision: str) -> int:
        """Devuelve el `seq` de `revision`, creándolo la primera vez.

        **IDEMPOTENTE POR EL `UNIQUE` DE `revision`, NO POR CÓDIGO.** Es la
        misma lección de `runtime_events.event_id` (ADR de idempotencia):
        la garantía la da la constraint, no el `if not exists`. Por eso el
        `INSERT` se puede repetir sin efecto y el `SELECT` posterior decide.
        """
        fila = self.conn.execute(
            "SELECT seq FROM revision_registro WHERE revision = ?", (revision,)
        ).fetchone()
        if fila is not None:
            return int(fila[0])
        self.conn.execute("INSERT INTO revision_registro (revision) VALUES (?)", (revision,))
        fila = self.conn.execute(
            "SELECT seq FROM revision_registro WHERE revision = ?", (revision,)
        ).fetchone()
        return int(fila[0])

    def seq_de(self, revision: str | None) -> int | None:
        """El `seq` de `revision`, o `None` si este store no la ha visto."""
        if revision is None:
            return None
        fila = self.conn.execute(
            "SELECT seq FROM revision_registro WHERE revision = ?", (revision,)
        ).fetchone()
        return None if fila is None else int(fila[0])


__all__ = ["SqliteRevisionRegistry"]
