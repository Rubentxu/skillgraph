"""Subcomandos `sg pack` (WI-54 corte 4, ADR-0018).

Cuarto corte del estrangulamiento H-02: los 2 handlers `cmd_pack_*`
salen de `cli/runner.py` verbatim. El constructor de registro es
compartido (cmd_init tambien lo usa) y vive en `cli.support`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillgraph import BrickRegistry, ResourceIdentity, load_defaults, parse_file
from skillgraph.cli.support import (
    EXIT_DB_MISSING,
    EXIT_OK,
    EXIT_PARSE,
    EXIT_VALIDATION,
    _build_registry_for_project,
    resolve_project,
)
from skillgraph.core.errors import ParseError, ValidationError
from skillgraph.domain.pack_loader import declare_types_from_pack
from skillgraph.platform.storage import Storage


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
