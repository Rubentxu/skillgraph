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
from pathlib import Path
from typing import Any, Literal

from skillgraph.knowledge.graph import Source, SourceID
from skillgraph.knowledge.graph import source_id as make_source_id
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


def analyze_skill(root: Path) -> SkillImportReport:
    """Pipeline completo: IMPORT -> ANALYZE -> STRUCTURE -> VALIDATE -> REGISTER.

    `root` es un directorio o archivo que contiene la skill original.
    El material NO se ejecuta. Se conserva el source y se genera un
    informe de estructuracion.
    """
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"skill path no existe: {root}")

    # ANALYZE: hash del contenido total (estable, orden alfabetico).
    if root.is_file():
        content_hash = _hash_bytes(root.read_bytes())
        original_path = str(root)
        files_iter = [root]
    else:
        content_hash = _hash_dir(root)
        original_path = str(root)
        files_iter = sorted(p for p in root.rglob("*") if p.is_file())

    files_total = len(list(files_iter))

    # STRUCTURE: clasificar cada archivo.
    structured: list[StructuredFile] = []
    ambiguous: list[AmbiguousEntry] = []
    scripts: list[str] = []
    capabilities: list[str] = []

    for f in files_iter:
        rel = f.relative_to(root).as_posix()
        size = f.stat().st_size
        fhash = _hash_bytes(f.read_bytes())
        kind = _classify(f)

        if kind == "python_script":
            # Scripts: REGISTRADOS pero NUNCA EJECUTADOS.
            scripts.append(rel)
            ambiguous.append(
                AmbiguousEntry(
                    path=rel,
                    reason=(
                        "Script Python detectado. NO se ejecuta (criterio UAT-14/"
                        "ADR-0009). Conservado como material original; su "
                        "comportamiento permanece encapsulado hasta que un "
                        "Adapter real lo evalue."
                    ),
                    ambiguity="ignored",
                )
            )
            continue

        if kind == "binary":
            ambiguous.append(
                AmbiguousEntry(
                    path=rel,
                    reason="Binario no textual. Sin capacidad de inspeccionar contenido.",
                    ambiguity="unparsed",
                )
            )
            continue

        if kind == "unknown":
            ambiguous.append(
                AmbiguousEntry(
                    path=rel,
                    reason=f"Extension desconocida ({f.suffix!r}). Sin heuristica aplicable.",
                    ambiguity="unparsed",
                )
            )
            continue

        structured.append(StructuredFile(path=rel, kind=kind, size_bytes=size, content_hash=fhash))

        if kind == "markdown_doc":
            text = _read_text_safely(f)
            if text is not None:
                capabilities.extend(_extract_capabilities_from_markdown(text))

    # VALIDATE: no hay capacidades 'verificadas' (no tenemos Adapter real).
    # Los headers extraidos son SENALES, no decisiones.
    nota = (
        "Las capacidades extraidas son señales heurísticas (headers Markdown), "
        "NO decisiones verificadas. La skill permanece en estado encapsulado "
        "hasta que un Adapter real evalúe su comportamiento."
    )

    sid = make_source_id(f"skill:{original_path}")

    return SkillImportReport(
        source_id=sid,
        original_path=original_path,
        content_hash=content_hash,
        imported_at=now_iso(),
        files_total=files_total,
        files_structured=tuple(structured),
        entries_ambiguous=tuple(ambiguous),
        scripts_detected=tuple(scripts),
        capabilities_extracted=tuple(capabilities),
        nota_honesta=nota,
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
