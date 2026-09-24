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
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

from skillgraph import (
    BrickRegistry,
    ResourceIdentity,
    load_defaults,
    parse_file,
)
from skillgraph.core.errors import (
    ParseError,
    SkillGraphError,
    UnknownKindError,
    ValidationError,
)
from skillgraph.domain.pack_loader import declare_types_from_pack
from skillgraph.governance.graph_expansion import (
    AddNode,
    AddTransition,
    Authorization,
    GraphExpansionProposal,
    RemoveTransition,
    apply_expansion,
    propose,
    record_rejection,
    validate,
)
from skillgraph.platform.paths import (
    DEFAULT_TENANT,
    catalog_path,
    is_safe_name,
    project_db_path,
    resolve_data_root,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.catalog import open_catalog
from skillgraph.resources.plan_loader import load_plan_file
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

# --- Codigos de salida tipados (AGENTS.md §11.15 / contrato CLI) -------------
#  0 OK
#  1 argumento desconocido o falta subcomando
#  2 nombre de proyecto invalido
#  3 proyecto ya existe
#  4 proyecto no existe
#  5 base de datos ausente
#  6 plan no encontrado
# 10 error de dominio SkillGraph (catch-all)
# 11 parse error (workflow o brick)
# 12 validacion semantica (kind desconocido o regla violada)
# 20 run FAILED
# 21 run no terminal tras max-iterations (CANCELLED / WAITING / ACTIVE)
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_BAD_NAME = 2
EXIT_PROJECT_EXISTS = 3
EXIT_PROJECT_NOT_FOUND = 4
EXIT_DB_MISSING = 5
EXIT_PLAN_NOT_FOUND = 6
EXIT_DOMAIN = 10
EXIT_PARSE = 11
EXIT_VALIDATION = 12
EXIT_RUN_FAILED = 20
EXIT_RUN_INCOMPLETE = 21


@dataclass(frozen=True, slots=True)
class ProjectResolver:
    """Encapsula la apertura del catalogo + lookup de proyecto.

    Elimina los 4 subcomandos que duplicaban `open_catalog ->
    get_project -> return 4`. Cada metodo devuelve el `Storage`
    cerrado o un exit code si algo falla.
    """

    data_root: Path
    tenant_id: str = DEFAULT_TENANT

    def with_default_root(self) -> ProjectResolver:
        return ProjectResolver(
            data_root=resolve_data_root(self.data_root),
            tenant_id=self.tenant_id,
        )

    def lookup(self, project_name: str) -> tuple[dict[str, str], int | None]:
        """Busca un proyecto. Devuelve (project_row, None) o ({}, exit_code)."""
        cat = open_catalog(catalog_path(self.data_root))
        try:
            project = cat.get_project(tenant_id=self.tenant_id, name=project_name)
        finally:
            cat.close()
        if project is None:
            print(
                f"ERROR: proyecto {project_name!r} no existe para tenant {self.tenant_id!r}",
                file=sys.stderr,
            )
            return {}, EXIT_PROJECT_NOT_FOUND
        return project, None


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
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.name)
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
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
    return {"total": len(rows), "by_kind": by_kind}


def _utcnow_iso() -> str:
    """ISO-8601 UTC con sufijo +00:00 (legible, ordenable lexicograficamente)."""
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _infer_proposal_stage(
    proposal_path: Path,
    proposal_id: str,
    rejection_ids: set[str],
) -> str:
    """Inferir stage desde markers en disco (mismo patron que list/show).

    Precedencia: ARCHIVED > APPLIED > REJECTED > PROPOSED.
    """
    base = proposal_path.with_suffix(proposal_path.suffix)
    archived_marker = base.with_suffix(base.suffix + ".archived")
    applied_marker = base.with_suffix(base.suffix + ".applied")
    if archived_marker.is_file():
        return "ARCHIVED"
    if applied_marker.is_file():
        return "APPLIED"
    if proposal_id in rejection_ids:
        return "REJECTED"
    return "PROPOSED"


def _collect_rejection_ids(rejections_dir: Path) -> set[str]:
    """Lee ``expansion_rejections/*.json`` y devuelve proposal_ids rechazados.

    Tolerante a JSON corrupto y a archivos sin ``proposal_id``.
    """
    ids: set[str] = set()
    if not rejections_dir.is_dir():
        return ids
    for p in rejections_dir.iterdir():
        if p.suffix != ".json":
            continue
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(d, dict) and "proposal_id" in d:
            ids.add(str(d["proposal_id"]))
    return ids


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


def _open_known_project(args: argparse.Namespace, project: str) -> tuple[str, str, Storage]:
    """Wrapper que valida que el proyecto existe antes de continuar."""
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    p, err = resolver.lookup(project)
    if err is not None:
        return "", "", _DummyStorage()
    return p["tenant_id"], project, Storage(Path(p["db_path"]))


def cmd_knowledge_stale(args: argparse.Namespace) -> int:
    """Lista Claims stale del proyecto."""
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    tenant_id, project_id, storage = _open_known_project(args, args.project)
    ctl = KnowledgeController(storage=storage, tenant_id=tenant_id, project_id=project_id)
    stale = ctl.list_stale_claims()
    print(f"stale claims ({len(stale)}):")
    for c in stale:
        print(f"  - {c.claim_id}  {c.predicate}={c.object_literal} stale=true")
    return EXIT_OK


def cmd_knowledge_invalidate(args: argparse.Namespace) -> int:
    """Invalida Claims dependientes de un source."""
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    tenant_id, project_id, storage = _open_known_project(args, args.project)
    ctl = KnowledgeController(storage=storage, tenant_id=tenant_id, project_id=project_id)
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

    tenant_id, project_id, storage = _open_known_project(args, args.project)
    ctl = KnowledgeController(storage=storage, tenant_id=tenant_id, project_id=project_id)
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
    import json

    from skillgraph.core.recipe import ContextRecipe
    from skillgraph.knowledge.context_controller import ContextController
    from skillgraph.knowledge.knowledge_controller import KnowledgeController

    tenant_id, project_id, storage = _open_known_project(args, args.project)
    ctl = KnowledgeController(storage=storage, tenant_id=tenant_id, project_id=project_id)
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

    tenant_id, project_id, storage = _open_known_project(args, args.project)
    ctl = KnowledgeController(storage=storage, tenant_id=tenant_id, project_id=project_id)
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


