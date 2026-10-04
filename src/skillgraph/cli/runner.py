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
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    pass

from skillgraph import (
    BrickRegistry,
    ResourceIdentity,
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
from skillgraph.cli.commands.knowledge import (
    cmd_knowledge_compile,
    cmd_knowledge_invalidate,
    cmd_knowledge_refresh,
    cmd_knowledge_stale,
    cmd_knowledge_trace,
)
from skillgraph.cli.commands.pack import (
    cmd_pack_import,
    cmd_pack_install,
    cmd_pack_list,
    cmd_pack_load,
    cmd_pack_remove,
    cmd_pack_update,
)
from skillgraph.cli.commands.promotion import (
    cmd_promotion_list,
    cmd_promotion_reconcile,
    cmd_promotion_submit,
)
from skillgraph.cli.commands.run import (
    cmd_run,
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
    _build_registry_for_project,
    _open_project_storage,
    exit_para,
    resolve_project,
)
from skillgraph.core.errors import (
    ParseError,
    SkillGraphError,
    UnknownKindError,
    ValidationError,
)
from skillgraph.governance.backups import (
    create_backup,
    default_backup_dir,
    list_backups,
    restore_backup,
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


# ---------------------------------------------------------------------------
# Comandos knowledge (H3 Slice 5)
# ---------------------------------------------------------------------------


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
        # WI-109: el `code` decide el exit code, no el tipo de la excepcion.
        # Antes este `return EXIT_DOMAIN` colapsaba TODO error de dominio a
        # 10, y los codigos 11/12 solo se alcanzaban porque cada comando
        # repetia su propio `except ParseError`. La regla de AGENTS.md 1.2
        # ("cada excepcion lleva un code... usado por la CLI para traducir
        # a exit codes") no era cierta; ahora la cumple `exit_para`.
        return exit_para(exc)
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


# Nombres de failpoint reconocidos en `sg promotion reconcile` (H8/UAT-13).
# Valor cerrado: un nombre desconocido no dispara nada, para que un typo en
# la variable de entorno no tumbe un run real por accidente.


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
        ("pack", "install"): cmd_pack_install,
        ("pack", "list"): cmd_pack_list,
        ("pack", "load"): cmd_pack_load,
        ("pack", "remove"): cmd_pack_remove,
        ("pack", "update"): cmd_pack_update,
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
    "cmd_pack_install",
    "cmd_pack_list",
    "cmd_pack_remove",
    "cmd_pack_update",
    "cmd_project_create",
    "cmd_project_inspect",
    "cmd_project_list",
    "cmd_run",
    "main",
    # Re-exported for monkeypatching in tests.
    "open_catalog",
]
