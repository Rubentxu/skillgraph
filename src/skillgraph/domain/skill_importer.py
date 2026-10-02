"""Asimilacion de skills externas: importa sin ejecutar, conserva fuente, informa.

Doc externo:
  external/blueprint-v1/adr/ADR-0009-asimilacion-progresiva.md
  external/blueprint-v1/10-cli-y-asimilacion.md
  external/blueprint-v1/plan/UAT.md UAT-11

Criterio legal UAT-11: 'Dada una skill convencional, cuando se importa,
entonces se conserva la fuente original y se genera un informe de
estructuracion. Las partes ambiguas deben permanecer senaladas; no se
presentan como decisiones verificadas.'

Flujo: IMPORT -> ANALYZE -> STRUCTURE -> VALIDATE -> REGISTER.

Reglas duras (no negociables):
- NUNCA ejecuta codigo del material importado (UAT-14 cubre esto
  para el path de import, pero aqui es el camino principal).
- Conserva el material original: registra un `Source` con
  content_hash (sha256 de bytes) + locator (path).
- Genera un informe de estructuracion: que pudo clasificar, que
  quedo como ambiguo, que capacidades se detectaron (texto,
  scripts ignorados, etc.).
- Partes ambiguas permanecen marcadas como `unparsed` en el informe.
  NO se presentan como decisiones verificadas.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass, field
from functools import reduce
from pathlib import Path
from typing import Any, Literal

from skillgraph.knowledge.graph import Source, SourceID, source_id as make_source_id
from skillgraph.runtime.engine import now_iso

Ambiguity = Literal["unparsed", "ignored", "needs_review"]


@dataclass(frozen=True, slots=True)
class StructuredFile:
    """Un archivo del paquete que SI pudimos clasificar."""

    path: str
    kind: str  # 'markdown_doc', 'python_script', 'json_config', 'plain_text', 'unknown'
    size_bytes: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class AmbiguousEntry:
    """Una parte del paquete que NO pudimos clasificar con certeza.

    El criterio legal exige que estas partes permanezcan senaladas,
    NO como decisiones verificadas.
    """

    path: str
    reason: str
    ambiguity: Ambiguity


@dataclass(frozen=True, slots=True)
class SkillImportReport:
    """Informe de fidelidad de la importacion (UAT-11)."""

    source_id: SourceID
    original_path: str
    content_hash: str
    imported_at: str  # ISO-8601 UTC
    files_total: int
    files_structured: tuple[StructuredFile, ...]
    entries_ambiguous: tuple[AmbiguousEntry, ...]
    scripts_detected: tuple[str, ...]  # paths de .py que NO se ejecutaron
    capabilities_extracted: tuple[str, ...]  # heuristica: headers markdown h2/h3
    nota_honesta: str = field(default_factory=str)

    def to_dict(self) -> dict[str, Any]:
        """Serializacion estable para CLI/JSON."""
        return {
            "source_id": self.source_id,
            "original_path": self.original_path,
            "content_hash": self.content_hash,
            "imported_at": self.imported_at,
            "files_total": self.files_total,
            "files_structured": [
                {
                    "path": sf.path,
                    "kind": sf.kind,
                    "size_bytes": sf.size_bytes,
                    "content_hash": sf.content_hash,
                }
                for sf in self.files_structured
            ],
            "entries_ambiguous": [
                {
                    "path": ae.path,
                    "reason": ae.reason,
                    "ambiguity": ae.ambiguity,
                }
                for ae in self.entries_ambiguous
            ],
            "scripts_detected": list(self.scripts_detected),
            "capabilities_extracted": list(self.capabilities_extracted),
            "nota_honesta": self.nota_honesta,
        }


_PY_SCRIPT_SUFFIXES = {".py", ".pyi"}
_TEXT_SUFFIXES = {".md", ".txt", ".rst"}
_JSON_SUFFIXES = {".json"}
_YAML_SUFFIXES = {".yaml", ".yml"}
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def _classify(path: Path) -> str:
    """Clasifica un archivo por extension/MIME. NO ejecuta nada."""
    suffix = path.suffix.lower()
    if suffix in _PY_SCRIPT_SUFFIXES:
        return "python_script"
    if suffix in _TEXT_SUFFIXES:
        return "markdown_doc" if suffix == ".md" else "plain_text"
    if suffix in _JSON_SUFFIXES:
        return "json_config"
    if suffix in _YAML_SUFFIXES:
        return "yaml_config"
    mime, _ = mimetypes.guess_type(str(path))
    if mime is not None:
        if mime.startswith("text/"):
            return "plain_text"
        return "binary"
    return "unknown"


def _hash_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_dir(root: Path) -> str:
    """Hash estable de un directorio: orden alfabetico, separador NUL."""
    files = sorted(p for p in root.rglob("*") if p.is_file())
    h = hashlib.sha256()
    for f in files:
        rel = f.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(f.read_bytes())
        h.update(b"\x00")
    return f"sha256:{h.hexdigest()}"


def _read_text_safely(path: Path) -> str | None:
    """Lee texto. Devuelve None si falla decode (binario, etc.)."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _extract_capabilities_from_markdown(text: str) -> tuple[str, ...]:
    """Heuristica honesta: NO inventa capacidades; solo lee headers h2/h3.

    Criterio del blueprint: 'Las partes ambiguas deben permanecer
    senaladas; no se presentan como decisiones verificadas.'
    Por eso devolvemos los headers LITERALES sin reinterpretar.
    """
    h2 = _H2_RE.findall(text)
    h3 = _H3_RE.findall(text)
    return tuple(f"{h.strip()}" for h in (h2 + h3) if h.strip())


