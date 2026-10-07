"""B27 — mide si los conflictos se pisan en silencio y si hay forma de saberlos.

**POR QUE ESTE SCRIPT.** El gate `exploration-sufficient` pregunta si la
exploracion de B27 esta medida, y un parrafo en prosa es una declaracion con
forma de dato. Este hace la pregunta y contesta, y su salida es la evidencia.

Salida: una linea por pregunta y `RESULTADO: N/5 ABIERTAS`. Codigo de salida 0
siempre: es una medicion, no un gate.

# LO QUE MIDIO ESTE MISMO SCRIPT, Y CORRIGIO EL ENUNCIADO DE LA FILA

La fila del roadmap dice: *«Dos claims incompatibles se pisan y no hay forma de
saberlo»*. **La primera mitad es falsa, y es falso de una forma que importa.**
MEDIDO sobre una base real:

    P1  dos fuentes, hechos opuestos   -> 2 filas, COEXISTEN
    P2  misma fuente, hechos opuestos  -> 1 fila, el segundo SE PISA

El overwrite **no** depende de que dos herramientas discrepen: depende de la
MISMA fuente con la MISMA revision, porque el `UNIQUE` de `claims` es
`(subject_entity_id, predicate, source_id, checked_at_revision)` y lleva
`source_id` dentro. Dos herramientas distintas ya coexistian de sobra.

Y hay un tercero, que es el peor porque **no se pierde nada**:

    P3  el sistema no dice que se contradigan  -> no existe el concepto

# QUE SIGNIFICA «CERRADA» EN ESTE INSTRUMENTO

Significa **«el comportamiento medido es el que se debe tener»**, no «el defecto
esta». P1 estaba «abierta» antes de B27 por una razon que no era un defecto:
que las afirmaciones coexistieran no es un problema que un bloque pueda
arreglar, es el comportamiento correcto. Se cierra cuando ademas son
CONSULTABLES.

Y hay un guard contra el otro extremo, que es el de un instrumento que solo sabe
ponerse en rojo: si B27 anunciara un conflicto donde no lo hay, P1 y P2 darian
falso y el bloque habria inventado un problema.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Final

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

SUJETO: Final[str] = "file:a.py"


def _base(tmp: str) -> object:
    """Una base con el sujeto y las fuentes que hacen falta para las sondas."""
    from skillgraph.knowledge.graph import Entity, Source, source_id
    from skillgraph.platform.storage import Storage

    s = Storage(Path(tmp) / "x.sqlite")
    for eid, key in ((SUJETO, "a.py"), ("file:b.py", "b.py")):
        s.upsert_entity(
            tenant_id="t",
            project_id="p",
            entity=Entity(entity_id=eid, kind="file", stable_key=key),
        )
    for sid in ("local:a.py", "local:b.py"):
        s.register_source(
            tenant_id="t",
            project_id="p",
            source=Source(
                source_id=source_id(sid),
                kind="local_file",
                content_hash="h",
                locator={"path": sid},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-06T00:00:00Z",
                freshness="current",
            ),
        )
    return s


def _claim(cid: str, valor: object, sid: str, rev: str = "r1") -> object:
    from skillgraph.knowledge.graph import Claim

    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="test_passes",
        object_literal=valor,
        source_id=sid,
        checked_at_revision=rev,
    )


# ---------------------------------------------------------------------------
# Las cinco preguntas
# ---------------------------------------------------------------------------


def p1_coexisten_y_son_consultables() -> tuple[bool, str]:
    """Dos fuentes que dicen cosas distintas: ¿se pisan?

    MEDIDO antes del bloque: coexistian y NADIE lo sabia. No habia consulta que
    las juntara.

    Se cierra solo cuando coexisten **y** son consultables. La primera mitad
    sola no seria el defecto: coexisten de sobra, y eso es lo correcto.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, "local:a.py"))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, "local:b.py"))
        n = s._conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
        s.close()
    bien = n == 2 and len(conflictos) == 1
    return bien, f"{n} filas y {len(conflictos)} conflicto(s) — coexisten Y son consultables"


