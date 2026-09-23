"""CLI de SkillGraph (Etapa 1).

Esta capa es deliberadamente delgada: el grueso de la lógica vive
en `skillgraph.storage`, `skillgraph.catalog` y `skillgraph.parser`.
Aquí solo se traduce argv -> llamadas + se formatea la salida.

Auditoria de duplicacion:
- No reimplements validacion de esquemas (eso vive en registry.py).
- No reimplements logica SQL (eso vive en storage.py y catalog.py).
"""

from __future__ import annotations

import argparse
import sys
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
    return 0


def cmd_project_create(args: argparse.Namespace) -> int:
    if not is_safe_name(args.name):
        print(
            f"ERROR: nombre de proyecto inválido {args.name!r}. "
            "Use solo [a-z0-9-_] y hasta 64 caracteres.",
            file=sys.stderr,
        )
        return 2

    root = resolve_data_root(args.data_root)
    cat = open_catalog(catalog_path(root))
    try:
        existing = cat.get_project(tenant_id=DEFAULT_TENANT, name=args.name)
        if existing is not None:
            print(
                f"ERROR: proyecto {args.name!r} ya existe para tenant {DEFAULT_TENANT!r}",
                file=sys.stderr,
            )
            return 3

        db = project_db_path(root, args.name, tenant=DEFAULT_TENANT)
        db.parent.mkdir(parents=True, exist_ok=True)
        storage = Storage(db)
        storage.close()
        cat.register_project(tenant_id=DEFAULT_TENANT, name=args.name, db_path=db)
    finally:
        cat.close()
    print(f"Proyecto {args.name!r} creado en: {db}")
    return 0


def cmd_project_list(args: argparse.Namespace) -> int:
    root = resolve_data_root(args.data_root)
    cat = open_catalog(catalog_path(root))
    try:
        projects = cat.list_projects(tenant_id=DEFAULT_TENANT)
    finally:
        cat.close()
    if not projects:
        print("(sin proyectos)")
        return 0
    for p in projects:
        print(f"{p['name']}\t{p['db_path']}\t{p['created_at']}")
    return 0


def cmd_project_inspect(args: argparse.Namespace) -> int:
    root = resolve_data_root(args.data_root)
    cat = open_catalog(catalog_path(root))
    try:
        project = cat.get_project(tenant_id=DEFAULT_TENANT, name=args.name)
        if project is None:
            print(
                f"ERROR: proyecto {args.name!r} no existe para tenant {DEFAULT_TENANT!r}",
                file=sys.stderr,
            )
            return 4
        db_path = Path(project["db_path"])
        if not db_path.exists():
            print(
                f"ERROR: base de datos ausente: {db_path}",
                file=sys.stderr,
            )
            return 5
        storage = Storage(db_path)
        try:
            counts = _count_resources(
                storage,
                tenant_id=project["tenant_id"],
                project_id=project["name"],
            )
        finally:
            storage.close()
    finally:
        cat.close()

    print(f"Proyecto: {project['name']}")
    print(f"Tenant:   {project['tenant_id']}")
    print(f"DB:       {project['db_path']}")
    print(f"Creado:   {project['created_at']}")
    print(f"Recursos: {counts['total']} total")
    for kind, n in sorted(counts["by_kind"].items()):
        print(f"  {kind}: {n}")
    return 0


def _count_resources(storage: Storage, *, tenant_id: str, project_id: str) -> dict[str, object]:
    rows = storage.list_resources(tenant_id=tenant_id, project_id=project_id)
    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
    return {"total": len(rows), "by_kind": by_kind}


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

    return p


def main(argv: list[str] | None = None) -> int:
    from skillgraph import __version__

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"skillgraph {__version__}")
        return 0

    if args.command is None:
        parser.print_help()
        return 0

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
    except SkillGraphError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return 10

    parser.print_help()
    return 1


def cmd_brick_register(args: argparse.Namespace) -> int:
    """Registra un brick en un proyecto, validándolo primero."""
    root = resolve_data_root(args.data_root)
    cat = open_catalog(catalog_path(root))
    try:
        project = cat.get_project(tenant_id=DEFAULT_TENANT, name=args.project)
        if project is None:
            print(
                f"ERROR: proyecto {args.project!r} no existe",
                file=sys.stderr,
            )
            return 4
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
            return 11
        try:
            registry.validate(brick)
        except (UnknownKindError, ValidationError) as exc:
            print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
            return 12
        storage = Storage(db_path)
        try:
            uid = storage.upsert_resource(brick)
        finally:
            storage.close()
    finally:
        cat.close()
    print(f"Brick registrado: {brick.kind}/{brick.identity.namespace}/{brick.identity.name}")
    print(f"UID: {uid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