class _DummyStorage:
    """Placeholder cuando el proyecto no existe; evita imports fragiles."""

    def __getattr__(self, name: str) -> object:
        msg = "proyecto no encontrado"
        raise FileNotFoundError(msg)


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skillgraph",
        description="SkillGraph: workflows declarativos para agentes.",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Raíz de datos interna (default: ~/.local/share/skillgraph).",
    )
    p.add_argument(
        "--version",
        action="store_true",
        help="Muestra la versión y sale.",
    )
    sub = p.add_subparsers(dest="command", required=False)

    sub.add_parser("init", help="Inicializa el directorio de datos raíz.")

    proj = sub.add_parser("project", help="Gestión de proyectos.")
    proj_sub = proj.add_subparsers(dest="project_command", required=True)
    pc = proj_sub.add_parser("create", help="Crea un proyecto.")
    pc.add_argument("name", help="Slug del proyecto (a-z0-9-_, máx 64).")
    proj_sub.add_parser("list", help="Lista proyectos del tenant actual.")
    pi = proj_sub.add_parser("inspect", help="Inspecciona un proyecto.")
    pi.add_argument("name", help="Nombre del proyecto a inspeccionar.")

    bp = sub.add_parser(
        "brick",
        help="(experimental) valida y registra un brick Markdown en un proyecto.",
    )
    bp.add_argument("project", help="Proyecto destino.")
    bp.add_argument("path", type=Path, help="Ruta al archivo .md del brick.")
    bp.add_argument(
        "--kind",
        default=None,
        help="(reservado) override de kind para tests avanzados.",
    )

    # H5 skill_import: pack import (asimila una skill, conserva fuente,
    # genera informe; NO ejecuta scripts).
    pp = sub.add_parser(
        "pack",
        help="Asimilacion de skills externas (H5).",
    )
    pp_sub = pp.add_subparsers(dest="pack_command", required=True)
    pi = pp_sub.add_parser(
        "import",
        help="Importa una skill: conserva fuente y genera informe de estructuracion.",
    )
    pi.add_argument("project", help="Proyecto destino (donde se registra el Source).")
    pi.add_argument("path", type=Path, help="Ruta al directorio o archivo de la skill.")
    pi.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Ruta donde escribir el informe JSON. Default: stdout.",
    )
    pl = pp_sub.add_parser(
        "load",
        help="Carga un Domain Pack en un proyecto: declara sus tipos (H8).",
    )
    pl.add_argument("project", help="Proyecto destino (donde se persiste el pack).")
    pl.add_argument("path", type=Path, help="Ruta al archivo Markdown del Domain Pack.")

    # H8: promotion entre bases (UAT-13 ruta publica)
    pr = sub.add_parser(
        "promotion",
        help="Promocion de conocimiento entre bases/proyectos (H8).",
    )
    pr_sub = pr.add_subparsers(dest="promotion_command", required=True)
    ps = pr_sub.add_parser(
        "submit",
        help="Registra una propuesta de promocion (PENDING) desde un Claim.",
    )
    ps.add_argument("project", help="Proyecto origen (donde vive el Claim).")
    ps.add_argument("claim_id", help="Identificador del Claim a promover.")
    ps.add_argument("target", help="Proyecto/catalogo destino.")
    ps.add_argument(
        "--proposal-id",
        default=None,
        help="Identificador de propuesta. Default: promo-<claim_id>.",
    )
    pll = pr_sub.add_parser(
        "list",
        help="Lista propuestas del outbox.",
    )
    pll.add_argument("project", help="Proyecto (su project.sqlite contiene el outbox).")
    pll.add_argument(
        "--pending",
        action="store_true",
        help="Solo PENDING/IN_PROGRESS.",
    )
    prc = pr_sub.add_parser(
        "reconcile",
        help="Aplica las propuestas pendientes sin duplicar (UAT-13).",
    )
    prc.add_argument("project", help="Proyecto dueño del outbox.")
    prc.add_argument(
        "--target",
        default=None,
        help="Proyecto destino donde aplicar los claims. Default: el mismo proyecto.",
    )

    rp = sub.add_parser(
        "run",
        help="Crea un Run desde un WorkflowPlan.md y reconcilia hasta terminal.",
    )
    rp.add_argument("project", help="Proyecto destino (debe existir).")
    rp.add_argument("plan", type=Path, help="Ruta al WorkflowPlan.md.")
    rp.add_argument(
        "--fixtures-root",
        type=Path,
        default=None,
        help="Raíz de fixtures de agentes (default: <data-root>/agents).",
    )
    rp.add_argument(
        "--max-iterations",
        type=int,
        default=50,
        help="Maximo de pasadas de reconcile_run (default: 50).",
    )
    rp.add_argument(
        "--budget-visits",
        type=int,
        default=None,
        help="Limite de ejecuciones por nodo (S4 Etapa 7).",
    )
    rp.add_argument(
        "--budget-runtime-seconds",
        type=int,
        default=None,
        help="Limite (reservado) de duracion total en segundos (S4 Etapa 7).",
    )
    rp.add_argument(
        "--budget-events",
        type=int,
        default=None,
        help="Limite de eventos emitidos por el Run (S4 Etapa 7).",
    )

    # ----- expansion subcommand (H4 Slice 1) ---------------------------
    # DISCOVER -> PROPOSE -> VALIDATE -> AUTHORIZE -> APPLY.
    # Ver specs/h4-slice-1.md y blueprint §5 §5-§6.
    ex = sub.add_parser(
        "expansion",
        help="Expansion controlada del WorkflowPlan (H4).",
    )
    ex_sub = ex.add_subparsers(dest="expansion_command", required=True)

    ep = ex_sub.add_parser(
        "propose",
        help="Crea una propuesta desde un archivo JSON.",
    )
    ep.add_argument("project", help="Proyecto destino (debe existir).")
    ep.add_argument(
        "proposal_json",
        type=Path,
        help="Archivo JSON con la propuesta.",
    )

    ea = ex_sub.add_parser(
        "apply",
        help="Aplica una propuesta (validacion + APPLY).",
    )
    ea.add_argument("project", help="Proyecto destino.")
    ea.add_argument("--proposal", type=Path, required=True)
    ea.add_argument(
        "--plan-file",
        type=Path,
        default=None,
        help="WorkflowPlan a expandir (default: <data>/plans/<project>.json).",
    )

    er = ex_sub.add_parser(
        "rejections",
        help="Lista propuestas rechazadas (UAT-09 evidencia).",
    )
    er.add_argument("project", help="Proyecto destino.")

    eval_p = ex_sub.add_parser(
        "validate",
        help="Solo valida, no aplica. Imprime el resultado.",
    )
    eval_p.add_argument("project", help="Proyecto destino.")
    eval_p.add_argument("--proposal", type=Path, required=True)
    eval_p.add_argument("--plan-file", type=Path, default=None)

    # ----- slice-3 subcommands -----
    el = ex_sub.add_parser(
        "list",
        help="Lista propuestas registradas (slice-3).",
    )
    el.add_argument("project", help="Proyecto destino.")
    el.add_argument(
        "--stage",
        choices=("PROPOSED", "EVALUATED", "AUTHORIZED", "APPLIED", "REJECTED", "ARCHIVED"),
        default=None,
        help="Filtra por stage (default: todas).",
    )

    es = ex_sub.add_parser(
        "show",
        help="Muestra una propuesta por proposal_id (slice-3).",
    )
    es.add_argument("project", help="Proyecto destino.")
    es.add_argument("proposal_id", help="ID de la propuesta a mostrar.")

    ea2 = ex_sub.add_parser(
        "archive",
        help="Archiva una propuesta (stage ARCHIVED, slice-3).",
    )
    ea2.add_argument("project", help="Proyecto destino.")
    ea2.add_argument("proposal_id", help="ID de la propuesta a archivar.")

    # ----- knowledge subcommand (H3 Slice 5) -----
    kn = sub.add_parser(
        "knowledge",
        help="Gestion del subsistema de conocimiento (H3).",
    )
    kn_sub = kn.add_subparsers(dest="knowledge_command", required=True)

    # ----- runs subcommand (Etapa 7 / S1) -----
    # Gestion del ciclo de vida de Runs existentes (cancel, etc.).
    # No crea Runs: eso es `sg run <project> <plan>`.
    rn = sub.add_parser(
        "runs",
        help="Operaciones sobre Runs existentes.",
    )
    rn_sub = rn.add_subparsers(dest="runs_command", required=True)

    # sg runs list <project> [--state S] [--limit N]
    rl = rn_sub.add_parser(
        "list",
        help="Lista Runs existentes (mas reciente primero).",
    )
    rl.add_argument("project", help="Proyecto destino.")
    rl.add_argument(
        "--state",
        default=None,
        help="Filtra por estado (CREATED, ACTIVE, COMPLETED, FAILED, CANCELLED).",
    )
    rl.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Numero maximo de Runs a listar (default 20).",
    )

    # sg runs show <project> <run-id>
    rs = rn_sub.add_parser(
        "show",
        help="Muestra el snapshot de un Run.",
    )
    rs.add_argument("project", help="Proyecto destino.")
    rs.add_argument("run_id", help="Run ID a inspeccionar.")

    # sg runs logs <project> <run-id> [--limit N]
    rl2 = rn_sub.add_parser(
        "logs",
        help="Muestra el timeline de eventos de un Run.",
    )
    rl2.add_argument("project", help="Proyecto destino.")
    rl2.add_argument("run_id", help="Run ID a inspeccionar.")
    rl2.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Numero maximo de eventos a mostrar (default: todos).",
    )

    rc = rn_sub.add_parser(
        "cancel",
        help="Cancela un Run en curso (ACTIVE/WAITING/CREATED).",
    )
    rc.add_argument("project", help="Proyecto destino.")
    rc.add_argument("run_id", help="Run ID a cancelar.")

    # sg runs budget <project> <run-id>
    rbu = rn_sub.add_parser(
        "budget",
        help="Muestra el RunBudget activo de un Run (S4 Etapa 7).",
    )
    rbu.add_argument("project", help="Proyecto destino.")
    rbu.add_argument("run_id", help="Run ID a inspeccionar.")

    ks = kn_sub.add_parser("stale", help="Lista Claims stale.")
    ks.add_argument("project", help="Proyecto destino.")

    ki = kn_sub.add_parser("invalidate", help="Invalida Claims desde un source.")
    ki.add_argument("project", help="Proyecto destino.")
    ki.add_argument("--source", required=True, help="source_id a invalidar.")
    ki.add_argument("--max-hops", type=int, default=2, help="Cap de hops (default 2).")

    kr = kn_sub.add_parser("refresh", help="Refresca Claims de un source.")
    kr.add_argument("project", help="Proyecto destino.")
    kr.add_argument("--source", required=True, help="source_id a refrescar.")
    kr.add_argument(
        "--revision",
        required=True,
        help="Nueva revision que re-valida los Claims stale.",
    )

    kc = kn_sub.add_parser("compile", help="Compila un handoff.")
    kc.add_argument("project", help="Proyecto destino.")
    kc.add_argument(
        "recipe",
        help='source_id o JSON literal "{"..."} con la receta completa.',
    )
    kc.add_argument("--strict", action="store_true", help="Aplica strict freshness.")
    kc.add_argument("--token-budget", type=int, default=8000, help="Chars maximos.")
    kc.add_argument(
        "--overflow",
        default="drop_optional",
        choices=["drop_optional", "fail", "truncate_finding"],
        help="Que hacer si overflow (default drop_optional).",
    )
    kc.add_argument("--run", default=None, help="run_id del handoff.")
    kc.add_argument("--node", default=None, help="node_execution_id.")
    kc.add_argument("--revision", default=None, help="source_revision del handoff.")

    kt = kn_sub.add_parser("trace", help="Extrae un OutcomeTrace desde run.")
    kt.add_argument("project", help="Proyecto destino.")
    kt.add_argument("--run", required=True, help="run_id del que extraer trace.")
    kt.add_argument("--name", default=None, help="Nombre del trace (opcional).")

    return p


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

    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "project" and args.project_command == "create":
            return cmd_project_create(args)
        if args.command == "project" and args.project_command == "list":
            return cmd_project_list(args)
        if args.command == "project" and args.project_command == "inspect":
            return cmd_project_inspect(args)
        if args.command == "brick":
            return cmd_brick_register(args)
        if args.command == "pack" and args.pack_command == "import":
            return cmd_pack_import(args)
        if args.command == "pack" and args.pack_command == "load":
            return cmd_pack_load(args)
        if args.command == "promotion" and args.promotion_command == "submit":
            return cmd_promotion_submit(args)
        if args.command == "promotion" and args.promotion_command == "list":
            return cmd_promotion_list(args)
        if args.command == "promotion" and args.promotion_command == "reconcile":
            return cmd_promotion_reconcile(args)
        if args.command == "run":
            return cmd_run(args)
        if args.command == "runs":
            return _route_runs(args)
        if args.command == "knowledge":
            return _route_knowledge(args)
        if args.command == "expansion":
            return _route_expansion(args)
    except SkillGraphError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_DOMAIN

    parser.print_help()
    return EXIT_USAGE


