"""FileScope — H12 Scopes y consultas composables.

Destino (evolution-v2/plan/ROADMAP.md H12):
consultar conocimiento canonico desde fichero, directorio, paquete
y bounded context. Composicion sin duplicacion, con cobertura
global explicita y aislamiento por tenant/project.

Adaptado a las primitivas H11:
- No introduce tabla nueva. Opera sobre FileSignatures ya
  persistidas via Evidence(kind='file_signature').
- Funciones puras sin I/O (regla AGENTS §1.1/§1.3).
- ADT cerradas via Literal (regla AGENTS §2.1).
- Deduplicacion por ``foco`` (clave natural de FileSignature).
- Aislamiento por tenant/project delegado al KnowledgeController
  (cada controller ya inyecta tenant_id+project_id).

Scopes soportados:

- ``file``: una sola signature de un source.
- ``directory``: conjunto de sources bajo un directorio (membresia
  declarada por el caller, NO inference por prefijo).
- ``package``: conjunto de sources con membresia logica (un paquete
  Python cuyos modulos pueden estar dispersos en el filesystem).
- ``bounded_context``: agrupacion explicita que cruza paquetes y se
  usa para definir fronteras de diseno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.file_signature import FileSignature

# --- ADT cerrada (regla AGENTS §2.1) ---------------------------------


FileScope = Literal["file", "directory", "package", "bounded_context"]

FILE_SCOPES: frozenset[str] = frozenset(
    {"file", "directory", "package", "bounded_context"}
)


# --- Validators (smart constructors) --------------------------------


_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*$")
_BOUNDED_CONTEXT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def validate_package_name(name: str) -> str:
    """Valida un nombre de paquete Python (dot-separated)."""
    if not _PACKAGE_NAME_RE.match(name):
        raise ValidationError(f"package_name invalido: {name!r}")
    return name


def validate_bounded_context_name(name: str) -> str:
    """Valida un nombre de bounded context."""
    if not _BOUNDED_CONTEXT_NAME_RE.match(name):
        raise ValidationError(f"bounded_context_name invalido: {name!r}")
    return name


# --- Dataclasses frozen ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ScopeQuery:
    """Consulta declarativa sobre un scope de conocimiento.

    Un ScopeQuery NO resuelve por si mismo: delega en su
    ``scope_kind`` correspondiente (ver ``resolve_*_scope``).
    """

    scope_kind: FileScope
    target: str

    def __post_init__(self) -> None:
        if self.scope_kind not in FILE_SCOPES:
            raise ValidationError(
                f"scope_kind invalido: {self.scope_kind!r} "
                f"(esperaba uno de {sorted(FILE_SCOPES)})"
            )
        if not self.target:
            raise ValidationError("ScopeQuery.target no puede estar vacio")
        # Validacion especifica por kind.
        if self.scope_kind == "package":
            validate_package_name(self.target)
        elif self.scope_kind == "bounded_context":
            validate_bounded_context_name(self.target)


@dataclass(frozen=True, slots=True)
class ScopeResolution:
    """Resultado de resolver un ScopeQuery en miembros concretos.

    ``member_source_ids`` es la lista de source_ids que pertenecen
    al scope, en el orden declarado por el caller (NO ordenados,
    NO deduplicados: el caller es responsable de pasarlos como
    quiera consumirlos).
    """

    scope_kind: FileScope
    target: str
    member_source_ids: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scope_kind not in FILE_SCOPES:
            raise ValidationError(
                f"scope_kind invalido: {self.scope_kind!r}"
            )
        if not self.target:
            raise ValidationError("ScopeResolution.target no puede estar vacio")
        # member_source_ids no vacio: un scope sin miembros no es un scope.
        if not self.member_source_ids:
            raise ValidationError(
                f"ScopeResolution sin miembros (target={self.target!r})"
            )


@dataclass(frozen=True, slots=True)
class AggregatedSignatures:
    """Resultado de agregar FileSignatures de varios sources.

    Agregacion sin duplicacion por ``foco`` (clave natural de
    FileSignature). Cobertura global = suma de ``cobertura`` por
    signature preservada. Procedencia preservada por signature
    (la agregacion NO sintetiza procedencia comun).
    """

    scope: ScopeQuery
    signatures: tuple[FileSignature, ...]
    total_files: int
    cobertura_global: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def signatures_count(self) -> int:
        return len(self.signatures)


# --- Resolvers (funciones puras) -------------------------------------


def resolve_directory_scope(
    *,
    directory_path: str,
    member_paths: tuple[str, ...],
) -> ScopeResolution:
    """Resuelve un scope de tipo ``directory``.

    Args:
        directory_path: ruta canonica del directorio (target).
        member_paths: source_ids miembros declarados por el caller.

    Returns:
        ScopeResolution con la membresia declarada.

    Notes:
        El resolver NO infiere la membresia por prefijo: el caller
        es quien declara quien pertenece al directorio. Esto permite
        que un mismo source_id pertenezca a varios scopes y evita
        ambiguedades cuando hay archivos generados o tests embebidos.
    """
    if not directory_path:
        raise ValidationError("directory_path no puede estar vacio")
    if not member_paths:
        raise ValidationError(
            f"directorio {directory_path!r} sin miembros declarados"
        )
    return ScopeResolution(
        scope_kind="directory",
        target=directory_path,
        member_source_ids=member_paths,
        metadata={"resolver": "explicit_listing"},
    )


def resolve_package_scope(
    *,
    package_name: str,
    declared_members: tuple[str, ...],
    prefix: str,
) -> ScopeResolution:
    """Resuelve un scope de tipo ``package``.

    Args:
        package_name: nombre logico del paquete (dot-separated).
        declared_members: source_ids que pertenecen al paquete
            segun su declaracion explicita.
        prefix: prefijo de ruta esperado (se usa SOLO para validar
            que todos los miembros pertenecen al directorio del
            paquete; NO para inferir la membresia).

    Returns:
        ScopeResolution con la membresia declarada.

    Notes:
        La membresia la decide el caller, no el prefijo de ruta.
        Esto respeta UAT-EVO-06: un paquete logico puede excluir
        archivos bajo su mismo directorio (p.ej. drafts) e incluir
        archivos en directorios no estandar.
    """
    validate_package_name(package_name)
    if not declared_members:
        raise ValidationError(
            f"paquete {package_name!r} sin miembros declarados"
        )
    # Verificacion defensiva: todos los miembros declarados
    # viven bajo el prefix (no es filtrado, es sanity check).
    for member in declared_members:
        if not member.startswith(prefix):
            raise ValidationError(
                f"miembro {member!r} del paquete {package_name!r} "
                f"no vive bajo prefix={prefix!r}"
            )
    return ScopeResolution(
        scope_kind="package",
        target=package_name,
        member_source_ids=declared_members,
        metadata={"resolver": "explicit_membership", "prefix": prefix},
    )


def resolve_bounded_context_scope(
    *,
    context_name: str,
    member_source_ids: tuple[str, ...],
) -> ScopeResolution:
    """Resuelve un scope de tipo ``bounded_context``.

    Args:
        context_name: nombre del bounded context (kebab-case).
        member_source_ids: source_ids miembros (pueden cruzar
            multiples paquetes, NO se impone prefix).

    Returns:
        ScopeResolution con la membresia declarada.
    """
    validate_bounded_context_name(context_name)
    if not member_source_ids:
        raise ValidationError(
            f"bounded_context {context_name!r} sin miembros declarados"
        )
    return ScopeResolution(
        scope_kind="bounded_context",
        target=context_name,
        member_source_ids=member_source_ids,
        metadata={"resolver": "explicit_membership"},
    )


# --- Aggregator (funcion pura) ---------------------------------------


def aggregate_signatures(
    *,
    signatures_per_source: dict[str, tuple[FileSignature, ...]],
    scope: ScopeQuery,
) -> AggregatedSignatures:
    """Agrega FileSignatures de varios sources en un solo resultado.

    Args:
        signatures_per_source: dict source_id -> tupla de
            FileSignatures. La agregacion deduplica por ``foco``
            (primera ocurrencia gana).
        scope: la consulta que produjo esta agregacion.

    Returns:
        AggregatedSignatures con ``signatures`` deduplicadas,
        ``cobertura_global`` (suma de cobertura), ``total_files``
        (numero de sources unicos representados).

    Notes:
        Funcion pura: NO toca Storage, Adapter ni reloj
        (regla AGENTS §1.1/§1.3).
    """
    if not signatures_per_source:
        # Sin sources -> agregacion vacia con cobertura 0.
        return AggregatedSignatures(
            scope=scope,
            signatures=(),
            total_files=0,
            cobertura_global=0,
        )

    seen_focos: set[str] = set()
    merged: list[FileSignature] = []
    total_cobertura = 0
    files_with_sigs: set[str] = set()

    for source_id, sigs in signatures_per_source.items():
        if sigs:
            files_with_sigs.add(source_id)
        for s in sigs:
            if s.foco in seen_focos:
                continue
            seen_focos.add(s.foco)
            merged.append(s)
            total_cobertura += s.cobertura

    return AggregatedSignatures(
        scope=scope,
        signatures=tuple(merged),
        total_files=len(files_with_sigs),
        cobertura_global=total_cobertura,
        metadata={
            "raw_source_count": len(signatures_per_source),
            "files_with_sigs": len(files_with_sigs),
        },
    )