@dataclass(frozen=True, slots=True)
class _ImportSource:
    """Raiz de import resuelta: que hash tiene y que ficheros hay que escanear.

    Publico a proposito solo dentro del modulo: es el resultado intermedio
    de `_resolve_source`, no parte del contrato de importacion.
    """

    root: Path
    original_path: str
    content_hash: str
    files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class _FileVerdict:
    """Veredicto de UN archivo: clasificado, ambiguo, script ignorado.

    Invariante: exactamente uno de `structured`/`ambiguous` viene
    informado. `script` se informa ADEMAS en el caso `python_script`,
    donde acompaña a la ambiguedad `ignored` (el script se conserva como
    material original y se senala; por eso son dos datos, no uno). La
    sostiene `_classify_file`, que siempre devuelve una de las ramas;
    `_merge` la traduce a los acumuladores del informe.
    """

    structured: StructuredFile | None = None
    ambiguous: AmbiguousEntry | None = None
    script: str | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ScanResult:
    """Acumulador inmutable del escaneo de una raiz de import.

    Es un acumulador, pero NO mutable: `_merge` devuelve siempre uno
    nuevo, de modo que el plegado de `analyze_skill` sigue siendo puro.
    """

    structured: tuple[StructuredFile, ...] = ()
    ambiguous: tuple[AmbiguousEntry, ...] = ()
    scripts: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()


# VALIDATE: no hay capacidades 'verificadas' (no tenemos Adapter real).
# Los headers extraidos son SENALES, no decisiones.
_NOTA_HONESTA = (
    "Las capacidades extraidas son señales heurísticas (headers Markdown), "
    "NO decisiones verificadas. La skill permanece en estado encapsulado "
    "hasta que un Adapter real evalúe su comportamiento."
)


def _resolve_source(root: Path) -> _ImportSource:
    """Resuelve la raiz de import: fichero unico o directorio.

    El hash del contenido total es estable (orden alfabetico para
    directorios). El mensaje de error nombra la raiz YA resuelta, que es
    lo que el llamador paso; se conserva por compatibilidad con UAT-11.
    """
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"skill path no existe: {root}")

    # ANALYZE: hash del contenido total (estable, orden alfabetico).
    if root.is_file():
        return _ImportSource(
            root=root,
            original_path=str(root),
            content_hash=_hash_bytes(root.read_bytes()),
            files=(root,),
        )
    return _ImportSource(
        root=root,
        original_path=str(root),
        content_hash=_hash_dir(root),
        files=tuple(sorted(p for p in root.rglob("*") if p.is_file())),
    )