def _route_runs(args: argparse.Namespace) -> int:
    """Enruta subcommand `runs` al handler correspondiente."""
    sub = args.runs_command
    if sub == "list":
        return cmd_runs_list(args)
    if sub == "show":
        return cmd_runs_show(args)
    if sub == "logs":
        return cmd_runs_logs(args)
    if sub == "cancel":
        return cmd_runs_cancel(args)
    if sub == "budget":
        return cmd_runs_budget(args)
    print(f"ERROR: runs subcommand no reconocido: {sub!r}", file=sys.stderr)
    return EXIT_USAGE


def _open_project_storage(args: argparse.Namespace) -> tuple[Storage | None, int]:
    """Abre el Storage de un proyecto o devuelve exit code de error.

    Helper para `cmd_runs_*`. Centraliza la resolucion del proyecto
    y la apertura del Storage (los handlers list/show/cancel la
    comparten). Devuelve (storage, EXIT_OK) o (None, exit_code).
    """
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
    if err is not None:
        return None, err
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        return None, EXIT_DB_MISSING
    return Storage(db_path), EXIT_OK


def cmd_runs_list(args: argparse.Namespace) -> int:
    """Lista Runs del proyecto via `RunController.list_runs`.

    Read-only: no emite eventos. Salida CSV-like para legibilidad
    en shell (una linea por run con columnas estables).
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    storage, err = _open_project_storage(args)
    if err != EXIT_OK or storage is None:
        return err
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, _ = resolver.lookup(args.project)
    ctl = RunController(
        storage=storage,
        adapter=FakeAgentAdapter(Path("/dev/null")),  # list no invoca adapter
    )
    runs = ctl.list_runs(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        state=args.state,
        limit=args.limit,
    )
    if not runs:
        print("(sin runs)")
        return EXIT_OK
    print(
        f"{'run_id':<40} {'state':<11} {'current_node':<20} "
        f"{'executed':<10} {'events':<8}"
    )
    for r in runs:
        print(
            f"{r.run_id:<40} {r.state:<11} "
            f"{(r.current_node or '-'):<20} "
            f"{','.join(r.executed_nodes):<10} {r.events_emitted:<8}"
        )
    return EXIT_OK


def cmd_runs_show(args: argparse.Namespace) -> int:
    """Muestra el snapshot de un Run via `RunController.show_run`.

    Read-only: no emite eventos. Salida en formato key=value para
    que un caller shell pueda parsear con awk/cut.
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    storage, err = _open_project_storage(args)
    if err != EXIT_OK or storage is None:
        return err
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, _ = resolver.lookup(args.project)
    ctl = RunController(
        storage=storage,
        adapter=FakeAgentAdapter(Path("/dev/null")),  # show no invoca adapter
    )
    snap = ctl.show_run(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        run_id=args.run_id,
    )
    print(f"run_id={snap.run_id}")
    print(f"state={snap.state}")
    print(f"current_node={snap.current_node or '-'}")
    print(f"executed_nodes={','.join(snap.executed_nodes) or '-'}")
    print(f"events_emitted={snap.events_emitted}")
    return EXIT_OK


