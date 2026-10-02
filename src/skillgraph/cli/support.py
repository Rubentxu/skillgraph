"""Helpers compartidos del CLI (WI-52, ADR-0018).

Extraidos verbatim de `cli/runner.py` (corte 1 del estrangulamiento
H-02). `runner` re-importa estos nombres, de modo que los call-sites
internos y la tabla de dispatch (WI-41) no se editan. Los componentes
de comando (`cli/commands/*`) importan desde aqui, nunca desde
`runner`, para no crear un ciclo de imports.

## Codigos de salida (AGENTS.md 11.15 / contrato CLI)

La tabla de los doce codigos vive en `cli/exit_codes.py`, un modulo hoja
sin imports, y aqui se reexporta para no romper a los importadores
previos. Lo movio ADR-0016 (WI-88): `parser.py` necesita `EXIT_USAGE`
para no devolver el 2 de `argparse`, que en esta CLI colisionaba con
`EXIT_BAD_NAME`; importar este modulo desde el parser habria arrastrado
`Storage`, `BrickRegistry`, `pack_loader`, `catalog`, `plan_loader` y
`workflow` — y el parser es, por diseño, autocontenido.

La forma `X as X` del import no es redundante: es la que ruff reconoce
como reexport intencional. Sin ella, F401 borra los nombres que este
modulo no usa internamente y rompe a sus importadores. Medido: al
migrar, `EXIT_DOMAIN` dejo de exportarse y
`cli/commands/expansion.py` dejo de importar. Leccion de la misma
familia que WI-81 (alias muertos) y WI-86 (capa de re-export muerta):
un re-export que el linter no puede ver como intencional, no es un
reexport, es un accidente a la espera de ocurrir.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from skillgraph import BrickRegistry, ResourceIdentity, load_defaults
from skillgraph.cli.exit_codes import (
    EXIT_BAD_NAME as EXIT_BAD_NAME,
    EXIT_DB_MISSING as EXIT_DB_MISSING,
    EXIT_DOMAIN as EXIT_DOMAIN,
    EXIT_OK as EXIT_OK,
    EXIT_PARSE as EXIT_PARSE,
    EXIT_PLAN_NOT_FOUND as EXIT_PLAN_NOT_FOUND,
    EXIT_PROJECT_EXISTS as EXIT_PROJECT_EXISTS,
    EXIT_PROJECT_NOT_FOUND as EXIT_PROJECT_NOT_FOUND,
    EXIT_RUN_FAILED as EXIT_RUN_FAILED,
    EXIT_RUN_INCOMPLETE as EXIT_RUN_INCOMPLETE,
    EXIT_USAGE as EXIT_USAGE,
    EXIT_VALIDATION as EXIT_VALIDATION,
)
from skillgraph.core.errors import SkillGraphError
from skillgraph.domain.pack_loader import declare_types_from_pack
from skillgraph.platform.paths import (
    DEFAULT_TENANT,
    catalog_path,
    resolve_data_root,
)
from skillgraph.platform.storage import Storage
from skillgraph.resources.bricks import Brick
from skillgraph.resources.catalog import open_catalog
from skillgraph.resources.plan_loader import load_plan_file
from skillgraph.resources.workflow import WorkflowNode, WorkflowPlan, WorkflowTransition


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


def resolve_project(args: argparse.Namespace, name: str) -> tuple[dict[str, str], int | None]:
    """Resuelve un proyecto del catalogo, con la raiz por defecto incluida.

    Punto UNICO de construccion del `ProjectResolver` (WI-44). Antes de
    este helper la construccion `ProjectResolver(data_root=...)` seguida
    de `.with_default_root()` se repetia 21 veces en el modulo.

    Deliberadamente NO unifica los tres helpers que lo consume. Cada uno
    reporta el fallo a su manera, y por eso no pueden componerse entre si:

    - `_open_known_project`    lanza FileNotFoundError
    - `_open_project_storage`  devuelve `(None, exit_code)` con contexto
    - `_open_project_or_error` devuelve `(None, exit_code)` y valida la DB

    Este helper solo resuelve el nombre. La validacion posterior
    (existencia de la DB, props del Storage) se queda donde estaba,
    porque forma parte del contrato de cada uno.

    Propaga el contrato de `ProjectResolver.lookup` sin traducirlo: el
    error viaja como exit code en la segunda posicion, y el primer
    elemento es `{}` en fallo. Por eso el consumidor decide mirando
    `err is not None`, no mirando si el proyecto es truthy.

    Returns:
        `(proyecto, None)` si el catalogo lo conoce, o `({}, exit_code)`
        con el error de `ProjectResolver.lookup`.
    """
    resolver = ProjectResolver(data_root=resolve_data_root(args.data_root)).with_default_root()
    return resolver.lookup(name)


def _open_project_or_error(
    args: argparse.Namespace, project_name: str
) -> tuple[dict[str, str] | None, int]:
    """Helper: resuelve un proyecto y valida que su DB exista."""
    project, err = resolve_project(args, project_name)
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


@contextmanager
def _open_project_storage(
    args: argparse.Namespace,
) -> Iterator[tuple[Storage | None, int]]:
    """Abre el Storage dentro de un contexto y devuelve exit code de error.

    Helper para `cmd_runs_*`. Centraliza la resolucion del proyecto,
    valida la base de datos y cierra el Storage al salir del bloque.
    Dentro del contexto devuelve `(storage, EXIT_OK)` o `(None, exit_code)`.
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        yield None, err
        return
    db_path = Path(project["db_path"])
    if not db_path.exists():
        print(
            f"ERROR: base de datos ausente: {db_path}",
            file=sys.stderr,
        )
        yield None, EXIT_DB_MISSING
        return
    storage = Storage(db_path)
    try:
        yield storage, EXIT_OK
    finally:
        storage.close()


# Variable de entorno que el UAT usa para simular un crash.

# Codigo de salida de un crash simulado. Distinto de cualquier EXIT_* del
# CLI para que un "crash" no se confunda con un error de dominio.


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
