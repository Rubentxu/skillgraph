"""CLI de SkillGraph (Etapa 1).

Esta capa es deliberadamente delgada: el grueso de la lógica vive
en `skillgraph.storage`, `skillgraph.catalog`, `skillgraph.parser`
y `skillgraph.runcontroller`.

Aqui solo se traduce argv -> llamadas + se formatea la salida.

Auditoria de duplicacion:
- No reimplements validacion de esquemas (eso vive en registry.py).
- No reimplements logica SQL (eso vive en storage.py y catalog.py).
- No reimplements el bucle del run (eso vive en runcontroller.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, NoReturn

if TYPE_CHECKING:
    from skillgraph.platform.paths import agents_root
    from skillgraph.runtime.runcontroller import RunBudget, RunController

from skillgraph import (
    BrickRegistry,
    ResourceIdentity,
    load_defaults,
    parse_file,
)
from skillgraph.cli.commands.expansion import (
    cmd_expansion_apply,
    cmd_expansion_archive,
    cmd_expansion_list,
    cmd_expansion_propose,
    cmd_expansion_rejections,
    cmd_expansion_show,
    cmd_expansion_validate,
)
from skillgraph.cli.commands.runs import (
    cmd_runs_budget,
    cmd_runs_cancel,
    cmd_runs_list,
    cmd_runs_logs,
    cmd_runs_show,
)
from skillgraph.cli.parser import build_parser
from skillgraph.cli.support import (
    EXIT_BAD_NAME,
    EXIT_DB_MISSING,
    EXIT_DOMAIN,
    EXIT_OK,
    EXIT_PARSE,
    EXIT_PLAN_NOT_FOUND,
    EXIT_PROJECT_EXISTS,
    EXIT_PROJECT_NOT_FOUND,
    EXIT_RUN_FAILED,
    EXIT_RUN_INCOMPLETE,
    EXIT_USAGE,
    EXIT_VALIDATION,
    ProjectResolver,
    _open_project_storage,
    resolve_project,
)
from skillgraph.core.errors import (
    ParseError,
    SkillGraphError,
    UnknownKindError,
    ValidationError,
)
from skillgraph.domain.pack_loader import declare_types_from_pack
from skillgraph.governance.backups import (
    create_backup,
    default_backup_dir,
    list_backups,
    restore_backup,
)
from skillgraph.platform.paths import (
    DEFAULT_TENANT,
    agents_root,
    catalog_path,
    is_safe_name,
    project_db_path,
    resolve_data_root,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.catalog import open_catalog
from skillgraph.resources.plan_loader import load_plan_file

# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_data_root(args.data_root)
    cat_path = catalog_path(root)
    cat = open_catalog(cat_path)
    cat.close()
    # El directorio del tenant por defecto se crea al registrar el primer proyecto.
    print(f"Catálogo inicializado en: {cat_path}")
    print(f"Raíz de datos: {root}")
    return EXIT_OK


def cmd_project_create(args: argparse.Namespace) -> int:
    if not is_safe_name(args.name):
        print(
            f"ERROR: nombre de proyecto inválido {args.name!r}. "
            "Use solo [a-z0-9-_] y hasta 64 caracteres.",
            file=sys.stderr,
        )
        return EXIT_BAD_NAME

    root = resolve_data_root(args.data_root)
    cat = open_catalog(catalog_path(root))
    try:
        existing = cat.get_project(tenant_id=DEFAULT_TENANT, name=args.name)
        if existing is not None:
            print(
                f"ERROR: proyecto {args.name!r} ya existe para tenant {DEFAULT_TENANT!r}",
                file=sys.stderr,
            )
            return EXIT_PROJECT_EXISTS

        db = project_db_path(root, args.name, tenant=DEFAULT_TENANT)
        db.parent.mkdir(parents=True, exist_ok=True)
        storage = Storage(db)
        storage.close()
        cat.register_project(tenant_id=DEFAULT_TENANT, name=args.name, db_path=db)
    finally:
        cat.close()
    print(f"Proyecto {args.name!r} creado en: {db}")
    return EXIT_OK


def cmd_project_list(args: argparse.Namespace) -> int:
    root = resolve_data_root(args.data_root)
    cat = open_catalog(catalog_path(root))
    try:
        projects = cat.list_projects(tenant_id=DEFAULT_TENANT)
    finally:
        cat.close()
    if not projects:
        print("(sin proyectos)")
        return EXIT_OK
    for p in projects:
        print(f"{p['name']}\t{p['db_path']}\t{p['created_at']}")
    return EXIT_OK


def cmd_project_inspect(args: argparse.Namespace) -> int:
    project, err = resolve_project(args, args.name)
    if err is not None:
        return err

    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        return EXIT_DB_MISSING

    storage = Storage(db_path)
    try:
        counts = _count_resources(
            storage,
            tenant_id=project["tenant_id"],
            project_id=project["name"],
        )
    finally:
        storage.close()

    print(f"Proyecto: {project['name']}")
    print(f"Tenant:   {project['tenant_id']}")
    print(f"DB:       {project['db_path']}")
    print(f"Creado:   {project['created_at']}")
    print(f"Recursos: {counts['total']} total")
    for kind, n in sorted(counts["by_kind"].items()):
        print(f"  {kind}: {n}")
    return EXIT_OK


def _count_resources(storage: Storage, *, tenant_id: str, project_id: str) -> dict[str, object]:
    rows = storage.list_resources(tenant_id=tenant_id, project_id=project_id)
    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[row.kind] = by_kind.get(row.kind, 0) + 1
    return {"total": len(rows), "by_kind": by_kind}


def _find_active_run_id(storage: Storage, *, tenant_id: str, project_id: str) -> str | None:
    """Devuelve el run_id del Run mas reciente en estado no terminal
    para (tenant, project), o None si no hay ninguno.

    No terminal = CREATED, ACTIVE o WAITING (ver
    ``Storage.NON_TERMINAL_RUN_STATES``). COMPLETED/FAILED/CANCELLED
    se consideran terminales y el siguiente `run` debe crear uno nuevo.
    Cumple UAT-06: tras un crash con un run ACTIVE, el CLI lo encuentra
    y lo reanuda en lugar de crear uno nuevo.

    Refactor H9-BSlice2: delega en ``Storage.find_active_run`` (API publica).
    """
    return storage.find_active_run(tenant_id=tenant_id, project_id=project_id)


# ---------------------------------------------------------------------------
# Comandos knowledge (H3 Slice 5)
# ---------------------------------------------------------------------------


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
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    with _open_known_project(args, args.project) as (tenant_id, project_id, storage):
        ctl = KnowledgeController(knowledge=storage, tenant_id=tenant_id, project_id=project_id)
        stale = ctl.list_stale_claims()
        print(f"stale claims ({len(stale)}):")
        for c in stale:
            print(f"  - {c.claim_id}  {c.predicate}={c.object_literal} stale=true")
        return EXIT_OK


def cmd_knowledge_invalidate(args: argparse.Namespace) -> int:
    """Invalida Claims dependientes de un source."""
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

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
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

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

    from skillgraph.core.recipe import ContextRecipe
    from skillgraph.knowledge.context_controller import ContextController
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

    from skillgraph.knowledge.context_controller import OutcomeTracer
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
# Parser principal
# ---------------------------------------------------------------------------


# Reexport: los consumidores previos del simbolo siguen funcionando.
# La tabla de dispatch y `main` lo usan a traves de este alias.
_build_parser = build_parser


def main(argv: list[str] | None = None) -> int:
    from skillgraph import __version__

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"skillgraph {__version__}")
        return EXIT_OK

    if args.command is None:
        parser.print_help()
        return EXIT_OK

    handler = _resolve_handler(args)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE

    try:
        return handler(args)
    except SkillGraphError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_DOMAIN
    except FileNotFoundError as exc:
        # Caso comun: el proyecto pasado a _open_known_project no existe.
        # Mensaje legible + exit code canonico (EXIT_PROJECT_NOT_FOUND = 4).
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_PROJECT_NOT_FOUND


def _route_runs(args: argparse.Namespace) -> int:
    """Enruta subcommand `runs` al handler correspondiente.

    Eliminado en WI-41: `_DISPATCH` enruta (runs, sub) directamente.
    Se conserva el nombre por compatibilidad con imports externos.
    """
    return _dispatch_nested("runs", args)


def _route_policy(args: argparse.Namespace) -> int:
    """Enruta subcommand `policy` al handler correspondiente.

    Eliminado en WI-41: `_DISPATCH` enruta (policy, sub) directamente.
    """
    return _dispatch_nested("policy", args)


def cmd_policy_get(args: argparse.Namespace) -> int:
    """Muestra la politica de redaccion del tenant (S5 Etapa 7).

    Read-only. Imprime `policy=<valor>` o `policy=none` (default).
    """
    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        policy = storage.get_policy(tenant_id=project["tenant_id"])
        print(f"tenant_id={project['tenant_id']}")
        print(f"policy={policy or 'none'}")
        return EXIT_OK


def cmd_policy_set(args: argparse.Namespace) -> int:
    """Configura la politica de redaccion del tenant (S5 Etapa 7).

    Valida el argumento via argparse choices (none|metadata|payload|full)
    y delega en Storage.upsert_policy. Persistente: aplica a TODOS los
    Runs futuros del tenant.
    """
    with _open_project_storage(args) as (storage, err):
        if err != EXIT_OK or storage is None:
            return err
        project, _ = resolve_project(args, args.project)
        storage.upsert_policy(tenant_id=project["tenant_id"], policy=args.redact_policy)
        print(f"tenant_id={project['tenant_id']} policy={args.redact_policy}")
        return EXIT_OK


def _route_knowledge(args: argparse.Namespace) -> int:
    """Enruta subcommand `knowledge` al handler correspondiente.

    Eliminado en WI-41: `_DISPATCH` enruta (knowledge, sub) directamente.
    """
    return _dispatch_nested("knowledge", args)


def _route_expansion(args: argparse.Namespace) -> int:
    """Enruta subcommand `expansion` al handler correspondiente.

    Eliminado en WI-41: `_DISPATCH` enruta (expansion, sub) directamente.
    """
    return _dispatch_nested("expansion", args)


def _build_registry_for_project(
    storage: Storage, *, tenant_id: str, project_id: str
) -> BrickRegistry:
    """Registry del nucleo + tipos declarados por los Domain Packs
    persistidos del proyecto (H8, ADR-0013-anexo).

    Los packs adoptados viven en la tabla `resources` con
    kind='DomainPack'; aqui se re-declaran sus tipos sobre
    `load_defaults()`. Sin ejecutar codigo del pack: la declaracion
    es solo el schema declarativo (declare_types_from_pack).
    """
    import json as _json

    from skillgraph.resources.bricks import Brick

    reg = load_defaults()
    for row in storage.list_resources(
        tenant_id=tenant_id, project_id=project_id, kind="DomainPack"
    ):
        try:
            spec = _json.loads(row.spec_json or "{}")
        except (ValueError, TypeError):
            spec = {}
        try:
            declare_types_from_pack(
                reg,
                Brick(
                    identity=ResourceIdentity(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        namespace=row.namespace,
                        kind="DomainPack",
                        name=row.name,
                    ),
                    api_version=row.api_version,
                    kind="DomainPack",
                    spec=spec or {},
                ),
            )
        except SkillGraphError:
            # Un pack corrupto no debe impedir arrancar el comando:
            # los tipos core siguen disponibles. Se omite el pack.
            continue
    return reg


def cmd_pack_load(args: argparse.Namespace) -> int:
    """Carga un Domain Pack en un proyecto (H8, UAT-12 ruta publica).

    Persiste el pack como resource kind='DomainPack'. Los tipos que
    declara quedan disponibles para futuros comandos del proyecto via
    `_build_registry_for_project`.
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err

    db_path = Path(project["db_path"])
    registry: BrickRegistry = load_defaults()
    identity = ResourceIdentity(
        tenant_id=project["tenant_id"],
        project_id=args.project,
        namespace="(pending)",
        kind="(pending)",
        name="(pending)",
    )
    try:
        pack = parse_file(args.path, identity=identity)
    except ParseError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_PARSE

    # Solo se acepta un DomainPack; validar que sus tipos son declarables
    # ANTES de persistir (fail-fast, sin dejar pack roto persistido).
    if pack.kind != "DomainPack":
        print(
            f"ERROR ({ValidationError.code}): se esperaba kind='DomainPack', recibio {pack.kind!r}",
            file=sys.stderr,
        )
        return EXIT_VALIDATION
    try:
        declared = declare_types_from_pack(registry, pack)
    except ValidationError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_VALIDATION

    storage = Storage(db_path)
    try:
        # Re-declaracion contra el registry del proyecto ya persistido:
        # evita shadowing con packs cargados previamente.
        project_reg = _build_registry_for_project(
            storage, tenant_id=project["tenant_id"], project_id=args.project
        )
        try:
            declare_types_from_pack(project_reg, pack)
        except ValidationError as exc:
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return EXIT_VALIDATION
        uid = storage.upsert_resource(pack)
    finally:
        storage.close()
    print(f"Domain Pack cargado: {pack.identity.namespace}/{pack.identity.name}")
    print(f"Tipos declarados: {', '.join(declared)}")
    print(f"UID: {uid}")
    return EXIT_OK


