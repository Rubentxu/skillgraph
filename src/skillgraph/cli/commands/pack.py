"""Subcomandos `sg pack` (WI-54 corte 4, ADR-0018).

Cuarto corte del estrangulamiento H-02: los 2 handlers `cmd_pack_*`
salen de `cli/runner.py` verbatim. El constructor de registro es
compartido (cmd_init tambien lo usa) y vive en `cli.support`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from skillgraph import (
    BrickRegistry,
    ResourceIdentity,
    __version__,
    load_defaults,
    parse_file,
)
from skillgraph.cli.support import (
    EXIT_DB_MISSING,
    EXIT_OK,
    EXIT_PARSE,
    EXIT_VALIDATION,
    _build_registry_for_project,
    resolve_project,
)
from skillgraph.core.errors import NotFoundError, ParseError, ValidationError
from skillgraph.domain.pack_loader import declare_types_from_pack
from skillgraph.packaging import (
    FilaDePack,
    PackManifest,
    RegistroDePacks,
    actualizar,
    instalar,
    manifiesto_de,
    retirar,
)
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


# --- B11: el ciclo de vida sobre el registro de packs instalados ----------


def _registro_de(storage: Storage, project: dict[str, str]) -> RegistroDePacks:
    """El registro de lo instalado en ese proyecto, tal y como esta persistido.

    Pide `solo_instalados=False` a proposito: `retirar` necesita ver la fila
    retirada para poder distinguir «esta retirado» de «nunca estuvo», y con
    el filtro puesto las dos serian la misma lista vacia. El registro
    FILTRA por `instalado` cuando lo que se pide es lo que ve el operador.
    """
    return storage.installed_packs_repository().listar(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        solo_instalados=False,
    )


def _guardar(storage: Storage, fila: FilaDePack, project: dict[str, str]) -> None:
    storage.installed_packs_repository().guardar(
        fila, tenant_id=project["tenant_id"], project_id=project["name"]
    )


def _manifiesto_del_fichero(args: argparse.Namespace, project: dict[str, str]) -> PackManifest:
    """Lee el pack del fichero y devuelve su manifiesto.

    El manifiesto viaja en `spec.manifest` porque `spec` es la unica parte
    del pack que el tipo `DomainPack` acepta: su validador exige `version`
    y admite `capabilities`, y el resto de claves pasan. Meterlo ahi unifica
    los DOS contratos —el `Brick` de siempre y el `PackManifest` de B8— en
    vez de crear un tercero que habria que mantener en paralelo.
    """
    identidad = ResourceIdentity(
        tenant_id=project["tenant_id"],
        project_id=project["name"],
        namespace="(pending)",
        kind="(pending)",
        name="(pending)",
    )
    brick = parse_file(args.path, identity=identidad)
    if brick.kind != "DomainPack":
        raise ValidationError(
            f"se esperaba kind='DomainPack', recibio {brick.kind!r}: eso no es un pack instalable"
        )
    return manifiesto_de(brick)


def _operacion_de_ciclo(
    args: argparse.Namespace, operacion: Callable[..., tuple[RegistroDePacks, str]]
) -> int:
    """El cuerpo comun de `install` y `update`.

    No se separan por el cuerpo, que es el mismo, sino por la EXIGENCIA:
    `instalar` acepta la primera vez o una reinstalacion, `actualizar`
    exige que la version suba. El cuerpo comun es una linea; la exigencia
    es lo que diferencia los comandos, y por eso vive en el nucleo.
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    storage = Storage(Path(project["db_path"]))
    try:
        manifiesto = _manifiesto_del_fichero(args, project)
        registro = _registro_de(storage, project)
        nuevo, delta = operacion(registro, manifiesto, version_skillgraph=__version__)
        fila = next(f for f in nuevo if f.pack == manifiesto.name)
        _guardar(storage, fila, project)
    except ParseError as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_PARSE
    except (ValidationError, NotFoundError) as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    finally:
        storage.close()
    print(f"{manifiesto.name}@{manifiesto.version}: {delta}")
    print(f"aislamiento: {manifiesto.isolation}")
    print(f"requiere: {manifiesto.requires.describe()}")
    return EXIT_OK


def cmd_pack_install(args: argparse.Namespace) -> int:
    """Instala un pack: valida su manifiesto y lo deja vivo en el proyecto.

    Y NO declara los tipos del pack: de eso se encarga `sg pack load`, que ya
    existe. Dos comandos que hacen lo mismo con nombres distintos son la
    trampa de «conectar no es contener»: uno administra la INSTALACION —el
    contrato y su compatibilidad— y el otro el CONTENIDO y sus tipos.
    """
    return _operacion_de_ciclo(args, instalar)


def cmd_pack_update(args: argparse.Namespace) -> int:
    """Actualiza un pack: exige que la version nueva SUBA."""
    return _operacion_de_ciclo(args, actualizar)


def cmd_pack_remove(args: argparse.Namespace) -> int:
    """Retira un pack instalado. Lo que no esta se dice; no revienta.

    No borra la fila: la MARCA como retirada. Un `DELETE` perderia la unica
    respuesta que existe a «¿este proyecto ha tenido alguna vez este pack?»,
    que es justo la fila que se borraria.
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    storage = Storage(Path(project["db_path"]))
    try:
        registro = _registro_de(storage, project)
        retirado, delta = retirar(registro, args.name)
        fila = next(f for f in retirado if f.pack == args.name)
        _guardar(storage, fila, project)
    except (ValidationError, NotFoundError) as exc:
        print(f"ERROR ({exc.code}): {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    finally:
        storage.close()
    print(delta)
    return EXIT_OK


def cmd_pack_list(args: argparse.Namespace) -> int:
    """Lista los packs instalados: nombre, version y aislamiento.

    El aislamiento sale porque es contenido del contrato de B8: sin el,
    `list` responderia «que hay» pero no «cuanto de lo que hay es de fiar».
    """
    project, err = resolve_project(args, args.project)
    if err is not None:
        return err
    storage = Storage(Path(project["db_path"]))
    try:
        registro = storage.installed_packs_repository().listar(
            tenant_id=project["tenant_id"],
            project_id=project["name"],
            solo_instalados=True,
        )
    finally:
        storage.close()
    instalados = registro.instalados
    if not instalados:
        print(f"(no hay packs instalados en {args.project})")
        return EXIT_OK
    for fila in instalados:
        print(fila.describe())
    return EXIT_OK