def cmd_runs_logs(args: argparse.Namespace) -> int:
    """Muestra el timeline de eventos de un Run via `RunController.logs_run`.

    Read-only: no emite eventos. Salida CSV-like con una linea por
    evento: `seq event_kind timestamp payload_summary`.
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    storage, err = _open_project_storage(args)
    if err != EXIT_OK or storage is None:
        return err
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, _ = resolver.lookup(args.project)
    ctl = RunController(
        storage=storage,
        adapter=FakeAgentAdapter(Path("/dev/null")),  # logs no invoca adapter
    )
    logs = ctl.logs_run(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        run_id=args.run_id,
    )
    if args.limit is not None:
        logs = logs[: args.limit]
    if not logs:
        print("(sin eventos)")
        return EXIT_OK
    print(f"{'seq':<6} {'event_kind':<22} {'timestamp':<26} payload")
    for entry in logs:
        # Resumen corto del payload (primer nivel clave=valor).
        kv = ",".join(
            f"{k}={v!s:.40}" for k, v in entry.event.payload.items()
        )
        print(
            f"{entry.sequence:<6} {entry.event.event_kind:<22} "
            f"{entry.event.timestamp:<26} {kv}"
        )
    return EXIT_OK


def cmd_runs_cancel(args: argparse.Namespace) -> int:
    """Cancela un Run existente via `RunController.cancel_run`.

    No necesita Adapter: la cancelacion ocurre en la capa de
    orquestacion sin volver a invocar al agente. La operacion
    es atomica (transicion de estado + evento RunCompleted en
    una sola TX, via `transition_run_state_atomically`).
    """
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunController

    storage, err = _open_project_storage(args)
    if err != EXIT_OK or storage is None:
        return err
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, _ = resolver.lookup(args.project)
    ctl = RunController(
        storage=storage,
        adapter=FakeAgentAdapter(Path("/dev/null")),  # cancel no invoca adapter
    )
    snap = ctl.cancel_run(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        run_id=args.run_id,
    )
    print(f"run_id={snap.run_id} state={snap.state}")
    return EXIT_OK


def cmd_runs_budget(args: argparse.Namespace) -> int:
    """Muestra el RunBudget activo de un Run (S4 Etapa 7).

    Read-only: NO emite eventos. Si el Run no tiene budget, imprime
    `(sin budget)`. Salida key=value parseable con awk/cut.
    """
    storage, err = _open_project_storage(args)
    if err != EXIT_OK or storage is None:
        return err
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, _ = resolver.lookup(args.project)
    # Validamos existencia del Run con un try/except explicito para
    # emitir un mensaje de error claro cuando es NotFoundError.
    from skillgraph.core.errors import NotFoundError

    try:
        storage.get_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=args.run_id,
        )
    except NotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_DOMAIN

    row = storage.get_budget(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        run_id=args.run_id,
    )
    if row is None:
        print("(sin budget)")
        return EXIT_OK
    print(f"run_id={args.run_id}")
    print(f"max_visits={row['max_visits'] if row['max_visits'] is not None else '-'}")
    print(
        "max_runtime_seconds="
        f"{row['max_runtime_seconds'] if row['max_runtime_seconds'] is not None else '-'}"
    )
    print(
        "max_events="
        f"{row['max_events'] if row['max_events'] is not None else '-'}"
    )
    return EXIT_OK


def _route_knowledge(args: argparse.Namespace) -> int:
    """Enruta subcommand `knowledge` al handler correspondiente."""
    sub = args.knowledge_command
    if sub == "stale":
        return cmd_knowledge_stale(args)
    if sub == "invalidate":
        return cmd_knowledge_invalidate(args)
    if sub == "refresh":
        return cmd_knowledge_refresh(args)
    if sub == "compile":
        return cmd_knowledge_compile(args)
    if sub == "trace":
        return cmd_knowledge_trace(args)
    parser_local = _build_parser()
    parser_local.parse_args(["knowledge", "--help"])
    return EXIT_USAGE  # unreachable


def _route_expansion(args: argparse.Namespace) -> int:
    """Enruta subcommand `expansion` al handler correspondiente."""
    sub = args.expansion_command
    if sub == "propose":
        return cmd_expansion_propose(args)
    if sub == "apply":
        return cmd_expansion_apply(args)
    if sub == "validate":
        return cmd_expansion_validate(args)
    if sub == "rejections":
        return cmd_expansion_rejections(args)
    if sub == "list":
        return cmd_expansion_list(args)
    if sub == "show":
        return cmd_expansion_show(args)
    if sub == "archive":
        return cmd_expansion_archive(args)
    parser_local = _build_parser()
    parser_local.parse_args(["expansion", "--help"])
    return EXIT_USAGE  # unreachable


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
            spec = _json.loads(row.get("spec_json", "{}") or "{}")
        except (ValueError, TypeError):
            spec = {}
        try:
            declare_types_from_pack(
                reg,
                Brick(
                    identity=ResourceIdentity(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        namespace=row.get("namespace", "shared"),
                        kind="DomainPack",
                        name=row.get("name", "?"),
                    ),
                    api_version=row.get("api_version", "skillgraph.dev/v1alpha1"),
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
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
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
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
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
    from datetime import UTC, datetime

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

    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
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
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
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


def cmd_promotion_reconcile(args: argparse.Namespace) -> int:
    """Reconcilia propuestas PENDING/IN_PROGRESS: aplica sin duplicar.

    Recorrido UAT-13: interrumpir el proceso (crash/failpoint) y
    re-invocar `promotion reconcile` completa la operacion sin
    duplicar el claim en el catalogo destino.
    """

    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
    if err is not None:
        return err
    tenant_id = project["tenant_id"]
    target = args.target or args.project

    # El apply debe escribir en la base del PROYECTO DESTINO (el outbox
    # vive en origen; el claim promovido vive en destino).
    dest_project, err = resolver.lookup(target)
    if err is not None:
        print(
            f"ERROR: proyecto destino {target!r} no existe; crealo antes de reconciliar.",
            file=sys.stderr,
        )
        return EXIT_DOMAIN
    dest_storage = Storage(Path(dest_project["db_path"]))
    storage = Storage(Path(project["db_path"]))
    try:
        apply_fn = _default_claim_importer(
            dest_storage, tenant_id=tenant_id, target_project=dest_project["name"]
        )
        # FAILPOINT de prueba (H8): simula un crash a mitad del apply.
        # SKILLGRAPH_FAILPOINT_PROMOTION=before_apply  -> os._exit(9) tras
        #   leer las pendientes pero ANTES de aplicar cualquiera.
        # SKILLGRAPH_FAILPOINT_PROMOTION=after_apply_first -> os._exit(9)
        #   justo despues de aplicar la primera (claim ya en destino pero
        #   outbox sin marcar PUBLISHED: el estado exacto post-crash).
        failpoint = os.environ.get("SKILLGRAPH_FAILPOINT_PROMOTION")
        if failpoint == "before_apply":
            sys.stderr.write("FAILPOINT: before_apply\n")
            sys.stderr.flush()
            os._exit(9)
        results: list[dict[str, str]] = []
        for proposal in storage.list_pending_promotions():
            from skillgraph.governance.promotion import apply_proposal

            # FAILPOINT mid_apply: el apply de negocio ya se ejecuto
            # (o se ejecutaria ahora) pero el outbox sigue sin marcar
            # PUBLISHED. Simula crash exactamente entre ambos efectos.
            if failpoint == "mid_apply":
                storage.mark_promotion_in_progress(proposal["proposal_id"])
                sys.stderr.write("FAILPOINT: mid_apply\n")
                sys.stderr.flush()
                os._exit(9)
            final_status = apply_proposal(storage, proposal["proposal_id"], apply_fn=apply_fn)
            results.append({"proposal_id": proposal["proposal_id"], "status": final_status})
    finally:
        storage.close()
        dest_storage.close()
    if not results:
        print("(nada que reconciliar)")
        return EXIT_OK
    published = sum(1 for r in results if r["status"] == "PUBLISHED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
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

    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
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


def cmd_run(args: argparse.Namespace) -> int:
    """Crea un Run desde un WorkflowPlan.md y reconcilia hasta terminal.

    Cierra H2 por la via UAT: el usuario real ejecuta el CLI.
    """
    from skillgraph.core.runtime_types import is_terminal_run_state
    from skillgraph.platform.paths import agents_root
    from skillgraph.resources.plan_loader import load_plan_file
    from skillgraph.runtime.agent import FakeAgentAdapter
    from skillgraph.runtime.runcontroller import RunBudget, RunController

    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(args.project)
    if err is not None:
        return err
    if not args.plan.is_file():
        print(
            f"ERROR: plan no encontrado: {args.plan}",
            file=sys.stderr,
        )
        return EXIT_PLAN_NOT_FOUND
    try:
        plan = load_plan_file(args.plan)
    except ParseError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_PARSE
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        return EXIT_DB_MISSING

    fixtures_root = args.fixtures_root or agents_root(resolver.data_root)
    fixtures_root.mkdir(parents=True, exist_ok=True)
    adapter = FakeAgentAdapter(fixtures_root)
    storage = Storage(db_path)
    try:
        ctl = RunController(
            storage=storage,
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
        # UAT-06 (fix): max_iterations cuenta TODAS las llamadas reconcile,
        # incluida la primera. Antes habia una llamada externa al while
        # que ejecutaba 1 nodo, y luego el while iteraba max_iterations
        # veces mas, dando un total de 1 + max_iterations reconciliaciones.
        # Con max-iterations=2 sobre un plan de 3 nodos, eso ejecutaba los
        # 3 nodos en lugar de respetar el limite. Aqui contamos la
        # primera como iterations=1 y luego iteramos hasta max_iterations.
        iterations = 1
        snap = ctl.reconcile_run(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            run_id=run_id,
        )
        while not is_terminal_run_state(snap.state) and iterations < args.max_iterations:
            iterations += 1
            snap = ctl.reconcile_run(
                tenant_id=project["tenant_id"],
                project_id=project["name"],
                run_id=run_id,
            )
        if not is_terminal_run_state(snap.state) and iterations >= args.max_iterations:
            print(
                f"WARN: max-iterations alcanzado ({args.max_iterations}); "
                f"estado={snap.state} current={snap.current_node}",
                file=sys.stderr,
            )
    finally:
        storage.close()

    print(f"Run: {run_id}")
    print(f"Estado: {snap.state}")
    print(f"Nodos ejecutados: {', '.join(snap.executed_nodes) or '(ninguno)'}")
    print(f"Eventos emitidos: {snap.events_emitted}")
    print(f"Fixtures de agente: {fixtures_root}")
    # Codigos distintos segun estado para que el shell pueda
    # ramificar sin parsear la salida.
    if snap.state == "COMPLETED":
        return EXIT_OK
    if snap.state == "FAILED":
        return EXIT_RUN_FAILED
    return EXIT_RUN_INCOMPLETE


# ---------------------------------------------------------------------------
# H4 Slice 1: expansion controlada CLI (UAT-08/09)
# ---------------------------------------------------------------------------


def _open_project_or_error(
    args: argparse.Namespace, project_name: str
) -> tuple[dict[str, str] | None, int]:
    """Helper: resuelve un proyecto y abre su DB."""
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    project, err = resolver.lookup(project_name)
    if err is not None:
        return None, err
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        return None, EXIT_DB_MISSING
    return project, EXIT_OK


def _load_registry(project_db: Path, *, tenant_id: str, project_id: str) -> dict[str, str]:
    """Devuelve dict capability_name -> brick_ref, leido de los resources
    del proyecto.

    Usa la API publica ``Storage.list_resources`` (H1). Las capabilities
    viven en ``spec_json.spec.capabilities`` (JSON del brick).
    """
    storage = Storage(project_db)
    try:
        rows = storage.list_resources(tenant_id=tenant_id, project_id=project_id)
    finally:
        storage.close()
    out: dict[str, str] = {}
    for r in rows:
        try:
            spec = json.loads(r.get("spec_json", "{}") or "{}")
        except (ValueError, TypeError):
            continue
        caps = (spec or {}).get("capabilities", []) or []
        ns = r.get("namespace", "?")
        kind = r.get("kind", "?")
        name = r.get("name", "?")
        for cap in caps:
            out[cap] = f"{ns}:{kind}/{name}"
    return out


def _plan_path(project_dir: Path) -> Path:
    return project_dir / "plan.json"


def _load_plan_from_storage(project_dir: Path) -> WorkflowPlan:
    """Carga el WorkflowPlan asociado al proyecto desde ``<project_dir>/plan.json``.

    Si no existe, levanta EXIT_PLAN_NOT_FOUND. Para H4 slice-1 el formato
    es el mismo JSON que produce ``WorkflowPlan``-as-dict en tests; extendido
    en slice-2 (storage dedicado).
    """
    path = _plan_path(project_dir)
    if not path.is_file():
        print(
            f"ERROR: plan no encontrado en {path}. "
            "El slice-1 espera <data>/tenants/default/projects/<p>/plan.json",
            file=sys.stderr,
        )
        sys.exit(EXIT_PLAN_NOT_FOUND)
    import json as _json

    raw = _json.loads(path.read_text())
    nodes = tuple(
        WorkflowNode(
            name=n["name"],
            kind=n["kind"],
            namespace=n["namespace"],
            api_version=n["api_version"],
            resource_revision=n["resource_revision"],
            expected_result=n["expected_result"],
            capabilities=tuple(n.get("capabilities", ())),
            metadata=n.get("metadata", {}) or {},
        )
        for n in raw["nodes"]
    )
    transitions = tuple(
        WorkflowTransition(
            source=t["source"],
            outcome=t["outcome"],
            target=t["target"],
        )
        for t in raw.get("transitions", ())
    )
    return WorkflowPlan(
        nodes=nodes,
        initial=raw["initial"],
        transitions=transitions,
    )


def _load_plan_from_path(plan_path: Path) -> WorkflowPlan:
    """Carga un WorkflowPlan desde un archivo: JSON interno o YAML/Markdown.

    Slice-1: detecta por extension/presencia de front matter.
    - Si empieza con ``{`` -> JSON directo.
    - Si empieza con ``---\\n`` -> YAML via ``load_plan_file``.
    """
    raw = plan_path.read_text()
    stripped = raw.lstrip()
    if stripped.startswith("{"):
        return _load_plan_from_storage(plan_path.parent)
    return load_plan_file(plan_path)


def _write_plan_to_storage(project_dir: Path, plan: WorkflowPlan) -> None:
    """Persiste el plan nuevo tras ``apply_expansion``."""
    import json as _json

    payload = {
        "nodes": [
            {
                "name": n.name,
                "kind": n.kind,
                "namespace": n.namespace,
                "api_version": n.api_version,
                "resource_revision": n.resource_revision,
                "expected_result": n.expected_result,
                "capabilities": list(n.capabilities),
                "metadata": n.metadata,
            }
            for n in plan.nodes
        ],
        "initial": plan.initial,
        "transitions": [
            {"source": t.source, "outcome": t.outcome, "target": t.target} for t in plan.transitions
        ],
    }
    path = _plan_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(payload, indent=2, sort_keys=True))


def _ops_from_dict(ops_json: list[dict[str, object]]) -> tuple[object, ...]:
    """Deserializa la lista de operaciones PatchOp desde JSON."""
    ops: list[object] = []
    for op in ops_json:
        kind = op["op"]
        if kind == "add_node":
            node_data = op["node"]  # type: ignore[assignment]
            assert isinstance(node_data, dict)
            node = WorkflowNode(
                name=node_data["name"],
                kind=node_data["kind"],
                namespace=node_data["namespace"],
                api_version=node_data["api_version"],
                resource_revision=node_data["resource_revision"],
                expected_result=node_data["expected_result"],
                capabilities=tuple(node_data.get("capabilities", [])),
                metadata=node_data.get("metadata", {}) or {},
            )
            ops.append(AddNode(node=node))
        elif kind == "add_transition":
            t_data = op["transition"]  # type: ignore[assignment]
            assert isinstance(t_data, dict)
            trans = WorkflowTransition(
                source=t_data["source"],
                outcome=t_data["outcome"],
                target=t_data["target"],
            )
            ops.append(AddTransition(transition=trans))
        elif kind == "remove_transition":
            ops.append(
                RemoveTransition(
                    from_node=op["from_node"],  # type: ignore[arg-type]
                    outcome=op["outcome"],  # type: ignore[arg-type]
                )
            )
        else:
            raise ValidationError(f"op desconocida: {kind!r}")
    return tuple(ops)


def _load_proposal_json(path: Path) -> GraphExpansionProposal:
    """Carga una propuesta desde JSON, validando campos minimos."""
    import json as _json

    raw = _json.loads(path.read_text())
    auth_raw = raw["authorization"]
    authorization = Authorization(
        mode=auth_raw["mode"],
        granted_by=auth_raw.get("granted_by"),
        granted_at=auth_raw.get("granted_at"),
    )
    return propose(
        base_revision=raw["base_revision"],
        problem_observed=raw["problem_observed"],
        evidence=tuple(raw.get("evidence", [])),
        operations=_ops_from_dict(raw["operations"]),
        new_dependencies=tuple(raw.get("new_dependencies", [])),
        capabilities_needed=tuple(raw.get("capabilities_needed", [])),
        scope=raw.get("scope", "NODE"),
        attachment_point=raw["attachment_point"],
        rollback_plan=tuple(raw.get("rollback_plan", [])),
        authorization=authorization,
        author=raw["author"],
    )


def cmd_expansion_propose(args: argparse.Namespace) -> int:
    """``sg expansion propose <project> <proposal.json>``: imprime el proposal_id."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    try:
        proposal = _load_proposal_json(args.proposal_json)
    except (KeyError, ValueError, ValidationError) as exc:
        print(f"ERROR: propuesta invalida: {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposal_id": proposal.proposal_id,
        "author": proposal.author,
        "created_at": proposal.created_at,
        "problem_observed": proposal.problem_observed,
        "operations": str(args.proposal_json),
        "capabilities_needed": list(proposal.capabilities_needed),
        "new_dependencies": list(proposal.new_dependencies),
        "attachment_point": proposal.attachment_point,
        "authorization_mode": proposal.authorization.mode,
    }
    out = proposals_dir / f"{proposal.proposal_id}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Propuesta {proposal.proposal_id} registrada en {out}")
    return EXIT_OK


