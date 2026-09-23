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
import sys
from dataclasses import dataclass
from pathlib import Path

from skillgraph import (
    BrickRegistry,
    ResourceIdentity,
    load_defaults,
    parse_file,
)
from skillgraph.catalog import open_catalog
from skillgraph.errors import (
    ParseError,
    SkillGraphError,
    UnknownKindError,
    ValidationError,
)
from skillgraph.graph_expansion import (
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
from skillgraph.paths import (
    DEFAULT_TENANT,
    catalog_path,
    is_safe_name,
    project_db_path,
    resolve_data_root,
)
from skillgraph.plan_loader import load_plan_file
from skillgraph.storage import Storage
from skillgraph.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition

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


def _find_active_run_id(storage: Storage, *, tenant_id: str, project_id: str) -> str | None:
    """Devuelve el run_id del Run mas reciente en estado no terminal
    para (tenant, project), o None si no hay ninguno.

    No terminal = CREATED, ACTIVE o WAITING. COMPLETED/FAILED/CANCELLED
    se consideran terminales y el siguiente `run` debe crear uno nuevo.
    Cumple UAT-06: tras un crash con un run ACTIVE, el CLI lo encuentra
    y lo reanuda en lugar de crear uno nuevo.
    """
    conn = storage._conn  # type: ignore[attr-defined]
    row = conn.execute(
        """
        SELECT run_id FROM workflow_runs
        WHERE tenant_id = ? AND project_id = ?
          AND state IN ('CREATED', 'ACTIVE', 'WAITING')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        return None
    return row["run_id"]


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
    from skillgraph.knowledge_controller import KnowledgeController

    tenant_id, project_id, storage = _open_known_project(args, args.project)
    ctl = KnowledgeController(storage=storage, tenant_id=tenant_id, project_id=project_id)
    stale = ctl.list_stale_claims()
    print(f"stale claims ({len(stale)}):")
    for c in stale:
        print(f"  - {c.claim_id}  {c.predicate}={c.object_literal} stale=true")
    return EXIT_OK


def cmd_knowledge_invalidate(args: argparse.Namespace) -> int:
    """Invalida Claims dependientes de un source."""
    from skillgraph.knowledge_controller import KnowledgeController

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
    from skillgraph.knowledge_controller import KnowledgeController

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

    from skillgraph.context_controller import ContextController
    from skillgraph.knowledge_controller import KnowledgeController
    from skillgraph.recipe import ContextRecipe

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

    from skillgraph.context_controller import OutcomeTracer
    from skillgraph.knowledge_controller import KnowledgeController

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
        if args.command == "run":
            return cmd_run(args)
        if args.command == "knowledge":
            return _route_knowledge(args)
        if args.command == "expansion":
            return _route_expansion(args)
    except SkillGraphError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_DOMAIN

    parser.print_help()
    return EXIT_USAGE


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


def cmd_brick_register(args: argparse.Namespace) -> int:
    """Registra un brick en un proyecto, validándolo primero."""
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
        brick = parse_file(args.path, identity=identity)
    except ParseError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_PARSE
    try:
        registry.validate(brick)
    except (UnknownKindError, ValidationError) as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    storage = Storage(db_path)
    try:
        uid = storage.upsert_resource(brick)
    finally:
        storage.close()
    print(f"Brick registrado: {brick.kind}/{brick.identity.namespace}/{brick.identity.name}")
    print(f"UID: {uid}")
    return EXIT_OK


def cmd_pack_import(args: argparse.Namespace) -> int:
    """H5 skill_import: asimila una skill externa sin ejecutar su codigo.

    Pipeline: IMPORT -> ANALYZE -> STRUCTURE -> VALIDATE -> REGISTER.
    Conserva el material original (Source con content_hash + locator)
    y emite un informe de estructuracion en JSON. Las partes ambiguas
    permanecen senaladas; NO se presentan como decisiones verificadas.
    """
    from skillgraph.skill_importer import analyze_skill, register_imported_skill
    from skillgraph.storage import Storage

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
    from skillgraph.agent import FakeAgentAdapter
    from skillgraph.paths import agents_root
    from skillgraph.plan_loader import load_plan_file
    from skillgraph.runcontroller import RunController
    from skillgraph.runtime_types import is_terminal_run_state

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
            conn=storage._conn,  # type: ignore[attr-defined]
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
            run_id = ctl.create_run(
                tenant_id=project["tenant_id"],
                project_id=project["name"],
                plan=plan,
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

    Stage inferido:
    - ARCHIVED: existe ``<proposal_id>.archived`` (marker file).
    - APPLIED: existe un plan que contiene el nodo/tr de la propuesta.
      Por simplicidad slice-3 marcamos APPLIED solo si ARCHIVED+APPLIED
      marker existe; sino = PROPOSED (estado inicial tras cmd_expansion_propose).
    - REJECTED: hay un archivo en ``expansion_rejections/`` con ese proposal_id.
    - Si nada match: PROPOSED.
    """
    project, rc = _open_project_or_error(args, args.project)
    if rc != EXIT_OK:
        return rc
    assert project is not None
    project_dir = Path(project["db_path"]).parent
    proposals_dir = project_dir.parent.parent / "expansion_proposals"
    rejections_dir = project_dir / "expansion_rejections"

    rejection_ids: set[str] = set()
    if rejections_dir.is_dir():
        for p in rejections_dir.iterdir():
            if p.suffix != ".json":
                continue
            try:
                d = json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(d, dict) and "proposal_id" in d:
                rejection_ids.add(str(d["proposal_id"]))

    rows = _scan_proposals_dir(proposals_dir)
    if not rows:
        print("(sin propuestas)")
        return EXIT_OK

    shown = 0
    for path, data in rows:
        proposal_id = str(data.get("proposal_id", path.stem))
        archived_marker = path.with_suffix(path.suffix + ".archived")
        if archived_marker.is_file():
            stage = "ARCHIVED"
        elif proposal_id in rejection_ids:
            stage = "REJECTED"
        else:
            stage = "PROPOSED"
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

    rows = _scan_proposals_dir(proposals_dir)
    for _, data in rows:
        if str(data.get("proposal_id", "")) == args.proposal_id:
            print(json.dumps(data, indent=2, sort_keys=True))
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
