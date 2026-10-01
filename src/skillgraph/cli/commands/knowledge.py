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

from skillgraph.cli.support import EXIT_DOMAIN, EXIT_OK, resolve_project
from skillgraph.core.errors import SkillGraphError
from skillgraph.core.recipe import ContextRecipe
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
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            if exc.code in {"sg_stale_knowledge_error"}:
                return EXIT_DOMAIN
            if exc.code in {"sg_missing_obligatory", "sg_token_budget_exceeded"}:
                return EXIT_DOMAIN
            return EXIT_DOMAIN
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
