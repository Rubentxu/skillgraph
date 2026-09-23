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
from skillgraph.paths import (
    DEFAULT_TENANT,
    catalog_path,
    is_safe_name,
    project_db_path,
    resolve_data_root,
)
from skillgraph.storage import Storage

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
        if args.command == "run":
            return cmd_run(args)
        if args.command == "knowledge":
            return _route_knowledge(args)
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


if __name__ == "__main__":
    sys.exit(main())
