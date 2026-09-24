"""Tests de caracterizacion para H9-LIMITACION-7 V6 (`record_claim`).

Este archivo es posterior al slice 1.b. Su proposito es caracterizar
el contrato vigente de `Storage.record_claim` con `evidence_ids`
pobladas (path multi-statement no inventariado en el slice 1).

Hipotesis a verificar:

  - `record_claim(claim=Claim(..., evidence_ids=(ev1, ev2, ev3)))`
    ejecuta 1 INSERT en `claims` + N INSERTs en `claim_evidence`.

  - Si el INSERT numero N+1 falla, lo escrito en los primeros N
    INSERTs queda en disco (autocommit de `isolation_level=None`)
    -> el operador observa un claim parcialmente confirmado.

  - El resultado es directamente analogo a V4 (`record_trace`),
    donde el fix (`_atomic()`) fue necesario para evitar el
    mismo estado orfano.

Resultado esperado:

  - T20 RED si la hipotesis es correcta: hay un bug no resuelto
    que precisa migrar `record_claim` a `_atomic()`, igual que V4.

  - T20 GREEN solo si una de las dos condiciones se cumple:

    (a) La hipotesis es incorrecta: la implementacion actual ya
        garantiza rollback sin `_atomic()`. Entonces se documenta
        el descubrimiento y V6 queda excluido por caracterizacion.

    (b) El estado parcialmente persistido es recuperable de forma
        trivial via reintento idempotente. Entonces se documenta
        y V6 queda excluido por idempotencia.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.knowledge.graph import Claim, Entity, Evidence, Source
from skillgraph.platform.storage import Storage
from tests.test_h9_limitacion_7_slice1 import PROJECT, TENANT, FaultyStorage

# ---------------------------------------------------------------------------
# Constantes y datos de prueba
# ---------------------------------------------------------------------------

CLAIM_ID = "claim-v6-1"
SUBJECT_ENTITY_ID = "file:src/foo.py"
SOURCE_ID = "local:src/foo.py"
EVIDENCE_IDS: tuple[str, ...] = ("ev-v6-1", "ev-v6-2", "ev-v6-3")


def _seed_source_entity_and_evidences(s: Storage) -> None:
    """Pre-registra Source + Entity + 3 Evidences (FK targets).

    Replica los helpers `_src()`/`_ent()` de `tests/test_knowledge_storage.py`
    sin acoplamiento a ese archivo.
    """
    s.register_source(
        tenant_id=TENANT,
        project_id=PROJECT,
        source=Source(
            source_id=SOURCE_ID,
            kind="local_file",
            content_hash="abc123",
            locator={"path": "src/foo.py"},
            git_commit_sha=None,
            git_tree_sha=None,
            working_tree_status=None,
            checked_at="2026-01-01T00:00:00Z",
            freshness="fresh",
        ),
    )
    s.upsert_entity(
        tenant_id=TENANT,
        project_id=PROJECT,
        entity=Entity(entity_id=SUBJECT_ENTITY_ID, kind="file", stable_key="src/foo.py"),
    )
    for evidence_id in EVIDENCE_IDS:
        s.record_evidence(
            tenant_id=TENANT,
            project_id=PROJECT,
            evidence=Evidence(
                evidence_id=evidence_id,
                kind="metric",
                content={"v": 1},
                source_id=SOURCE_ID,
                observed_at="2026-01-01",
            ),
        )


def _claim_with_three_evidences() -> Claim:
    """Claim listo para el path multi-statement de record_claim."""
    return Claim(
        claim_id=CLAIM_ID,
        subject_entity_id=SUBJECT_ENTITY_ID,
        predicate="line_count",
        object_literal=42,
        source_id=SOURCE_ID,
        evidence_ids=EVIDENCE_IDS,
        extraction_method="manual",
        extractor_version="skillgraph-rules/0.1.0",
        checked_at_revision="rev-v6-1",
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "limitacion7_v6.sqlite"


# ---------------------------------------------------------------------------
# T20 — Caracterizacion del contrato de `record_claim`
# ---------------------------------------------------------------------------


class TestT20RecordClaimRollback:
    """V6: `record_claim()` con `evidence_ids` no vacias ejecuta:

      - 1 INSERT en `claims`
      - N INSERTs en `claim_evidence` (uno por cada `evidence_id`)

    Con `isolation_level=None`, un fallo en el INSERT numero k
    (con k > 1) deja en disco las escrituras previas sin rollback.
    Esta clase comprueba si esa escritura parcial ocurre o si
    la implementacion ya garantiza atomicidad.
    """

    def test_record_claim_rolls_back_when_middle_evidence_fails(self, db_path: Path) -> None:
        """Hipotesis: si falla el 3er INSERT (durante el 2do evidence
        link), queda el INSERT del claim (1) + el INSERT del 1er
        evidence link (2) confirmados, y el resto fallido.

        Sentencias esperadas dentro de `record_claim`:
          1) INSERT INTO claims
          2) INSERT INTO claim_evidence (ev-v6-1)
          3) INSERT INTO claim_evidence (ev-v6-2) <- falla aqui
          4) INSERT INTO claim_evidence (ev-v6-3)  (no llega)

        Tras cerrar la conexion y reabrir:

          - Si T20 es RED: la BD contiene 1 fila en `claims` con
            `claim_id='claim-v6-1'` y 1 fila en `claim_evidence`
            con `(claim-v6-1, ev-v6-1)`. Estado parcialmente
            confirmado, análogo a V4.

          - Si T20 es GREEN: la BD no contiene ni la fila en
            `claims` ni ninguna en `claim_evidence`. La API ya
            garantiza rollback (lo que requiere que `record_claim`
            use `_atomic()` o equivalente).
        """
        # --- Setup + Fault injection en el mismo Storage: reutilizamos
        # la migracion inicial (corrida con _fault_enabled=False, no
        # incrementa counter) y sembramos FK targets (source, entity,
        # 3 evidences). Despues reseteamos counter y activamos fault
        # para que la siguiente `record_claim` falle en su 3a execute.
        # patron identico a T17 del slice 1.b (test_h9_limitacion_7_slice1).
        faulty = FaultyStorage(db_path)
        _seed_source_entity_and_evidences(faulty)
        faulty._call_counter = 0
        faulty._fault_enabled = True
        faulty._fail_on_call = 3

        with pytest.raises(RuntimeError, match="fault injection"):
            faulty.record_claim(
                tenant_id=TENANT,
                project_id=PROJECT,
                claim=_claim_with_three_evidences(),
            )
        faulty.close()

        # --- Verificacion independiente: NUEVA conexion para no
        # reutilizar estado transaccional del wrapper. ---
        s = Storage(db_path)
        claim_rows = s._conn.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (CLAIM_ID,)
        ).fetchall()
        link_rows = s._conn.execute(
            "SELECT * FROM claim_evidence WHERE claim_id = ?", (CLAIM_ID,)
        ).fetchall()
        s.close()

        # Decision: si la API cumple su contrato de "registro del
        # conjunto", ambos selects deben devolver 0 filas. Si no,
        # hay escrituras parcialmente confirmadas.
        assert len(claim_rows) == 0, (
            f"V6 RED: `record_claim` confirmo parcialmente. "
            f"La fila del claim quedo persistida sin rollback: "
            f"{claim_rows}"
        )
        assert len(link_rows) == 0, (
            f"V6 RED: `record_claim` confirmo parcialmente. "
            f"Quedaron {len(link_rows)} filas en `claim_evidence` "
            f"huérfanas de un rollback: {link_rows}"
        )
        # Si llegamos aqui sin raise, T20 es GREEN: el contrato se
        # cumple. El motivo concreto (atomic via _atomic, o exclusion
        # por otra razon) se documenta al cierre del slice V6.
