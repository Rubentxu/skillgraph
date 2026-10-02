"""WI-76 — Los shims de WI-56 corte 3 se EJECUTAN, no solo se inspeccionan.

Por que este fichero existe
---------------------------
La retrospectiva del ciclo anterior (WI-72..WI-75) encontro un falso
exito: dos clases de test garantizaban que los shims de compatibilidad de
`platform/row_mappers.py` estan vivos, pero ninguno los ejecutaba.

- `test_wi60_knowledge_mappers_extraction.py::test_storage_shim_import_keeps_working`
  hace `inspect.getsource(storage._row_to_source)` y comprueba que la
  linea de import aparece en el TEXTO. No invoca nada.
- `test_wi65_storage_schema_mappers.py::TestShimPreserved` trabaja por AST:
  mira si los nombres que el modulo construye en runtime estan importados.
  Tampoco ejecuta nada.

Medido 2026-10-02: invirtiendo los argumentos del `return` de los 7 shims
(`row_to_source(json, row)` en vez de `row_to_source(row, json)`, que
reventaria con TypeError si alguien los llamara), la suite completa queda
VERDE: **2225 passed**. Siete funciones publicas, declaradas en
`storage.__all__` y en `MAPPER_NAMES`, pueden estar rotas sin que nada se
entere.

Este fichero convierte la garantia en real: llama a cada shim con una fila
y compara el resultado con el del mapper de verdad. Si el shim devuelve
otra cosa —o revienta, o devuelve None— el test falla.

No es un test de estilo: el oraculo es diferencial. `shim(fila)` tiene que
producir exactamente el mismo ADT/DTO que `mapper_real(fila)`.

Lo que NO se hace aqui
----------------------
Borrar los shims. El re-export de `storage` esta justificado en el
docstring de `test_wi65` solo para tres simbolos (`_SCHEMA_SQL`,
`_row_to_stored_event`, `_row_to_stored_budget`, `_uid`); los otros siete
no tienen justificacion documentada y no los llama nadie en el repo. Aun
asi, los siete estan en `storage.__all__` y en `MAPPER_NAMES`, que es
superficie publica: eliminarlos es un cambio de contrato que pide ADR, no
un cleanup. Queda como decision del operador. Lo que si es un defecto
-Y no una opinion- es que nadie los ejecuta, y eso se corrige aqui.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from skillgraph.platform import knowledge_mappers, row_mappers

# Filas minimas: cada mapper solo usa `row["columna"]`, asi que un dict
# cumple el duck-type de `sqlite3.Row` sin montar una base de datos.
ROW_SOURCE = {
    "source_id": "local:src/foo.py",
    "kind": "local_file",
    "content_hash": "h1",
    "locator_json": '{"path": "src/foo.py"}',
    "git_commit_sha": "c0ffee",
    "git_tree_sha": "deadbeef",
    "working_tree_status_json": '{"dirty": true}',
    "checked_at": "2026-01-01T00:00:00Z",
    "freshness": "fresh",
}

ROW_EVIDENCE = {
    "evidence_id": "ev1",
    "kind": "manual",
    "content_json": '{"line": 42}',
    "source_id": "local:src/foo.py",
    "observed_at": "2026-01-02T00:00:00Z",
}

ROW_STORED_EVIDENCE = {
    "evidence_id": "ev1",
    "tenant_id": "t1",
    "project_id": "p1",
    "kind": "manual",
    "content_json": '{"line": 42}',
    "source_id": "local:src/foo.py",
    "observed_at": "2026-01-02T00:00:00Z",
}

ROW_CLAIM = {
    "claim_id": "c1",
    "subject_entity_id": "file:src/foo.py",
    "predicate": "line_count",
    "object_literal_json": "42",
    "source_id": "local:src/foo.py",
    "extraction_method": "manual",
    "extractor_version": "skillgraph-rules/0.1.0",
    "checked_at_revision": "rev1",
    "stale": 0,
}

ROW_STORED_CLAIM = {
    **ROW_CLAIM,
    "tenant_id": "t1",
    "project_id": "p1",
    "evidence_ids_csv": "ev1,ev2",
}

ROW_RESOURCE = {
    "uid": "res1",
    "tenant_id": "t1",
    "project_id": "p1",
    "api_version": "v1",
    "kind": "brick",
    "namespace": "software",
    "name": "name",
    "resource_version": "1",
    "generation": "1",
    "spec_json": "{}",
    "status_json": "{}",
    "created_at": "2026-01-03T00:00:00Z",
}

ROW_RELATION = {
    "uid": "rel1",
    "tenant_id": "t1",
    "project_id": "p1",
    "source_uid": "res1",
    "target_uid": "res2",
    "kind": "depends_on",
    "properties_json": "{}",
}

# (nombre del shim, nombre del mapper real, fila, argumentos extra del real)
SHIMS: tuple[tuple[str, str, dict[str, Any], tuple[Any, ...]], ...] = (
    ("_row_to_source", "row_to_source", ROW_SOURCE, (json,)),
    ("_row_to_evidence", "row_to_evidence", ROW_EVIDENCE, (json,)),
    ("_row_to_stored_evidence", "row_to_stored_evidence", ROW_STORED_EVIDENCE, (json,)),
    ("_row_to_claim", "row_to_claim", ROW_CLAIM, ([], json)),
    ("_row_to_stored_claim", "row_to_stored_claim", ROW_STORED_CLAIM, (json,)),
    ("_row_to_resource", "row_to_resource", ROW_RESOURCE, ()),
    ("_row_to_relation", "row_to_relation", ROW_RELATION, ()),
)

SHIM_NAMES = tuple(name for name, _, _, _ in SHIMS)


class TestShimsActuallyRun:
    """El contrato de WI-60 era "el shim es un wrapper, no el mapper".

    Aqui se cumple de verdad: se invoca y se compara con el mapper.
    """

    @pytest.mark.parametrize("shim_name,real_name,row,extra", SHIMS, ids=SHIM_NAMES)
    def test_shim_matches_real_mapper(
        self,
        shim_name: str,
        real_name: str,
        row: dict[str, Any],
        extra: tuple[Any, ...],
    ) -> None:
        shim = getattr(row_mappers, shim_name)
        real = getattr(knowledge_mappers, real_name)

        expected = real(row, *extra)
        got = shim(row)

        assert got is not None, f"{shim_name} devolvio None: el wrapper no llega al mapper"
        assert type(got) is type(expected), (
            f"{shim_name} devolvio {type(got).__name__}, se esperaba {type(expected).__name__}"
        )
        assert got == expected, (
            f"{shim_name} diverge de {real_name}:\n  shim={got!r}\n  real={expected!r}"
        )

    @pytest.mark.parametrize("shim_name,real_name,row,extra", SHIMS, ids=SHIM_NAMES)
    def test_shim_is_not_trivially_empty(
        self,
        shim_name: str,
        real_name: str,
        row: dict[str, Any],
        extra: tuple[Any, ...],
    ) -> None:
        """Evita que la igualdad anterior se cumpla comparando dos cosas vacias.

        Exige que el DTO transporte al menos un valor distinguible, tomado
        de la fila de entrada.
        """
        shim = getattr(row_mappers, shim_name)
        got = shim(row)

        assert got is not None, f"{shim_name} devolvio None"
        assert repr(got) not in {"None", "{}", "()"}, f"{shim_name} devolvio un DTO vacio: {got!r}"
        assert len(repr(got)) > 20, f"{shim_name} devolvio algo trivial: {got!r}"
