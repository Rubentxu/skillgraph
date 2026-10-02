"""WI-87: el vocabulario de estados tiene una sola fuente (ADR-0015).

El defecto que este archivo cubre no es una discrepancia *hoy*: hoy el
``CHECK`` de SQLite y ``PROMOTION_STATUSES`` coinciden, porque los dos
están escritos a mano con los mismos cuatro valores. El defecto es que
**pueden** divergir sin que nada lo note, y que el unico test que
declaraba cubrir el vinculo comparaba el valor contra una copia de si
mismo sin leer el DDL.

Por eso hay dos tipos de comprobacion aqui, y no se sustituyen:

1. **Igualdad** (``test_*_matches_*``): el invariante. Si el conjunto
   derivado y el DDL dicen cosas distintas, falla. Es lo que importa.
2. **Derivacion** (``test_ddl_*_is_not_hand_written``): lee el AST de
   ``schema.py`` y falla si el DDL vuelve a llevar el vocabulario escrito
   a mano. Una igualdad se puede cumplir a mano; esta no.

La igualdad sola admite la respuesta incorrecta —"estan iguales, asi que
bien"— implementada a mano. La derivacion sola no detecta que los valores
divorguen. Juntas cierran las dos.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import get_args

import pytest

from skillgraph.core.runtime_types import (
    NON_TERMINAL_RUN_STATES,
    PROMOTION_STATUSES,
    TERMINAL_RUN_STATES,
    PromotionStatus,
    RunState,
    is_terminal_run_state,
)

SCHEMA_PY = Path(__file__).resolve().parents[1] / "src" / "skillgraph" / "platform" / "schema.py"

CHECK_RE = re.compile(r"CHECK\s*\(\s*status\s+IN\s*\(([^)]*)\)", re.IGNORECASE)


def _check_statuses_from_ddl() -> frozenset[str]:
    """Extrae los estados del CHECK de promotion_outbox del DDL real."""
    from skillgraph.platform.schema import SCHEMA_SQL

    match = CHECK_RE.search(SCHEMA_SQL)
    assert match is not None, "no se encontro CHECK (status IN (...)) en SCHEMA_SQL"
    return frozenset(re.findall(r"'([^']+)'", match.group(1)))


def _string_literals_in_schema() -> list[str]:
    """Todos los literales de cadena del AST de schema.py."""
    tree = ast.parse(SCHEMA_PY.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


class TestPromotionVocabularyIsDerived:
    """PROMOTION_STATUSES sale de su Literal, no de una lista a mano."""

    def test_constant_is_the_whole_literal(self) -> None:
        assert frozenset(get_args(PromotionStatus)) == PROMOTION_STATUSES

    def test_ddl_check_matches_constant(self) -> None:
        assert _check_statuses_from_ddl() == PROMOTION_STATUSES

    def test_ddl_check_is_not_hand_written(self) -> None:
        """El DDL no debe volver a llevar el vocabulario escrito a mano.

        Es la comprobacion que el test anterior no puede hacer: dos
        listas escritas a mano pueden coincidir hoy y divergir manana.
        """
        offenders = [lit for lit in _string_literals_in_schema() if "IN_PROGRESS" in lit]
        assert offenders == [], (
            "schema.py lleva el vocabulario de promocion escrito a mano "
            f"({len(offenders)} literal(es)). Debe derivarlo de "
            "core.runtime_types.PROMOTION_STATUSES."
        )

    def test_schema_version_unchanged(self) -> None:
        """El conjunto de valores aceptados no cambia: no hay migracion."""
        from skillgraph.platform.schema import SCHEMA_VERSION

        assert SCHEMA_VERSION == 1

    def test_database_rejects_a_status_outside_the_vocabulary(self) -> None:
        """El CHECK lo hace cumplir SQLite, no solo el texto.

        Si esto pasara, el texto y la base de datos habrian divergido.
        """
        from skillgraph.platform.storage import Storage

        storage = Storage(":memory:")
        try:
            storage._conn.execute(
                "INSERT INTO promotion_outbox (proposal_id, idempotency_key, "
                "tenant_id, source_project, target_catalog, knowledge_ref, "
                "payload_json, status) VALUES (?,?,?,?,?,?,?,?)",
                ("p1", "k1", "t1", "src", "cat", "kr", "{}", "NOT_A_STATUS"),
            )
            storage._conn.commit()
        except Exception as exc:
            assert "CHECK" in str(exc) or "constraint" in str(exc).lower()
        else:
            pytest.fail("SQLite acepto un status fuera de PROMOTION_STATUSES")

    @pytest.mark.parametrize("status", sorted(PROMOTION_STATUSES))
    def test_database_accepts_every_status_of_the_vocabulary(self, status: str) -> None:
        from skillgraph.platform.storage import Storage

        storage = Storage(":memory:")
        storage._conn.execute(
            "INSERT INTO promotion_outbox (proposal_id, idempotency_key, "
            "tenant_id, source_project, target_catalog, knowledge_ref, "
            "payload_json, status) VALUES (?,?,?,?,?,?,?,?)",
            (f"p-{status}", f"k-{status}", "t1", "src", "cat", "kr", "{}", status),
        )
        storage._conn.commit()


class TestRunStatePartition:
    """NON_TERMINAL y TERMINAL particionan RunState exactamente."""

    def test_partition_is_exhaustive(self) -> None:
        assert frozenset(get_args(RunState)) == NON_TERMINAL_RUN_STATES | TERMINAL_RUN_STATES

    def test_partition_is_disjoint(self) -> None:
        assert not (NON_TERMINAL_RUN_STATES & TERMINAL_RUN_STATES)

    def test_non_terminal_is_derived_by_complement(self) -> None:
        """La polaridad: se declara lo terminal, lo demas queda vivo.

        Anadir un estado a RunState lo hace reanudable sin tocar otro
        fichero. UAT-06 depende de esto: un estado no listado no se
        encuentra en find_active_run() y el CLI crea un segundo run.
        """
        assert frozenset(get_args(RunState)) - TERMINAL_RUN_STATES == NON_TERMINAL_RUN_STATES

    def test_an_unknown_state_is_outside_the_vocabulary(self) -> None:
        """Un estado que no esta en RunState no pertenece al dominio.

        `RunState` es una ADT **cerrada** (AGENTS.md 2.1): anadir un valor
        es un cambio de contrato que exige ADR. Por eso "un estado nuevo
        es reanudable" hay que entenderlo con precision — vale para un
        valor *anadido* a `RunState`, porque la derivacion por
        complemento lo recoge; no vale para un valor arbitrario, que
        sencillamente no es un estado.

        La propiedad que importa la cubre
        `test_non_terminal_is_derived_by_complement`.
        """
        assert "PAUSED" not in TERMINAL_RUN_STATES
        assert "PAUSED" not in NON_TERMINAL_RUN_STATES

    def test_terminal_helper_agrees_with_the_partition(self) -> None:
        """Sobre el vocabulario de RunState, ambos lados son exactos.

        Comprueba que el helper que ya existia y el conjunto derivado no
        se contradicen para ningun estado del dominio.
        """
        for state in get_args(RunState):
            assert is_terminal_run_state(state) == (state in TERMINAL_RUN_STATES)
            assert is_terminal_run_state(state) != (state in NON_TERMINAL_RUN_STATES)