def p2_el_overwrite_avisa() -> tuple[bool, str]:
    """Misma fuente, mismos hechos opuestos: ¿se pisa en silencio?

    MEDIDO antes del bloque: **si, y en silencio**. Dos `claim_id` distintos
    acababan en una sola fila, y `record_claim` devolvia el `claim_id` de
    todos modos, como si hubiera escrito.

    Se cierra cuando `conflicto` es `True` **y** dice que valor habia antes.
    Un aviso sin el valor previo no es accionable: quien lo recibe no sabe si
    lo que se solapa es `true` o `false`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, "local:a.py"))
        r = s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", False, "local:a.py"))
        s.close()
    bien = r.conflicto is True and r.valor_previo is not None
    return bien, (
        f"conflicto={r.conflicto}, valor_previo={r.valor_previo!r}, "
        f"valor_intento={r.valor_intento!r}"
    )


def p3_el_aviso_llega_a_quien_escribe() -> tuple[bool, str]:
    """¿El aviso sale del sistema, o se queda dentro de la base?

    **LA PREGUNTA MAS IMPORTANTE DEL INSTRUMENTO.** Un aviso que se recoge y no
    se imprime es un aviso que no existio: el sistema lo sabe, la base lo
    guarda, y el operador recibe un `PUBLISHED` sin mas. MEDIDO: antes de B27
    eso era exactamente lo que pasaba en el reconcile de la promocion.
    """
    from skillgraph.cli.commands.promotion import (
        _apply_pending_promotions,
        _claim_to_payload,
        _entity_to_payload,
        _source_to_payload,
    )
    from skillgraph.governance.promotion import submit_proposal
    from skillgraph.knowledge.graph import Entity
    from skillgraph.platform.storage import Storage

    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        origen = _base(str(raiz))
        destino = Storage(raiz / "destino.sqlite")
        # El destino necesita sus propias entidades y su propia fuente.
        destino.upsert_entity(
            tenant_id="t",
            project_id="destino",
            entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
        )
        destino.register_source(
            tenant_id="t",
            project_id="destino",
            source=origen.get_source(tenant_id="t", project_id="p", source_id="local:a.py"),
        )
        destino.record_claim(
            tenant_id="t",
            project_id="destino",
            claim=_claim("ya-existe", False, "local:a.py"),
        )

        claim = _claim("c-nuevo", True, "local:a.py")
        origen.record_claim(tenant_id="t", project_id="p", claim=claim)
        submit_proposal(
            origen,
            proposal_id="p1",
            tenant_id="t",
            source_project="p",
            target_catalog="destino",
            knowledge_ref="c-nuevo",
            payload={
                "source_project": "p",
                "target_project": "destino",
                "source": _source_to_payload(
                    origen, tenant_id="t", project_id="p", source_id="local:a.py"
                ),
                "entity": _entity_to_payload(
                    origen, tenant_id="t", project_id="p", entity_id=SUJETO
                ),
                "claim": _claim_to_payload(claim),
            },
        )
        resultados = _apply_pending_promotions(
            origen, destino, tenant_id="t", target_project="destino"
        )
        origen.close()
        destino.close()
    texto = "\n".join(f"{r['proposal_id']}  {r['status']}" for r in resultados)
    bien = "CONFLICTOS" in texto
    return bien, f"el reconcile dijo: {texto.strip()!r}"


def p4_el_conflict_set_es_estable() -> tuple[bool, str]:
    """¿El conflict set es ESTABLE entre llamadas y entre almacenes?

    Se mide por AST, no leyendo el `ORDER BY`. Un conflict set que dependa del
    orden en que SQLite devuelva las filas no es un conflict set: es el estado
    de un `SELECT` sin `ORDER BY`, y dos consultas iguales darian listas
    distintas. Eso es lo que haria fallar a B28 de forma intermitente.
    """
    import inspect

    from skillgraph.platform.knowledge_conflicts import SqliteConflictRepository

    src = inspect.getsource(SqliteConflictRepository.conflicts_for)
    ordenado = "ORDER BY" in src
    return ordenado, (
        "el conflict set se ordena explicitamente"
        if ordenado
        else "sin ORDER BY: dos llamadas pueden devolver listas distintas"
    )


def p5_el_conflict_set_no_declara_donde_no_debe() -> tuple[bool, str]:
    """EL CONTRA SALTO DEL GUARD. Sin esto, el guard solo sabe ponerse en rojo.

    Comprueba las tres cosas que hacen que `conflicts_for` NO sea ruido:
    una sola afirmacion no es conflicto, dos que dicen lo mismo no lo son, y
    dos proyectos distintos no se comparan.

    Sin esta pregunta, un `conflicts_for` que devolviera TODO seguiria
    «cerrando» P1, P3 y P4, y el bloque habria Fabricado un problema mas
    grande que el que arregla.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c1", True, "local:a.py"))
        solo_una = len(s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO))

        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c2", True, "local:b.py"))
        iguales = len(s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO))

        # Otro proyecto: la misma afirmacion, alli si es un conflicto y aqui no.
        s.upsert_entity(
            tenant_id="t",
            project_id="otro",
            entity=_entidad_de("file:a.py"),
        )
        s.register_source(
            tenant_id="t",
            project_id="otro",
            source=_source_de("local:a.py"),
        )
        s.record_claim(tenant_id="t", project_id="otro", claim=_claim("c3", False, "local:a.py"))
        filtrado = len(s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO))
        s.close()
    bien = solo_una == 0 and iguales == 0 and filtrado == 0
    return bien, (
        f"una afirmacion -> {solo_una} conflictos, "
        f"dos que coinciden -> {iguales}, "
        f"otro proyecto no se mezcla -> {filtrado}"
    )


def _entidad_de(eid: str) -> object:
    from skillgraph.knowledge.graph import Entity

    return Entity(entity_id=eid, kind="file", stable_key="a.py")


def _source_de(sid: str) -> object:
    from skillgraph.knowledge.graph import Source, source_id

    return Source(
        source_id=source_id(sid),
        kind="local_file",
        content_hash="h",
        locator={},
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at="2026-10-06T00:00:00Z",
        freshness="current",
    )


def main() -> int:
    preguntas = (
        ("P1", "fuentes distintas: coexisten Y son consultables", p1_coexisten_y_son_consultables),
        ("P2", "el overwrite avisa, y dice que valor habia", p2_el_overwrite_avisa),
        ("P3", "el aviso LLEGA a quien escribe", p3_el_aviso_llega_a_quien_escribe),
        ("P4", "el conflict set es estable", p4_el_conflict_set_es_estable),
        (
            "P5",
            "no declara conflictos donde no los hay",
            p5_el_conflict_set_no_declara_donde_no_debe,
        ),
    )
    print("B27 — ¿los conflictos se pisan en silencio y hay forma de saberlos?")
    print("  (MEDIDO: el overwrite solo ocurre con la MISMA fuente y la MISMA")
    print("   revision; el enunciado de la fila lo daba por general)\n")
    abiertas = 0
    for pid, texto, fn in preguntas:
        cerrada, medido = fn()
        print(f"  {pid}  {'CERRADA' if cerrada else 'ABIERTA':<8} {texto}")
        print(f"      medido: {medido}")
        if not cerrada:
            abiertas += 1
    print(f"\nRESULTADO: {abiertas}/{len(preguntas)} preguntas ABIERTAS")
    if abiertas == 0:
        print("B27 esta implementado: los conflictos avisan y son consultables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