def cmd_brick_register(args: argparse.Namespace) -> int:
    """Registra un brick en un proyecto, validándolo primero."""
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err

    db_path = Path(project["db_path"])
    storage = Storage(db_path)
    try:
        registry: BrickRegistry = _build_registry_for_project(
            storage, tenant_id=project["tenant_id"], project_id=args.project
        )
        identity = ResourceIdentity(
            tenant_id=project["tenant_id"],
            project_id=args.project,
            namespace="(pending)",
            kind="(pending)",
            name="(pending)",
        )
        try:
            brick = parse_file(args.path, identity=identity)
        except ParseError as exc:
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return EXIT_PARSE
        try:
            registry.validate(brick)
        except (UnknownKindError, ValidationError) as exc:
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return EXIT_VALIDATION
        uid = storage.upsert_resource(brick)
    finally:
        storage.close()
    print(f"Brick registrado: {brick.kind}/{brick.identity.namespace}/{brick.identity.name}")
    print(f"UID: {uid}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# H8: promocion entre bases (sg promotion submit/list/reconcile)
# ---------------------------------------------------------------------------


def _default_claim_importer(storage: Storage, *, tenant_id: str, target_project: str):
    """apply_fn por defecto: importa al proyecto destino lo que el claim
    referenciado necesita (source -> entity -> claim), reutilizando las
    APIs idempotentes de Storage (upsert_source/upsert_entity/record_claim,
    todas INSERT OR IGNORE/REPLACE). Asi el apply es re-ejecutable sin
    duplicar: la idempotencia es del storage destino, no del caller.

    El payload lo produce `cmd_promotion_submit`:
    {source, entity, claim, source_project, target_project}.
    Devuelve True si el claim quedó registrado en destino (o ya estaba).
    """
    from datetime import datetime

    from skillgraph.knowledge.graph import Claim, Entity, Source

    def _apply(payload: dict) -> bool:
        c = payload.get("claim")
        if not isinstance(c, dict):
            return False
        s = payload.get("source")
        if isinstance(s, dict) and s.get("source_id"):
            storage.register_source(
                tenant_id=tenant_id,
                project_id=target_project,
                source=Source(
                    source_id=s["source_id"],
                    kind=s.get("kind", "local_file"),
                    content_hash=s.get("content_hash", "promoted"),
                    locator=s.get("locator", {}),
                    git_commit_sha=s.get("git_commit_sha"),
                    git_tree_sha=s.get("git_tree_sha"),
                    working_tree_status=s.get("working_tree_status"),
                    checked_at=s.get("checked_at") or datetime.now(UTC).isoformat(),
                    freshness=s.get("freshness", "fresh"),
                ),
            )
        e = payload.get("entity")
        if isinstance(e, dict) and e.get("entity_id"):
            storage.upsert_entity(
                tenant_id=tenant_id,
                project_id=target_project,
                entity=Entity(
                    entity_id=e["entity_id"],
                    kind=e.get("kind", "module"),
                    stable_key=e.get("stable_key", e["entity_id"]),
                ),
            )
        claim = Claim(
            claim_id=c["claim_id"],
            subject_entity_id=c["subject_entity_id"],
            predicate=c["predicate"],
            object_literal=c["object_literal"],
            source_id=c["source_id"],
            evidence_ids=tuple(c.get("evidence_ids", ()) or ()),
            extraction_method=c.get("extraction_method", "static_analysis"),
            extractor_version=c.get("extractor_version", "unknown"),
            checked_at_revision=c.get("checked_at_revision", "unknown"),
        )
        storage.record_claim(tenant_id=tenant_id, project_id=target_project, claim=claim)
        return True

    return _apply


def _source_to_payload(
    storage: Storage,
    *,
    tenant_id: str,
    project_id: str,
    source_id: str,
) -> dict | None:
    """Serializa una Source del proyecto origen para el payload de promocion.

    Delega en ``Storage.get_source`` (API publica, refactor H9-BSlice2).
    Devuelve el mismo formato ``dict`` que antes para mantener compatibilidad
    con el payload JSON que escribe ``promotion.submit_proposal``.

    Mejora de aislamiento: el filtro original usaba solo ``source_id`` +
    ``tenant_id`` (sin ``project_id``), lo que permitia colisiones entre
    proyectos del mismo tenant con mismo ``source_id``. El nuevo filtro
    discrimina tambien por proyecto: mas estricto, mas correcto
    (cumple blueprint 09 'aislamiento por proyecto').
    """
    source = storage.get_source(tenant_id=tenant_id, project_id=project_id, source_id=source_id)
    if source is None:
        return None
    import dataclasses
    import json as _json

    d = dataclasses.asdict(source)
    # `asdict` no deserializa los JSON strings; replicamos el parseo previo.
    for k in ("locator", "working_tree_status"):
        if isinstance(d.get(k), str):
            try:
                d[k] = _json.loads(d[k])
            except (ValueError, TypeError):
                d[k] = {}
        elif d.get(k) is None:
            d[k] = {}
    return d


def _entity_to_payload(
    storage: Storage,
    *,
    tenant_id: str,
    project_id: str,
    entity_id: str,
) -> dict | None:
    """Serializa una Entity del proyecto origen para el payload de promocion.

    Delega en ``Storage.get_entity`` (API publica, refactor H9-BSlice2).
    Misma nota de aislamiento que ``_source_to_payload``.
    """
    import dataclasses

    entity = storage.get_entity(tenant_id=tenant_id, project_id=project_id, entity_id=entity_id)
    if entity is None:
        return None
    return dataclasses.asdict(entity)


def cmd_promotion_submit(args: argparse.Namespace) -> int:
    """Registra una propuesta de promocion en el outbox (status=PENDING).

    El payload se construye desde el Claim indicado (source_project);
    target_project es el catalogo destino donde `reconcile` lo aplicara.
    """
    from skillgraph.core.errors import IdentityConflictError
    from skillgraph.governance.promotion import submit_proposal

    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    tenant_id = project["tenant_id"]

    storage = Storage(Path(project["db_path"]))
    try:
        claim = storage.get_claim(
            tenant_id=tenant_id, project_id=args.project, claim_id=args.claim_id
        )
        if claim is None:
            print(
                f"ERROR (sg_not_found): claim {args.claim_id!r} no existe en {args.project!r}",
                file=sys.stderr,
            )
            return EXIT_DOMAIN
        payload = {
            "source_project": args.project,
            "target_project": args.target,
            "source": _source_to_payload(
                storage, tenant_id=tenant_id, project_id=args.project, source_id=claim.source_id
            ),
            "entity": _entity_to_payload(
                storage,
                tenant_id=tenant_id,
                project_id=args.project,
                entity_id=claim.subject_entity_id,
            ),
            "claim": {
                "claim_id": claim.claim_id,
                "subject_entity_id": claim.subject_entity_id,
                "predicate": claim.predicate,
                "object_literal": claim.object_literal,
                "source_id": claim.source_id,
                "evidence_ids": list(claim.evidence_ids),
                "extraction_method": claim.extraction_method,
                "extractor_version": claim.extractor_version,
                "checked_at_revision": claim.checked_at_revision,
            },
        }
        proposal_id = args.proposal_id or f"promo-{args.claim_id}"
        try:
            submit_proposal(
                storage,
                proposal_id=proposal_id,
                tenant_id=tenant_id,
                source_project=args.project,
                target_catalog=args.target,
                knowledge_ref=args.claim_id,
                payload=payload,
            )
        except IdentityConflictError as exc:
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return EXIT_DOMAIN
    finally:
        storage.close()
    print(f"Propuesta registrada: {proposal_id} (PENDING)")
    print(f"Destino: {args.target}")
    return EXIT_OK


def cmd_promotion_list(args: argparse.Namespace) -> int:
    """Lista propuestas del outbox (todas o solo pendientes)."""
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err

    storage = Storage(Path(project["db_path"]))
    try:
        # list_promotions() es la API publica; status='PENDING' devuelve solo
        # PENDING (no IN_PROGRESS). list_pending_promotions() conserva el
        # compat con IN_PROGRESS para callers internos (cmd_promotion_reconcile).
        rows = storage.list_pending_promotions() if args.pending else storage.list_promotions()
    finally:
        storage.close()
    if not rows:
        print("(sin propuestas)")
        return EXIT_OK
    for r in rows:
        print(
            f"{r['proposal_id']}  {r['status']:<12} {r['source_project']} -> {r['target_catalog']}"
        )
    return EXIT_OK


# Nombres de failpoint reconocidos en `sg promotion reconcile` (H8/UAT-13).
# Valor cerrado: un nombre desconocido no dispara nada, para que un typo en
# la variable de entorno no tumbe un run real por accidente.
PROMOTION_FAILPOINTS: Final[frozenset[str]] = frozenset(
    {"before_apply", "mid_apply", "after_apply_first"}
)

# Variable de entorno que el UAT usa para simular un crash.
_PROMOTION_FAILPOINT_ENV = "SKILLGRAPH_FAILPOINT_PROMOTION"

# Codigo de salida de un crash simulado. Distinto de cualquier EXIT_* del
# CLI para que un "crash" no se confunda con un error de dominio.
_FAILPOINT_EXIT_CODE = 9


def _select_promotion_failpoint() -> str | None:
    """Normaliza el failpoint pedido por el entorno, o None si no hay.

    Decision pura salvo por la lectura de entorno: separar la *decision*
    del `os._exit` es lo que hace comprobable el failpoint, porque el
    efecto termina el proceso y no se puede observar desde pytest.

    Returns:
        El nombre normalizado si es uno de `PROMOTION_FAILPOINTS`;
        None si la variable no esta, vacia o trae un nombre desconocido.
    """
    raw = os.environ.get(_PROMOTION_FAILPOINT_ENV)
    if raw is None:
        return None
    name = raw.strip().lower()
    return name if name in PROMOTION_FAILPOINTS else None


def _abort_with_failpoint(name: str) -> NoReturn:
    """Escribe el failpoint en stderr y termina el proceso.

    El codigo de salida es `_FAILPOINT_EXIT_CODE`, el mismo que usaban
    los failpoints inline antes de extraerse. Se conserva para no romper
    los asserts de los tests subprocess de UAT-13.

    Args:
        name: nombre del failpoint, ya validado.

    Raises:
        SystemExit: nunca; el proceso termina con `os._exit`.
    """
    sys.stderr.write(f"FAILPOINT: {name}\n")
    sys.stderr.flush()
    os._exit(_FAILPOINT_EXIT_CODE)


def _apply_pending_promotions(
    storage: Storage,
    dest_storage: Storage,
    *,
    tenant_id: str,
    target_project: str,
) -> list[dict[str, str]]:
    """Aplica cada propuesta pendiente y devuelve su estado final.

    El apply escribe en la base del PROYECTO DESTINO: el outbox vive en
    origen y el claim promovido vive en destino. La idempotencia es del
    storage destino (upserts), no de este bucle, asi que re-invocar el
    comando tras un crash completa la operacion sin duplicar.

    Los failpoint se disparan aqui porque son los unicos puntos donde el
    estado queda a medio camino:
    - `before_apply`: tras leer las pendientes, antes de aplicar ninguna.
    - `mid_apply`: tras marcar IN_PROGRESS, antes del apply de negocio.
    - `after_apply_first`: DENTRO del apply de la primera, entre el
      efecto de negocio y el marcado PUBLISHED. Es el unico punto real
      de estado partido: el claim ya esta en destino y el outbox sigue
      sin publicar. Colocarlo despues de `apply_proposal` no serviria
      de nada, porque ahi el outbox ya quedo PUBLISHED.

    Args:
        storage: outbox de origen (donde viven las propuestas).
        dest_storage: base destino (donde se registran los claims).
        tenant_id: tenant de la promocion.
        target_project: nombre del proyecto destino.

    Returns:
        Una entrada `{"proposal_id", "status"}` por propuesta aplicada.
    """
    from skillgraph.governance.promotion import apply_proposal

    base_apply = _default_claim_importer(
        dest_storage, tenant_id=tenant_id, target_project=target_project
    )
    failpoint = _select_promotion_failpoint()
    if failpoint == "before_apply":
        _abort_with_failpoint(failpoint)

    crashed = False

    def apply_fn(payload: dict) -> bool:
        """Aplica al destino y, si toca, deja el estado partido."""
        nonlocal crashed
        ok = base_apply(payload)
        if failpoint == "after_apply_first" and not crashed:
            crashed = True
            _abort_with_failpoint(failpoint)
        return ok

    results: list[dict[str, str]] = []
    for proposal in storage.list_pending_promotions():
        if failpoint == "mid_apply":
            storage.mark_promotion_in_progress(proposal["proposal_id"])
            _abort_with_failpoint(failpoint)

        final_status = apply_proposal(storage, proposal["proposal_id"], apply_fn=apply_fn)
        results.append({"proposal_id": proposal["proposal_id"], "status": final_status})
    return results


def _reconcile_summaries(results: list[dict[str, str]]) -> tuple[int, int]:
    """Cuenta (publicadas, fallidas) sobre los resultados del reconcile.

    Funcion pura: no toca storage ni imprime. Solo cuenta los dos estados
    que el comando conoce, de modo que un estado nuevo no altera el
    recuento por accidente.

    Args:
        results: entradas `{"proposal_id", "status"}` del reconcile.

    Returns:
        Par (published, failed). La lista vacia da (0, 0).
    """
    published = sum(1 for r in results if r["status"] == "PUBLISHED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    return published, failed


def cmd_promotion_reconcile(args: argparse.Namespace) -> int:
    """Reconcilia propuestas PENDING/IN_PROGRESS: aplica sin duplicar.

    Recorrido UAT-13: interrumpir el proceso (crash/failpoint) y
    re-invocar `promotion reconcile` completa la operacion sin
    duplicar el claim en el catalogo destino.
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    tenant_id = project["tenant_id"]
    target = args.target or args.project

    # El apply debe escribir en la base del PROYECTO DESTINO (el outbox
    # vive en origen; el claim promovido vive en destino).
    dest_project, err = resolve_project(args, target)
    if err is not None:
        print(
            f"ERROR: proyecto destino {target!r} no existe; crealo antes de reconciliar.",
            file=sys.stderr,
        )
        return EXIT_DOMAIN
    dest_storage = Storage(Path(dest_project["db_path"]))
    storage = Storage(Path(project["db_path"]))
    try:
        results = _apply_pending_promotions(
            storage,
            dest_storage,
            tenant_id=tenant_id,
            target_project=dest_project["name"],
        )
    finally:
        storage.close()
        dest_storage.close()
    if not results:
        print("(nada que reconciliar)")
        return EXIT_OK
    published, failed = _reconcile_summaries(results)
    for r in results:
        print(f"{r['proposal_id']}: {r['status']}")
    print(f"Reconciliadas: {len(results)} (PUBLISHED={published}, FAILED={failed})")
    return EXIT_OK if failed == 0 else EXIT_DOMAIN


def cmd_pack_import(args: argparse.Namespace) -> int:
    """H5 skill_import: asimila una skill externa sin ejecutar su codigo.

    Pipeline: IMPORT -> ANALYZE -> STRUCTURE -> VALIDATE -> REGISTER.
    Conserva el material original (Source con content_hash + locator)
    y emite un informe de estructuracion en JSON. Las partes ambiguas
    permanecen senaladas; NO se presentan como decisiones verificadas.
    """
    from skillgraph.domain.skill_importer import analyze_skill, register_imported_skill
    from skillgraph.platform.storage import Storage

    project, err = resolve_project(args, args.project)
    if err is not None:
        return err

    skill_path = args.path
    if not skill_path.exists():
        print(f"ERROR: skill path no existe: {skill_path}", file=sys.stderr)
        return EXIT_VALIDATION

    # IMPORT + ANALYZE + STRUCTURE + VALIDATE
    report = analyze_skill(skill_path)

    # REGISTER: persistir el Source en el storage del proyecto.
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(f"ERROR: base de datos ausente: {db_path}", file=sys.stderr)
        return EXIT_DB_MISSING
    storage = Storage(db_path)
    try:
        register_imported_skill(
            storage=storage,
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            report=report,
        )
    finally:
        storage.close()

    # Reporte: stdout o --report path.
    payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
        print(f"Fuente conservada: source_id={report.source_id}")
        print(f"Content hash: {report.content_hash}")
        print(
            f"Archivos: {report.files_total} "
            f"(estructurados={len(report.files_structured)}, "
            f"ambiguos={len(report.entries_ambiguous)})"
        )
        print(f"Scripts detectados (NO ejecutados): {len(report.scripts_detected)}")
        print(
            f"Capacidades extraidas (senales, no verificadas): {len(report.capabilities_extracted)}"
        )
        print(f"Informe escrito en: {args.report}")
    else:
        print(payload)
    return EXIT_OK


def cmd_backup_create(args: argparse.Namespace) -> int:
    """Crea un backup .zip del data-root (WI-15)."""
    output = create_backup(resolve_data_root(args.data_root))
    print(f"Backup creado: {output}")
    print(f"Tamano: {output.stat().st_size} bytes")
    return EXIT_OK


def cmd_backup_list(args: argparse.Namespace) -> int:
    """Lista backups disponibles en el directorio configurado."""
    backup_dir = (
        args.dir if args.dir is not None else default_backup_dir(resolve_data_root(args.data_root))
    )
    infos = list_backups(backup_dir)
    if not infos:
        print(f"Sin backups en {backup_dir}")
        return EXIT_OK
    print(f"Backups en {backup_dir}:")
    for info in infos:
        print(
            f"  {info.relpath}  {info.size_bytes}B  "
            f"tenants={info.tenant_count} projects={info.project_count}  "
            f"created={info.created_at}"
        )
    return EXIT_OK


def cmd_backup_restore(args: argparse.Namespace) -> int:
    """Restaura un backup .zip a un data-root destino."""
    target = restore_backup(args.backup, args.target, overwrite=args.overwrite)
    print(f"Backup restaurado en: {target}")
    return EXIT_OK


def cmd_backup(args: argparse.Namespace) -> int:
    """Dispatcher del sub-comando `backup` (WI-15)."""
    sub = getattr(args, "backup_command", None)
    if sub == "create":
        return cmd_backup_create(args)
    if sub == "list":
        return cmd_backup_list(args)
    if sub == "restore":
        return cmd_backup_restore(args)
    print(
        "ERROR: sub-comando de backup requerido (create|list|restore).",
        file=sys.stderr,
    )
    return EXIT_VALIDATION


def _build_adapter(args: argparse.Namespace, fixtures_root: Path) -> Any:
    """Construye el adapter segun --adapter (fake | http).

    fake: FakeAgentAdapter con fixtures_root (default; comportamiento
        historico, determinista).
    http: HttpAgentAdapter leyendo ANTHROPIC_API_KEY o OPENAI_API_KEY
        del entorno segun --llm-provider.

    Raises:
        SkillGraphError (via http_adapter_from_env) si --adapter=http
        y la variable de entorno del proveedor no esta definida.
    """
    from skillgraph.core.errors import ValidationError
    from skillgraph.runtime.agent import FakeAgentAdapter

    kind = getattr(args, "adapter", "fake")
    if kind == "fake":
        return FakeAgentAdapter(fixtures_root)
    if kind == "http":
        from skillgraph.runtime.http_adapter import http_adapter_from_env

        provider = getattr(args, "llm_provider", "anthropic")
        model = getattr(args, "llm_model", None)
        timeout_s = getattr(args, "llm_timeout_s", 30.0)
        adapter = http_adapter_from_env(provider, model=model)
        # Override timeout si el usuario lo especifico.
        if timeout_s != 30.0:
            object.__setattr__(adapter, "timeout_s", timeout_s)
        return adapter
    # argparse normalmente bloquea esto via choices=['fake','http'];
    # este error existe para usos programaticos sin argparse.
    raise ValidationError(f"adapter invalido: {kind!r} (esperado: 'fake' | 'http')")


def _resolve_run_inputs(
    args: argparse.Namespace,
) -> tuple[RunController, Storage, str, str, str, str]:
    """Valida input + construye controller + Run (nuevo o resumed).

    Returns:
        Tupla ``(ctl, storage, run_id, tenant_id, project_name,
        project_db_error, plan_or_None)``. ``project_db_error`` es el
    exit code si algo fallo (no-None), y ``plan_or_None`` es None en
    el caso de fallo (el caller propaga el error al usuario).
    """
    from skillgraph.runtime.runcontroller import RunBudget, RunController

    project, err = resolve_project(args, args.project)
    if err is not None:
        return None, None, None, None, None, err
    if not args.plan.is_file():
        print(
            f"ERROR: plan no encontrado: {args.plan}",
            file=sys.stderr,
        )
        return None, None, None, None, None, EXIT_PLAN_NOT_FOUND
    try:
        plan = load_plan_file(args.plan)
    except ParseError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return None, None, None, None, None, EXIT_PARSE
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        return None, None, None, None, None, EXIT_DB_MISSING

    fixtures_root = args.fixtures_root or agents_root(resolve_data_root(args.data_root))
    fixtures_root.mkdir(parents=True, exist_ok=True)
    adapter = _build_adapter(args, fixtures_root)
    storage = Storage(db_path)
    ctl = RunController(
        runs=storage,
        events=storage,
        policy=storage,
        adapter=adapter,
    )

    # Resume-or-start: si ya existe un Run no terminal para este
    # proyecto, lo reanudamos. Asi el usuario puede re-invocar
    # `run` tras un crash y el controller reanuda el mismo Run
    # con su current_node y sus NodeExecutions. Cumple UAT-06.
    existing_run_id = _find_active_run_id(
        storage,
        tenant_id=project["tenant_id"],
        project_id=project["name"],
    )
    if existing_run_id is not None:
        run_id = existing_run_id
    else:
        # S4 Etapa 7: construye RunBudget solo si el usuario paso
        # al menos un limite. Si los tres son None, budget=None
        # (compat con Runs anteriores).
        budget: RunBudget | None = None
        if any(
            v is not None
            for v in (
                args.budget_visits,
                args.budget_runtime_seconds,
                args.budget_events,
            )
        ):
            budget = RunBudget(
                max_visits=args.budget_visits,
                max_runtime_seconds=args.budget_runtime_seconds,
                max_events=args.budget_events,
            )
        run_id = ctl.create_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            plan=plan,
            budget=budget,
        )
    return (
        ctl,
        storage,
        run_id,
        project["tenant_id"],
        project["name"],
        None,
    )


def _reconcile_until_terminal(
    ctl: RunController,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    max_iterations: int,
) -> tuple[str, str, tuple[str, ...], int, bool]:
    """Bucle de reconciliacion hasta terminal o max_iterations.

    Returns:
        Tupla ``(state, current_node, executed_nodes_tuple,
        events_emitted, hit_max_iterations)``.
    """
    from skillgraph.core.runtime_types import is_terminal_run_state

    iterations = 1
    snap = ctl.reconcile_run(
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
    )
    while not is_terminal_run_state(snap.state) and iterations < max_iterations:
        iterations += 1
        snap = ctl.reconcile_run(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
        )
    hit_max = not is_terminal_run_state(snap.state) and iterations >= max_iterations
    if hit_max:
        print(
            f"WARN: max-iterations alcanzado ({max_iterations}); "
            f"estado={snap.state} current={snap.current_node}",
            file=sys.stderr,
        )
    return (
        snap.state,
        snap.current_node,
        tuple(snap.executed_nodes),
        snap.events_emitted,
        hit_max,
    )


def cmd_run(args: argparse.Namespace) -> int:
    """Crea un Run desde un WorkflowPlan.md y reconcilia hasta terminal.

    Cierra H2 por la via UAT: el usuario real ejecuta el CLI.
    """
    ctl, storage, run_id, tenant_id, project_name, early_exit = _resolve_run_inputs(args)
    if early_exit is not None:
        return early_exit

    try:
        state, _current_node, executed_nodes, events_emitted, _hit_max = _reconcile_until_terminal(
            ctl,
            tenant_id=tenant_id,
            project_id=project_name,
            run_id=run_id,
            max_iterations=args.max_iterations,
        )
    finally:
        storage.close()

    print(f"Run: {run_id}")
    print(f"Estado: {state}")
    print(f"Nodos ejecutados: {', '.join(executed_nodes) or '(ninguno)'}")
    print(f"Eventos emitidos: {events_emitted}")
    adapter_kind = getattr(args, "adapter", "fake")
    print(f"Tipo de adapter: {adapter_kind}")
    print(f"Fixtures de agente: {_resolve_fixtures_root(args)}")
    # Codigos distintos segun estado para que el shell pueda
    # ramificar sin parsear la salida.
    if state == "COMPLETED":
        return EXIT_OK
    if state == "FAILED":
        return EXIT_RUN_FAILED
    return EXIT_RUN_INCOMPLETE


def _resolve_fixtures_root(args: argparse.Namespace) -> Path:
    """Resuelve el fixtures_root final tras defaults (sigue a cmd_run)."""
    fixtures_root = args.fixtures_root or agents_root(resolve_data_root(args.data_root))
    fixtures_root.mkdir(parents=True, exist_ok=True)
    return fixtures_root


# ---------------------------------------------------------------------------
# H4 Slice 1: expansion controlada CLI (UAT-08/09)
# ---------------------------------------------------------------------------


# --- Tabla de dispatch (WI-41) ----------------------------------------------
# Sustituye el if-chain de 32 ramas que tenia `main` (cc=43, unico hotspot
# publico del informe de arquitectura) y consolida los cuatro routers
# `_route_*`, que eran cuatro copias del mismo patron.
#
# Una sola tabla declara todo el dispatch. Un comando plano se indexa por
# su nombre; un grupo, por el par (comando, subcomando). La resolucion es
# una funcion pura: la misma tupla (comando, subcomando) produce siempre
# el mismo handler (AGENTS.md 1.1, 11.2).
#
# Invariante verificado por `tests/test_wi41_cli_dispatch.py`: todo comando
# y todo subcomando declarados en `_build_parser` tienen entrada aqui.

Handler = Callable[[argparse.Namespace], int]

_DISPATCH: Final[Mapping[str | tuple[str, str], Handler]] = MappingProxyType(
    {
        # --- comandos planos ---
        "init": cmd_init,
        "backup": cmd_backup,
        "brick": cmd_brick_register,
        "run": cmd_run,
        # --- proyecto ---
        ("project", "create"): cmd_project_create,
        ("project", "list"): cmd_project_list,
        ("project", "inspect"): cmd_project_inspect,
        # --- paquetes y bricks ---
        ("pack", "import"): cmd_pack_import,
        ("pack", "load"): cmd_pack_load,
        # --- promocion ---
        ("promotion", "submit"): cmd_promotion_submit,
        ("promotion", "list"): cmd_promotion_list,
        ("promotion", "reconcile"): cmd_promotion_reconcile,
        # --- runs ---
        ("runs", "list"): cmd_runs_list,
        ("runs", "show"): cmd_runs_show,
        ("runs", "logs"): cmd_runs_logs,
        ("runs", "cancel"): cmd_runs_cancel,
        ("runs", "budget"): cmd_runs_budget,
        # --- politica ---
        ("policy", "get"): cmd_policy_get,
        ("policy", "set"): cmd_policy_set,
        # --- knowledge ---
        ("knowledge", "stale"): cmd_knowledge_stale,
        ("knowledge", "invalidate"): cmd_knowledge_invalidate,
        ("knowledge", "refresh"): cmd_knowledge_refresh,
        ("knowledge", "compile"): cmd_knowledge_compile,
        ("knowledge", "trace"): cmd_knowledge_trace,
        # --- expansion ---
        ("expansion", "propose"): cmd_expansion_propose,
        ("expansion", "apply"): cmd_expansion_apply,
        ("expansion", "validate"): cmd_expansion_validate,
        ("expansion", "rejections"): cmd_expansion_rejections,
        ("expansion", "list"): cmd_expansion_list,
        ("expansion", "show"): cmd_expansion_show,
        ("expansion", "archive"): cmd_expansion_archive,
    }
)

# Comando -> atributo del Namespace que contiene su subcomando.
# `None` = comando plano, resoluble por nombre.
_SUBCOMMAND_OF: Final[Mapping[str, str | None]] = MappingProxyType(
    {
        "init": None,
        "backup": None,
        "project": "project_command",
        "brick": None,
        "pack": "pack_command",
        "promotion": "promotion_command",
        "run": None,
        "runs": "runs_command",
        "policy": "policy_command",
        "knowledge": "knowledge_command",
        "expansion": "expansion_command",
    }
)


def _resolve_handler(args: argparse.Namespace) -> Handler | None:
    """Resuelve el handler de `args` en la tabla de dispatch.

    Funcion pura: no lee disco, no muta, no depende del reloj. La misma
    entrada produce siempre la misma salida (AGENTS.md 1.3, 11.1).

    Returns:
        El handler aplicable, o `None` si el comando o el subcomando no
        tienen entrada en la tabla. `None` es el unico caso en que `main`
        imprime la ayuda: las ramas de error de los routers anteriores
        quedan subsumidas aqui.
    """
    command: str = args.command
    attribute: str | None = _SUBCOMMAND_OF.get(command)
    if attribute is None:
        return _DISPATCH.get(command)
    subcommand: str | None = getattr(args, attribute, None)
    if subcommand is None:
        return None
    return _DISPATCH.get((command, subcommand))


def _dispatch_nested(command: str, args: argparse.Namespace) -> int:
    """Ejecuta el subcomando de `args` dentro del grupo `command`.

    Fachada que preserva los nombres `_route_*` (importables por tests y
    por codigo externo) ahora que la tabla es la unica fuente de verdad.

    Un subcomando sin entrada es un error de uso: se informa por stderr y
    se devuelve EXIT_USAGE, igual que antes del refactor.

    Returns:
        El exit code del handler, o EXIT_USAGE si el subcomando no existe.
    """
    attribute: str | None = _SUBCOMMAND_OF.get(command)
    subcommand: str | None = getattr(args, attribute, None) if attribute else None
    handler: Handler | None = _DISPATCH.get((command, subcommand))
    if handler is None:
        print(f"ERROR: {command} subcommand no reconocido: {subcommand!r}", file=sys.stderr)
        return EXIT_USAGE
    return handler(args)


# --- Nota sobre los tres "abrir proyecto + storage" (WI-41) -----------------
# `_open_known_project`, `_open_project_storage` y `_open_project_or_error`
# comparten sus dos primeras lineas (resolver + lookup) pero NO su contrato:
#   - `_open_known_project`    es contextmanager y lanza FileNotFoundError.
#   - `_open_project_storage`  es contextmanager y devuelve (storage, exit).
#   - `_open_project_or_error` no es contextmanager y devuelve (dict, exit).
# Unificarlos exigiría un tipo de retorno que hoy no existe, y los 21 usos
# de la línea `ProjectResolver(...).with_default_root()` están repartidos
# entre los tres y los handlers.
#
# Decision: NO se unifican en este bloque. La repetición de esas dos
# líneas es real pero superficial; el contrato divergente es lo que
# sostiene la diferencia. Forzar una firma única produciría un helper
# con más ramas que los tres que sustituye, que es exactamente el
# antipatrón que WI-41 acaba de eliminar del dispatch. La deuda que
# quedaba era componer los tres sobre un helper `resolve_project(args,
# name)`, lo que elimina las 21 repeticiones sin unificar contratos.
# Verificado por AST: los tres construian un ProjectResolver con el
# data_root resuelto y encadenaban `.with_default_root()`.
#
# RESUELTO en WI-44: los tres componen ahora sobre `resolve_project`, y
# el patron de construccion quedo en un unico sitio. Sus contratos se
# mantienen distintos a proposito: cada uno reporta el fallo a su manera.


if __name__ == "__main__":
    sys.exit(main())


# Public API surface for `from skillgraph.cli.runner import *`.
__all__ = [
    "EXIT_BAD_NAME",
    "EXIT_DB_MISSING",
    "EXIT_DOMAIN",
    "EXIT_OK",
    "EXIT_PARSE",
    "EXIT_PLAN_NOT_FOUND",
    "EXIT_PROJECT_EXISTS",
    "EXIT_PROJECT_NOT_FOUND",
    "EXIT_RUN_FAILED",
    "EXIT_RUN_INCOMPLETE",
    "EXIT_USAGE",
    "EXIT_VALIDATION",
    "ProjectResolver",
    "cmd_brick_register",
    "cmd_expansion_apply",
    "cmd_expansion_archive",
    "cmd_expansion_list",
    "cmd_expansion_propose",
    "cmd_expansion_rejections",
    "cmd_expansion_show",
    "cmd_expansion_validate",
    "cmd_init",
    "cmd_knowledge_compile",
    "cmd_knowledge_invalidate",
    "cmd_knowledge_refresh",
    "cmd_knowledge_stale",
    "cmd_knowledge_trace",
    "cmd_pack_import",
    "cmd_project_create",
    "cmd_project_inspect",
    "cmd_project_list",
    "cmd_run",
    "main",
    # Re-exported for monkeypatching in tests.
    "open_catalog",
]
