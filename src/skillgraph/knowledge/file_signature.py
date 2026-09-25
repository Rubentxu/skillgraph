"""FileSignature — H11 Conocimiento tipado reutilizable.

Destino (evolution-v2/plan/ROADMAP.md H11):
registrar FileSignatures con foco, contrato, cobertura, procedencia
y vigencia. Reutilizables entre procesos, con estados
vacio/ausente/parcial/complete y deteccion de stale.

Adaptado a la ADT existente:
- FileSignature es un **payload logico** que se persiste como
  ``Evidence`` (kind="file_signature") en Storage. NO introduce
  una tabla nueva ni una migracion: reusa la infraestructura de
  evidences que ya tiene tests, schema, indices y cobertura.
- ExtractionState es un Literal cerrado (regla AGENTS §2.1).
- El extractor (``extract_file_signatures``) es una funcion pura
  que NO toca Storage ni Adapter (regla AGENTS §1.1/§1.3).

Heuristicas implementadas (deterministas, sin red, sin reloj):
- ``import`` lineas -> signature con foco="module" y contrato=module.
- ``def name(`` lineas -> signature con foco="function" y contrato=def.
- lineas totales -> signature "summary" con foco="<file>" y cobertura=N.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# --- ADT cerrada (regla AGENTS §2.1) ---------------------------------

ExtractionState = Literal["empty", "absent", "partial", "complete", "stale"]

EXTRACTION_STATES: frozenset[str] = frozenset(
    {"empty", "absent", "partial", "complete", "stale"}
)


@dataclass(frozen=True, slots=True)
class SignatureProcedencia:
    """Como se obtuvo esta signature.

    ``extraction_method`` es la heuristica concreta
    (``regex_import`` | ``regex_def`` | ``line_count``). Coherente
    con el campo homonimo en ``Claim``.
    """

    extraction_method: str
    extractor_version: str

    def __post_init__(self) -> None:
        if not self.extraction_method:
            raise ValueError("extraction_method no puede estar vacio")
        if not self.extractor_version:
            raise ValueError("extractor_version no puede estar vacia")


@dataclass(frozen=True, slots=True)
class SignatureVigencia:
    """Estado temporal de la signature.

    ``fresh`` y ``stale`` son la pareja booleana principal
    (``fresh == not stale`` cuando state in {"complete", "partial"}).
    Para state in {"empty", "absent", "stale"}, ``fresh=False`` y
    ``stale=True`` para que el caller pueda filtrar con un solo flag.
    """

    state: ExtractionState
    fresh: bool
    stale: bool
    checked_at_revision: str = ""

    def __post_init__(self) -> None:
        if self.state not in EXTRACTION_STATES:
            raise ValueError(f"state invalido: {self.state!r}")
        # Coherencia fresh/stale por estado.
        # fresh=True solo para 'complete'; partial es fresh=False (algunas
        # heuristicas aplicables pero no todas; el caller debe revisar).
        expected_fresh = self.state == "complete"
        expected_stale = self.state in {"empty", "absent", "stale", "partial"}
        if self.fresh != expected_fresh:
            raise ValueError(
                f"fresh={self.fresh} inconsistente con state={self.state!r} "
                f"(esperaba fresh={expected_fresh})"
            )
        if self.stale != expected_stale:
            raise ValueError(
                f"stale={self.stale} inconsistente con state={self.state!r} "
                f"(esperaba stale={expected_stale})"
            )


@dataclass(frozen=True, slots=True)
class FileSignature:
    """Signature tipada de un fichero.

    Una FileSignature es un payload logico con:

    * ``foco``: que parte del fichero representa (modulo, funcion,
      archivo completo como summary).
    * ``contrato``: tipo de signature (module | def | file_summary).
    * ``cobertura``: cuanto abarca (numero de lineas o 0 para
      signatures puntuales).
    * ``procedencia``: como se obtuvo (heuristica + version).
    * ``vigencia``: estado temporal (empty/absent/partial/complete/stale).
    """

    foco: str
    contrato: str
    cobertura: int
    procedencia: SignatureProcedencia
    vigencia: SignatureVigencia
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.foco:
            raise ValueError("foco no puede estar vacio")
        if not self.contrato:
            raise ValueError("contrato no puede estar vacio")
        if self.cobertura < 0:
            raise ValueError(f"cobertura debe ser >= 0, recibio {self.cobertura}")

    def to_dict(self) -> dict[str, Any]:
        """Serializa a dict plano (JSON-friendly)."""
        return {
            "foco": self.foco,
            "contrato": self.contrato,
            "cobertura": self.cobertura,
            "procedencia": asdict(self.procedencia),
            "vigencia": asdict(self.vigencia),
            "metadata": dict(self.metadata),
        }


# --- Extractor determinista (puro, sin I/O) ---------------------------

_EXTRACTOR_VERSION = "skillgraph-rules/0.1.0"

_RE_IMPORT = re.compile(r"^\s*(?:from\s+(\S+)\s+)?import\s+(\S+)")
_RE_DEF = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def extract_file_signatures(
    *, file_path: str, content: str
) -> tuple[FileSignature, ...]:
    """Extrae FileSignatures deterministas de un fichero.

    Args:
        file_path: ruta del fichero (puede ser sentinela "<absent>"
            para indicar archivo ausente).
        content: contenido textual del fichero (vacio para empty).

    Returns:
        Tupla de FileSignatures. SIEMPRE devuelve al menos una
        signature "summary" con foco=file_path para que el caller
        pueda detectar estados terminales (empty/absent) y saber
        que se intento extraer.
    """
    # Caso 1: archivo ausente (sentinel).
    if file_path == "<absent>":
        return (
            FileSignature(
                foco=file_path,
                contrato="file_summary",
                cobertura=0,
                procedencia=SignatureProcedencia(
                    extraction_method="absent_sentinel",
                    extractor_version=_EXTRACTOR_VERSION,
                ),
                vigencia=SignatureVigencia(
                    state="absent",
                    fresh=False,
                    stale=True,
                ),
            ),
        )

    lines = content.splitlines()
    n_lines = len(lines)

    # Caso 2: archivo vacio.
    if n_lines == 0:
        return (
            FileSignature(
                foco=file_path,
                contrato="file_summary",
                cobertura=0,
                procedencia=SignatureProcedencia(
                    extraction_method="line_count",
                    extractor_version=_EXTRACTOR_VERSION,
                ),
                vigencia=SignatureVigencia(
                    state="empty",
                    fresh=False,
                    stale=True,
                ),
            ),
        )

    # Caso 3: extraer imports + defs.
    sigs: list[FileSignature] = []
    has_imports = False
    has_defs = False
    for line in lines:
        m_imp = _RE_IMPORT.match(line)
        if m_imp:
            has_imports = True
            module = m_imp.group(2) or m_imp.group(1) or "?"
            sigs.append(
                FileSignature(
                    foco=f"{file_path}::{module}",
                    contrato="module",
                    cobertura=1,
                    procedencia=SignatureProcedencia(
                        extraction_method="regex_import",
                        extractor_version=_EXTRACTOR_VERSION,
                    ),
                    vigencia=SignatureVigencia(state="complete", fresh=True, stale=False),
                )
            )
            continue
        m_def = _RE_DEF.match(line)
        if m_def:
            has_defs = True
            name = m_def.group(1)
            sigs.append(
                FileSignature(
                    foco=f"{file_path}::def::{name}",
                    contrato="def",
                    cobertura=1,
                    procedencia=SignatureProcedencia(
                        extraction_method="regex_def",
                        extractor_version=_EXTRACTOR_VERSION,
                    ),
                    vigencia=SignatureVigencia(state="complete", fresh=True, stale=False),
                )
            )

    # Summary final: estado depende de si hubo heuristicas aplicables.
    if has_imports or has_defs:
        summary_state: ExtractionState = "complete"
    else:
        summary_state = "partial"

    summary = FileSignature(
        foco=file_path,
        contrato="file_summary",
        cobertura=n_lines,
        procedencia=SignatureProcedencia(
            extraction_method="line_count",
            extractor_version=_EXTRACTOR_VERSION,
        ),
        vigencia=SignatureVigencia(
            state=summary_state,
            fresh=(summary_state == "complete"),
            stale=(summary_state != "complete"),
        ),
    )
    # Summary primero; signatures especificas despues.
    return (summary, *sigs)
