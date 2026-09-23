"""CLI mínima del núcleo SkillGraph.

Etapa 1: `init`, `project create/list/inspect`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skillgraph",
        description="SkillGraph: workflows declarativos para agentes.",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Raíz de datos interna (por defecto: ~/.local/share/skillgraph).",
    )
    p.add_argument("--version", action="store_true", help="Muestra la versión y sale.")
    sub = p.add_subparsers(dest="command", required=False)

    sub.add_parser("init", help="Inicializa el directorio de datos raíz.")

    proj = sub.add_parser("project", help="Gestión de proyectos.")
    proj_sub = proj.add_subparsers(dest="project_command", required=True)
    pc = proj_sub.add_parser("create", help="Crea un proyecto.")
    pc.add_argument("name", help="Nombre del proyecto (slug, único por tenant).")
    proj_sub.add_parser("list", help="Lista proyectos del tenant actual.")
    pi = proj_sub.add_parser("inspect", help="Inspecciona un proyecto.")
    pi.add_argument("name", help="Nombre del proyecto a inspeccionar.")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from skillgraph import __version__

        print(f"skillgraph {__version__}")
        return 0

    # El despacho real a controladores se implementa en WorkItems posteriores.
    # En este WorkItem solo dejamos el cableado y los mensajes contractuales.
    if args.command is None:
        parser.print_help()
        return 0

    print(
        f"[skillgraph {__version__}] comando={args.command!r} "
        f"(stub de bootstrap; pendiente de Etapa 1)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