def cmd_expansion_apply(args: argparse.Namespace) -> int:
    """``sg expansion apply <project> --proposal P --plan-file F``: aplica."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    try:
        proposal = _load_proposal_json(args.proposal)
    except (KeyError, ValueError, ValidationError) as exc:
        print(f"ERROR: propuesta invalida: {exc}", file=sys.stderr)
        return EXIT_VALIDATION

    if args.plan_file is not None:
        # Carga desde Markdown+YAML o JSON interno (segun formato del archivo).
        plan = _load_plan_from_path(args.plan_file)
        # Persiste la version "canonica" del plan en project_dir/plan.json
        # para que ``apply`` pueda usarla como base y la propuesta modifique
        # ese archivo al aplicar.
        _write_plan_to_storage(project_dir, plan)
    try:
        plan = _load_plan_from_storage(project_dir)
    except SystemExit:
        return EXIT_PLAN_NOT_FOUND

    registry = _load_registry(
        Path(project["db_path"]),
        tenant_id=project["tenant_id"],
        project_id=project["name"],
    )
    result = apply_expansion(proposal, plan, registry=registry)

    if result.is_err():
        err = result.unwrap_err()
        rejection_path = record_rejection(
            proposal,
            reason=err.reason,
            rejected_by="validator-cli",
            project_dir=project_dir,
            violated_invariants=err.violated_invariants,
        )
        print(
            f"REJECTED: {proposal.proposal_id}: {err.reason} (violated={list(err.violated_invariants)})",
            file=sys.stderr,
        )
        print(f"Evidencia persistida en {rejection_path}", file=sys.stderr)
        return EXIT_DOMAIN

    new_plan = result.unwrap()
    _write_plan_to_storage(project_dir, new_plan)
    # Persiste la propuesta aplicada en ``expansion_proposals/`` (mismo
    # patron que ``cmd_expansion_propose``) para que ``list``/``show`` la
    # puedan descubrir tras el apply. Tambien crea el marker APPLIED,
    # analogo al marker ARCHIVED de ``cmd_expansion_archive``.
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_json = proposals_dir / f"{proposal.proposal_id}.json"
    if not proposal_json.is_file():
        proposal_json.write_text(
            json.dumps(
                {
                    "proposal_id": proposal.proposal_id,
                    "author": proposal.author,
                    "created_at": proposal.created_at,
                    "problem_observed": proposal.problem_observed,
                    "operations": str(args.proposal),
                    "capabilities_needed": list(proposal.capabilities_needed),
                    "new_dependencies": list(proposal.new_dependencies),
                    "attachment_point": proposal.attachment_point,
                    "authorization_mode": proposal.authorization.mode,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    applied_marker = proposals_dir / f"{proposal.proposal_id}.json.applied"
    applied_marker.write_text(
        json.dumps(
            {
                "proposal_id": proposal.proposal_id,
                "applied_at": _utcnow_iso(),
                "applied_by": "expansion-apply-cli",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"OK: {proposal.proposal_id} aplicado. Nuevo plan en {_plan_path(project_dir)}")
    print(f"Nodos antes: {len(plan.nodes)} -> despues: {len(new_plan.nodes)}")
    return EXIT_OK


def cmd_expansion_validate(args: argparse.Namespace) -> int:
    """``sg expansion validate ...``: imprime ValidationResult, no muta."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    try:
        proposal = _load_proposal_json(args.proposal)
    except (KeyError, ValueError, ValidationError) as exc:
        print(f"ERROR: propuesta invalida: {exc}", file=sys.stderr)
        return EXIT_VALIDATION

    if args.plan_file is not None:
        plan = _load_plan_from_path(args.plan_file)
        _write_plan_to_storage(project_dir, plan)
    try:
        plan = _load_plan_from_storage(project_dir)
    except SystemExit:
        return EXIT_PLAN_NOT_FOUND

    registry = _load_registry(
        Path(project["db_path"]),
        tenant_id=project["tenant_id"],
        project_id=project["name"],
    )
    result = validate(proposal, plan=plan, registry=registry)
    out = {
        "accepted": result.accepted,
        "reason": result.reason,
        "violated_invariants": list(result.violated_invariants),
        "warnings": list(result.warnings),
    }
    print(json.dumps(out, indent=2))
    return EXIT_OK if result.accepted else EXIT_DOMAIN


