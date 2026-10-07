"""WI-B32 — que se puede responder de la ascendencia HOY, antes de escribir una linea.

Este script no es codigo de produccion: es el instrumento que mide el hueco
que B32 viene a cerrar. Se ejecuta sobre un repo real y sobre una base real,
y su salida es lo que decide el alcance del bloque.

Se ejecuta con:
    uv run python scripts/measure_b32_git_history.py

Las preguntas son las del roadmap, escritas como se le harian a alguien:

  P1. ¿Hay un camino de un CLAIM al commit del que vino?
  P2. ¿Ese camino se puede recorrer al reves — commit -> claims —?
  P3. ¿Se puede pedir la ASCENDENCIA de un commit (su padre, y el padre del
      padre)?  Sin esto no hay cadena, hay un punto.
  P4. ¿Se puede saber que claims nacieron DESPUES de un commit dado?
  P5. ¿Dos revisiones que son commits distintos tienen un ORDEN que se pueda
      consultar sin ser este repo?

Y una sexta, que es la que la fila del roadmap llama «ni por que»:

  P6. ¿Dado un claim, hay algo que diga POR QUE se afirmo, mas alla del
      `source_id`?

La salida es lo que hay, con la respuesta literal de `AttributeError` cuando
la capacidad no existe: una capacidad ausente se responde «no existe», y
decirlo en voz alta es lo que evita escribir el bloque describiendo un
problema que no existe.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from skillgraph.knowledge.knowledge_controller import KnowledgeController  # noqa: E402
from skillgraph.platform.storage import Storage  # noqa: E402

TENANT = "default"
PROJECT = "demo"


def _responde(nombre: str, fn) -> None:
    try:
        valor = fn()
    except Exception as exc:  # el instrumento MIDE, no juzga: no reescriba esto
        print(f"  {nombre}: NO ({type(exc).__name__})")
        return
    if valor is None:
        print(f"  {nombre}: NO (devuelve None)")
    elif isinstance(valor, (list, tuple, dict)) and not valor:
        print(f"  {nombre}: NO (vacio)")
    else:
        resumen = str(valor)
        print(f"  {nombre}: SI ({resumen[:88]})")


def main() -> int:
    print("=" * 74)
    print("WI-B32 — ascendencia de commits: que existe HOY")
    print("=" * 74)

    with tempfile.TemporaryDirectory(prefix="b32_") as tmp:
        base = Path(tmp)
        storage = Storage(base / "p.sqlite")
        ctl = KnowledgeController(knowledge=storage, tenant_id=TENANT, project_id=PROJECT)

        print("\n[esquema] ¿la tabla guarda el SHA y hay indice por el?")
        filas = storage._conn.execute(
            "SELECT name FROM pragma_table_info('sources') WHERE name LIKE 'git_%'"
        ).fetchall()
        print(f"  columnas git_* en sources: {[f[0] for f in filas]}")
        idx = storage._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sources'"
        ).fetchall()
        print(f"  indices sobre sources: {[f[0] for f in idx]}")

        print("\n[preguntas] sobre una base con un claim de verdad")
        from skillgraph.knowledge.graph import Claim, Entity, Source

        ctl.register_source(
            source=Source(
                source_id="s-1",
                kind="git_commit",
                content_hash="h1",
                locator={"vcs": "git", "repo_root": "/tmp/x", "commit_sha": "abc123"},
                git_commit_sha="abc123",
                git_tree_sha="t1",
                working_tree_status=None,
                checked_at="2026-10-07T09:00:00+00:00",
                freshness="fresh",
            )
        )
        eid = ctl.upsert_entity(entity=Entity(entity_id="e-1", kind="File", stable_key="src/a.py"))
        cid = ctl.record_claim(
            claim=Claim(
                claim_id="c-1",
                subject_entity_id=eid,
                predicate="line_count",
                object_literal=10,
                source_id="s-1",
                assertion_origin="observed",
                checked_at_revision="abc123",
            )
        )
        print(f"  claim registrado: {cid}")

        _responde(
            "P1 claim -> source (el commit del que vino)",
            lambda: (
                storage.get_claim(tenant_id=TENANT, project_id=PROJECT, claim_id="c-1").source_id
            ),
        )
        _responde(
            "P2 commit -> claims (al reves)",
            lambda: [
                r[0]
                for r in storage._conn.execute(
                    "SELECT claim_id FROM claims JOIN sources USING (source_id)"
                    " WHERE sources.git_commit_sha = 'abc123'"
                ).fetchall()
            ],
        )
        _responde(
            "P3 ascendencia de un commit (padre, y el padre del padre)",
            lambda: getattr(storage, "commit_parents", None),
        )
        _responde(
            "P4 claims que nacieron DESPUES de un commit",
            lambda: getattr(storage, "claims_since_commit", None),
        )
        _responde(
            "P5 orden entre dos revisiones-commit",
            lambda: getattr(storage, "orden_de_revisiones", None),
        )
        _responde(
            "P6 por que se afirmo el claim (mas alla del source_id)",
            lambda: getattr(storage, "por_que", None),
        )

        print("\n[el otro reloj] revision_registro, que NO es git")
        from skillgraph.platform.revision_registry import SqliteRevisionRegistry

        reg = SqliteRevisionRegistry(storage._conn)
        reg.registrar("commit-sha-real-1234")
        reg.registrar("commit-sha-real-1234")
        reg.registrar("otro-commit-9999")
        filas = [
            (r["seq"], r["revision"])
            for r in storage._conn.execute(
                "SELECT seq, revision FROM revision_registro ORDER BY seq"
            ).fetchall()
        ]
        print(f"  revision_registro: {filas}")
        mismo = [f[0] for f in filas if f[1] == filas[0][1]]
        print(
            f"  el MISMO sha registrado dos veces sigue siendo UN seq: "
            f"{filas[0][1]!r} -> seq {mismo}"
        )
        print("  esto es ORDEN DE OBSERVACION local, no ascendencia. Un reloj que")
        print("  no puede decir si A es padre de B, solo que A se vio antes que B.")
        print("  El nombre del puerto lo declara; por eso B32 necesita OTRO reloj.")

        storage.close()

    print("\n[fuera de la base] ¿hay un puerto de ascendencia en el codigo?")
    from skillgraph.platform.ports import revisions

    print(f"  puertos de revision: {[n for n in dir(revisions) if not n.startswith('_')]}")
    for simbolo in ("GitHistory", "CommitHistory", "CommitLineage"):
        print(f"  {simbolo} definido: {any(simbolo in m for m in _modulos())}")

    print("\n[fuera de la base] ¿el nucleo importa git?")
    try:
        import dulwich  # noqa: F401

        print("  dulwich: disponible (dependencia principal)")
    except ImportError:
        print("  dulwich: NO disponible")

    print()
    return 0


def _modulos() -> list[str]:
    from skillgraph.platform.ports import revisions as r

    return [m for m in dir(r) if not m.startswith("_")]


if __name__ == "__main__":
    raise SystemExit(main())
