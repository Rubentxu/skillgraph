"""Subcomandos `sg knowledge` (WI-54 corte 5, ADR-0018).

Quinto corte del estrangulamiento H-02: los 5 handlers
`cmd_knowledge_*` salen de `cli/runner.py` verbatim.
`_open_known_project` es compartida (3 usos fuera del cluster) y vive
en `cli.support`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from skillgraph.cli.support import EXIT_OK, exit_para, resolve_project
from skillgraph.core.errors import ParseError, SkillGraphError
from skillgraph.core.recipe import ContextRecipe
from skillgraph.knowledge.authority import Resolution
from skillgraph.knowledge.context_controller import (
    ContextController,
    OutcomeTracer,
)
from skillgraph.knowledge.knowledge_controller import KnowledgeController
from skillgraph.platform.paths import DEFAULT_TENANT, resolve_data_root
from skillgraph.platform.storage import Storage


@contextmanager
def _open_known_project(
    args: argparse.Namespace,
    project: str,
) -> Iterator[tuple[str, str, Storage]]:
    """Valida el proyecto y posee el Storage durante el bloque `with`.

    Raises:
        FileNotFoundError: si el proyecto no esta registrado en el
            catalog (con mensaje legible para el operador).
    """
    p, err = resolve_project(args, project)
    if err is not None:
        data_root = resolve_data_root(args.data_root)
        raise FileNotFoundError(
            f"proyecto {project!r} no encontrado en el catalog "
            f"(tenant={DEFAULT_TENANT!r}, data_root={data_root}); "
            f"crealo primero con 'sg project create <name>'"
        )
    storage = Storage(Path(p["db_path"]))
    try:
        yield p["tenant_id"], project, storage
    finally:
        storage.close()


def cmd_knowledge_stale(args: argparse.Namespace) -> int:
    """Lista Claims stale del proyecto."""

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        stale = ctl.list_stale_claims()
        print(f"stale claims ({len(stale)}):")
        for c in stale:
            print(f"  - {c.claim_id}  {c.predicate}={c.object_literal} stale=true")
        return EXIT_OK


def cmd_knowledge_invalidate(args: argparse.Namespace) -> int:
    """Invalida Claims dependientes de un source."""

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        invalidated = ctl.invalidate_from_source(
            source_id=args.source,
            max_hops=args.max_hops,
        )
        print(f"invalidated {len(invalidated)} claim(s) from source={args.source}")
        for cid in invalidated:
            print(f"  - {cid}")
        return EXIT_OK


def cmd_knowledge_refresh(args: argparse.Namespace) -> int:
    """Re-valida Claims contra nueva revision."""

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        reactivated = ctl.refresh_source(
            source_id=args.source,
            new_revision=args.revision,
        )
        print(f"reactivated {len(reactivated)} claim(s)")
        for cid in reactivated:
            print(f"  - {cid}")
        return EXIT_OK


def cmd_knowledge_compile(args: argparse.Namespace) -> int:
    """Compila un handoff desde una receta inline."""

    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        # WI-109: la recipe es ENTRADA DE USUARIO y va como JSON literal.
        # Este `json.loads` estaba fuera del `try`, y `JSONDecodeError` no
        # es `SkillGraphError`, asi que un `{` mal cerrado salia como
        # Traceback con rc=1 de Python en vez de como error de dominio.
        try:
            recipe_raw = (
                json.loads(args.recipe)
                if args.recipe.startswith("{")
                else {
                    "obligatory": [{"kind": "source", "value": args.recipe}],
                    "freshness_policy": "strict" if args.strict else "best_effort",
                    "token_budget": args.token_budget,
                    "overflow_strategy": args.overflow,
                }
            )
        except json.JSONDecodeError as exc:
            # Conversion inmediata a un error de dominio tipado: la
            # frontera con `json` no es nuestra, pero el significado si.
            raise ParseError(
                f"recipe JSON invalido: {exc}. Pasa un source_id o un JSON literal completo."
            ) from exc
        recipe = ContextRecipe.from_dict(recipe_ref=args.recipe, raw=recipe_raw)
        ctx = ContextController(knowledge=ctl)
        try:
            handoff = ctx.compile_handoff(
                recipe=recipe,
                run_id=args.run or "cli-run",
                node_execution_id=args.node or "cli-node",
                source_revision=args.revision or "HEAD",
            )
        except SkillGraphError as exc:
            # WI-109: el `code` decide el exit code. Estas tres ramas
            # devolvian EXIT_DOMAIN las tres, y la ultima la alcanzaba
            # todo lo demas: no distinguian nada, solo parecían hacerlo.
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return exit_para(exc)
        print(json.dumps(handoff.to_dict(), indent=2, ensure_ascii=False))
        print(f"--- context_hash: {handoff.context_hash}")
        return EXIT_OK


def cmd_knowledge_trace(args: argparse.Namespace) -> int:
    """Extrae un OutcomeTrace desde un run."""
    import json

    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        trace = OutcomeTracer.from_run(
            knowledge=ctl,
            run_id=args.run,
            trace_name=args.name or f"trace-{args.run}",
        )
        print(
            json.dumps(
                {
                    "trace_id": trace.trace_id,
                    "kind": trace.kind,
                    "name": trace.name,
                    "project_id": trace.project_id,
                    "created_at": trace.created_at,
                    "claim_refs": list(trace.claim_refs),
                    "evidence_refs": list(trace.evidence_refs),
                },
                indent=2,
            )
        )
        return EXIT_OK


# ---------------------------------------------------------------------------
# B28 — «¿qué creo, y por qué?»
# ---------------------------------------------------------------------------


def cmd_knowledge_resolve(args: argparse.Namespace) -> int:
    """Resuelve los conflictos de un sujeto PARA UNA INTENCION.

    **POR QUE ESTE SUBCOMANDO ES EL ENTREGABLE Y NO UN ADONO.** Sin el, la
    politica de B28 seria un eje que nadie rellena — MEDIDO en B6 que
    `extraction_method` era un `str` al que no escribia NADIE en `src/`, y por
    eso no podia ser donde viviera el origen. Un bloque que anade capacidad y
    no la deja preguntar es el mismo defecto con mas codigo.

    **Y POR QUE EL `--intent` ES OBLIGATORIO Y NO UN DEFAULT.** Es lo unico que
    separa dos respuestas distintas sobre el mismo conflicto. Poner un valor
    por defecto seria exactement el ranking global que la fila del roadmap
    acusa: la respuesta «correcta» sin preguntar. Sin `--intent` no hay
    pregunta, y sin pregunta no hay respuesta honesta.
    """
    from skillgraph.knowledge.authority import resolver

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        conflictos = storage.conflicts_for(
            tenant_id=tenant_id,
            project_id=project_id,
            subject_entity_id=args.subject,
        )
        if not conflictos:
            print(
                f"{args.subject}: sin conflicto. Nadie se contradice, y no hay nada que resolver."
            )
            return EXIT_OK

        # Cada conflicto se resuelve CON SU PROPIA respuesta. Un sujeto con dos
        # predicados que se contradicen tiene dos respuestas, y escolher una
        # seria el mismo error de authority por el otro lado.
        resoluciones = [resolver(conflicto, intencion=args.intent) for conflicto in conflictos]

    if args.json:
        print(
            json.dumps(
                [_como_dict(r) for r in resoluciones],
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_OK

    for r in resoluciones:
        for ln in _render(r):
            print(ln)
    return EXIT_OK


def _como_dict(r: Resolution) -> dict[str, object]:
    """La resolucion en JSON: la MISMA informacion que `_render` imprime.

    **POR QUE NO SE REIMPLEMENTA LA LOGICA.** Un `--json` que cuenta otra
    historia que el texto es un camino a dos verdades, y el dia que cambien
    una, el otro dira la cosa contraria sin avisar. Se deriva del mismo
    objeto.
    """
    return {
        "subject_entity_id": r.conflicto.subject_entity_id,
        "predicate": r.conflicto.predicate,
        "query_intent": r.intencion,
        "profile": r.perfil,
        "winner": (
            {
                "claim_id": r.ganadora.claim_id,
                "object_literal": r.ganadora.object_literal,
                "assertion_origin": r.ganadora.assertion_origin,
            }
            if r.ganadora is not None
            else None
        ),
        "unresolved": r.sin_resolver,
        "discarded": [
            {
                "claim_id": d.afirmacion.claim_id,
                "object_literal": d.afirmacion.object_literal,
                "assertion_origin": d.afirmacion.assertion_origin,
                "motivo": d.motivo,
            }
            for d in r.descartadas
        ],
    }


def _render(r: Resolution) -> list[str]:
    """La resolucion explicada, como texto.

    **POR QUE NO ES JSON POR DEFECTO.** El campo `perfil` y los `motivo` de
    descarte existen para que un humano entienda por que gano una y perdio la
    otra; un `json.dumps` lo esconde detras de una coma. `--json` lo da
    cuando lo que se quiere es el dato, no la lectura.
    """
    out = [
        f"conflicto: {r.conflicto.subject_entity_id} {r.conflicto.predicate}",
        f"  pregunta:   {r.intencion}  (politica: {r.perfil})",
    ]
    if r.ganadora is not None:
        out.append(f"  gana:       {r.ganadora.claim_id} = {r.ganadora.object_literal!r}")
    else:
        out.append("  gana:       NADIE — la politica no pudo elegir")
    if r.sin_resolver:
        out.append(
            f"  sin resolver: {len(r.elegidas)} afirmaciones empatadas en la misma jerarquia"
        )
    for d in r.descartadas:
        out.append(
            f"  descartada: {d.afirmacion.claim_id} = {d.afirmacion.object_literal!r}  [{d.motivo}]"
        )
    return out