def cmd_expansion_rejections(args: argparse.Namespace) -> int:
    """``sg expansion rejections <project>``: lista rechazos persistidos."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    rej_dir = project_dir / "expansion_rejections"
    if not rej_dir.is_dir():
        print("(sin rechazos)")
        return EXIT_OK
    files = sorted(p for p in rej_dir.iterdir() if p.suffix == ".json")
    if not files:
        print("(sin rechazos)")
        return EXIT_OK
    for p in files:
        data = json.loads(p.read_text())
        print(
            f"- {data['proposal_id']}: reason={data['reason']!r} "
            f"rejected_by={data['rejected_by']!r} at={data['rejected_at']}"
        )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Slice-3 handlers: list / show / archive
# ---------------------------------------------------------------------------


def _scan_proposals_dir(proposals_dir: Path) -> list[tuple[Path, dict[str, object]]]:
    """Lee todos los JSON de propuestas. Devuelve (path, payload).

    Ignora silenciosamente archivos con JSON malformado (no rompe
    el comando entero por un archivo corrupto).
    """
    if not proposals_dir.is_dir():
        return []
    out: list[tuple[Path, dict[str, object]]] = []
    for p in sorted(proposals_dir.iterdir()):
        if p.suffix != ".json":
            continue
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            out.append((p, data))
    return out


def cmd_expansion_list(args: argparse.Namespace) -> int:
    """``sg expansion list <project> [--stage STAGE]``: lista propuestas.

    Slice-3: lee desde el directorio ``expansion_proposals/`` existente
    (JSON files planos, source-of-truth actual; ver specs/h4-slice-3.md
    limitacion 3). NO migra a SQLite (deferido slice-4).

    Stage inferido (precedencia: ARCHIVED > APPLIED > REJECTED > PROPOSED):
    - ARCHIVED: existe ``<proposal_id>.archived`` (marker file).
    - APPLIED: existe ``<proposal_id>.applied`` (marker file, creado por
      ``cmd_expansion_apply`` al persistir el nuevo plan).
    - REJECTED: hay un archivo en ``expansion_rejections/`` con ese proposal_id.
    - Si nada match: PROPOSED (estado inicial tras cmd_expansion_propose).
    """
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    rejections_dir = project_dir / "expansion_rejections"

    rejection_ids = _collect_rejection_ids(rejections_dir)

    rows = _scan_proposals_dir(proposals_dir)
    if not rows:
        print("(sin propuestas)")
        return EXIT_OK

    shown = 0
    for path, data in rows:
        proposal_id = str(data.get("proposal_id", path.stem))
        stage = _infer_proposal_stage(path, proposal_id, rejection_ids)
        if args.stage is not None and args.stage != stage:
            continue
        created = data.get("created_at", "?")
        author = data.get("author", "?")
        print(f"- {proposal_id}: stage={stage} author={author} created_at={created}")
        shown += 1
    if shown == 0:
        print(f"(sin propuestas en stage={args.stage})")
    return EXIT_OK


def cmd_expansion_show(args: argparse.Namespace) -> int:
    """``sg expansion show <project> <proposal_id>``: muestra la propuesta."""
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    rejections_dir = project_dir / "expansion_rejections"

    rejection_ids = _collect_rejection_ids(rejections_dir)

    rows = _scan_proposals_dir(proposals_dir)
    for path, data in rows:
        if str(data.get("proposal_id", "")) == args.proposal_id:
            stage = _infer_proposal_stage(path, str(data["proposal_id"]), rejection_ids)
            payload = {**data, "stage": stage}
            print(json.dumps(payload, indent=2, sort_keys=True))
            return EXIT_OK
    print(f"ERROR: proposal_id={args.proposal_id!r} no encontrado", file=sys.stderr)
    return EXIT_PROJECT_NOT_FOUND


def cmd_expansion_archive(args: argparse.Namespace) -> int:
    """``sg expansion archive <project> <proposal_id>``: marca ARCHIVED.

    Crea un marker file ``<proposal_id>.json.archived`` adyacente al
    proposal JSON. No borra el proposal (audit forense). Idempotente.
    """
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"

    rows = _scan_proposals_dir(proposals_dir)
    for path, data in rows:
        if str(data.get("proposal_id", "")) == args.proposal_id:
            marker = path.with_suffix(path.suffix + ".archived")
            marker.touch()
            print(f"Archived: {args.proposal_id} (marker={marker})")
            return EXIT_OK
    print(f"ERROR: proposal_id={args.proposal_id!r} no encontrado", file=sys.stderr)
    return EXIT_PROJECT_NOT_FOUND


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