def _classify_file(root: Path, f: Path) -> _FileVerdict:
    """Clasifica UN archivo del paquete. NO ejecuta nada (UAT-14/ADR-0009)."""
    rel = f.relative_to(root).as_posix()
    size = f.stat().st_size
    fhash = _hash_bytes(f.read_bytes())
    kind = _classify(f)

    if kind == "python_script":
        # Scripts: REGISTRADOS pero NUNCA EJECUTADOS.
        return _FileVerdict(
            script=rel,
            ambiguous=AmbiguousEntry(
                path=rel,
                reason=(
                    "Script Python detectado. NO se ejecuta (criterio UAT-14/"
                    "ADR-0009). Conservado como material original; su "
                    "comportamiento permanece encapsulado hasta que un "
                    "Adapter real lo evalue."
                ),
                ambiguity="ignored",
            ),
        )

    if kind == "binary":
        return _FileVerdict(
            ambiguous=AmbiguousEntry(
                path=rel,
                reason="Binario no textual. Sin capacidad de inspeccionar contenido.",
                ambiguity="unparsed",
            )
        )

    if kind == "unknown":
        return _FileVerdict(
            ambiguous=AmbiguousEntry(
                path=rel,
                reason=f"Extension desconocida ({f.suffix!r}). Sin heuristica aplicable.",
                ambiguity="unparsed",
            )
        )

    capabilities: tuple[str, ...] = ()
    if kind == "markdown_doc":
        text = _read_text_safely(f)
        if text is not None:
            capabilities = _extract_capabilities_from_markdown(text)

    return _FileVerdict(
        structured=StructuredFile(path=rel, kind=kind, size_bytes=size, content_hash=fhash),
        capabilities=capabilities,
    )


def _merge(result: _ScanResult, verdict: _FileVerdict) -> _ScanResult:
    """Plegado puro: acumula un veredicto y devuelve un `_ScanResult` NUEVO."""
    return _ScanResult(
        structured=result.structured
        if verdict.structured is None
        else (*result.structured, verdict.structured),
        ambiguous=result.ambiguous
        if verdict.ambiguous is None
        else (*result.ambiguous, verdict.ambiguous),
        scripts=result.scripts if verdict.script is None else (*result.scripts, verdict.script),
        capabilities=(*result.capabilities, *verdict.capabilities),
    )


def analyze_skill(root: Path) -> SkillImportReport:
    """Pipeline completo: IMPORT -> ANALYZE -> STRUCTURE -> VALIDATE -> REGISTER.

    `root` es un directorio o archivo que contiene la skill original.
    El material NO se ejecuta. Se conserva el source y se genera un
    informe de estructuracion.

    Orquestador de una pasada: resolver la raiz, plegar `_classify_file`
    con `_merge` y publicar el informe. El detalle de por que un kind es
    ambiguo vive en `_classify_file`, no aqui.
    """
    source = _resolve_source(root)
    result = reduce(
        lambda acc, f: _merge(acc, _classify_file(source.root, f)),
        source.files,
        _ScanResult(),
    )

    return SkillImportReport(
        source_id=make_source_id(f"skill:{source.original_path}"),
        original_path=source.original_path,
        content_hash=source.content_hash,
        imported_at=now_iso(),
        files_total=len(source.files),
        files_structured=result.structured,
        entries_ambiguous=result.ambiguous,
        scripts_detected=result.scripts,
        capabilities_extracted=result.capabilities,
        nota_honesta=_NOTA_HONESTA,
    )


def register_imported_skill(
    *,
    storage: Any,
    tenant_id: str,
    project_id: str,
    report: SkillImportReport,
    locator_extra: dict[str, Any] | None = None,
) -> str:
    """Registra el Source en storage (H3) sin ejecutar el material.

    Devuelve el source_id registrado.
    """
    locator: dict[str, Any] = {"path": report.original_path, "kind": "skill_dir"}
    if locator_extra:
        locator.update(locator_extra)

    src = Source(
        source_id=report.source_id,
        kind="skill_pack",
        content_hash=report.content_hash,
        locator=locator,
        git_commit_sha=None,
        git_tree_sha=None,
        working_tree_status=None,
        checked_at=report.imported_at,
        freshness="fresh",
    )
    storage.register_source(source=src, tenant_id=tenant_id, project_id=project_id)
    return src.source_id


__all__ = [
    "Ambiguity",
    "AmbiguousEntry",
    "SkillImportReport",
    "StructuredFile",
    "analyze_skill",
    "register_imported_skill",
]
