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

from skillgraph.core.errors import ParseError, ValidationError

# --- ADT cerrada (regla AGENTS §2.1) ---------------------------------

ExtractionState = Literal["empty", "absent", "partial", "complete", "stale"]

EXTRACTION_STATES: frozenset[str] = frozenset({"empty", "absent", "partial", "complete", "stale"})

# --- Validacion de forma (WI-90) ---------------------------------------
#
# `from_dict` es el inverso de `to_dict`, y un inverso sin validacion no
# compra nada: solo cambia donde revienta. Estos cinco helpers concentran
# la comprobacion para que el "que formas validas" viva en un sitio y cada
# `from_dict` se limite a declarar sus campos.


def _require_mapping(value: Any, owner: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ParseError(f"{owner}: se esperaba un dict, recibio {type(value).__name__}")
    return value


def _require_keys(data: dict[str, Any], required: tuple[str, ...], owner: type) -> None:
    """Faltan claves -> ParseError. Sobran -> ParseError tambien.

    Lo que no hace es ignorar la de mas. Un payload escrito por una version
    futura trae campos que esta no conoce, y perderlos en silencio deja al
    consumidor creyendo que tiene el dato completo.
    """
    faltantes = [k for k in required if k not in data]
    if faltantes:
        raise ParseError(f"{owner.__name__}: faltan claves {sorted(faltantes)}")
    sobrantes = sorted(set(data) - set(required) - {"metadata"})
    if sobrantes:
        raise ParseError(
            f"{owner.__name__}: claves desconocidas {sobrantes}. Puede ser un payload "
            "de una version posterior; no se ignoran en silencio."
        )


def _require_str(value: Any, name: str, owner: type) -> str:
    if not isinstance(value, str):
        raise ParseError(
            f"{owner.__name__}.{name}: se esperaba str, recibio {type(value).__name__}"
        )
    return value


def _require_int(value: Any, name: str, owner: type) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ParseError(
            f"{owner.__name__}.{name}: se esperaba int, recibio {type(value).__name__}"
        )
    return value


def _require_bool(value: Any, name: str, owner: type) -> bool:
    if not isinstance(value, bool):
        raise ParseError(
            f"{owner.__name__}.{name}: se esperaba bool, recibio {type(value).__name__}"
        )
    return value


def _require_optional_mapping(value: Any, name: str, owner: type) -> dict[str, Any]:
    if value is None:
        return {}
    return _require_mapping(value, f"{owner.__name__}.{name}")


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
            raise ValidationError("extraction_method no puede estar vacio")
        if not self.extractor_version:
            raise ValidationError("extractor_version no puede estar vacia")

    def to_dict(self) -> dict[str, Any]:
        return {
            "extraction_method": self.extraction_method,
            "extractor_version": self.extractor_version,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> SignatureProcedencia:
        """Inverso de `to_dict`. Ver `FileSignature.from_dict` (WI-90)."""
        data = _require_mapping(payload, cls.__name__)
        _require_keys(data, ("extraction_method", "extractor_version"), cls)
        return cls(
            extraction_method=_require_str(data["extraction_method"], "extraction_method", cls),
            extractor_version=_require_str(data["extractor_version"], "extractor_version", cls),
        )


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
            raise ValidationError(f"state invalido: {self.state!r}")
        # Coherencia fresh/stale por estado.
        # fresh=True solo para 'complete'; partial es fresh=False (algunas
        # heuristicas aplicables pero no todas; el caller debe revisar).
        expected_fresh = self.state == "complete"
        expected_stale = self.state in {"empty", "absent", "stale", "partial"}
        if self.fresh != expected_fresh:
            raise ValidationError(
                f"fresh={self.fresh} inconsistente con state={self.state!r} "
                f"(esperaba fresh={expected_fresh})"
            )
        if self.stale != expected_stale:
            raise ValidationError(
                f"stale={self.stale} inconsistente con state={self.state!r} "
                f"(esperaba stale={expected_stale})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "fresh": self.fresh,
            "stale": self.stale,
            "checked_at_revision": self.checked_at_revision,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> SignatureVigencia:
        """Inverso de `to_dict`. Ver `FileSignature.from_dict` (WI-90).

        `state` fuera de la ADT cerrada no se comprueba aqui: lo hace
        `__post_init__`, que lanza `ValidationError` en vez de `ParseError`.
        La distincion importa — la forma es valida y el valor no lo es — y
        duplicar la comprobacion aqui seria inventarse un segundo sitio que
        puede desincronizarse del primero.
        """
        data = _require_mapping(payload, cls.__name__)
        _require_keys(data, ("state", "fresh", "stale", "checked_at_revision"), cls)
        return cls(
            state=_require_str(data["state"], "state", cls),
            fresh=_require_bool(data["fresh"], "fresh", cls),
            stale=_require_bool(data["stale"], "stale", cls),
            checked_at_revision=_require_str(
                data["checked_at_revision"], "checked_at_revision", cls
            ),
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
            raise ValidationError("foco no puede estar vacio")
        if not self.contrato:
            raise ValidationError("contrato no puede estar vacio")
        if self.cobertura < 0:
            raise ValidationError(f"cobertura debe ser >= 0, recibio {self.cobertura}")

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

    @classmethod
    def from_dict(cls, payload: Any) -> FileSignature:
        """Inverso exacto de `to_dict` (WI-90).

        Antes este inverso vivia escrito a mano en
        `KnowledgeController.list_file_signatures_for_source`, con
        subindices crudos. Medido, eso dava tres fallos: una clave que
        faltaba reventaba con `KeyError`, un sub-dict incompleto con
        `TypeError`, y **un campo de mas se perdia en silencio**. El
        ultimo es el que mas duele: un consumidor creeria tener el dato
        completo. Y anadir un campo obligatorio a este dataclass rompia
        la lectura de lo ya persistido, no la escritura.

        Aqui la forma se valida una vez y el error es `ParseError`
        (`sg_parse`): el registro no se puede leer. El `ValidationError`
        que lanza `__post_init__` es otra cosa — la forma es correcta y
        los valores violan politica — y se deja propagar.

        Args:
            payload: dict tal y como lo emite `to_dict`.

        Returns:
            La `FileSignature` reconstruida.

        Raises:
            ParseError: si el payload no tiene la forma de esta clase.
        """
        data = _require_mapping(payload, cls.__name__)
        _require_keys(data, ("foco", "contrato", "cobertura", "procedencia", "vigencia"), cls)
        return cls(
            foco=_require_str(data["foco"], "foco", cls),
            contrato=_require_str(data["contrato"], "contrato", cls),
            cobertura=_require_int(data["cobertura"], "cobertura", cls),
            procedencia=SignatureProcedencia.from_dict(data["procedencia"]),
            vigencia=SignatureVigencia.from_dict(data["vigencia"]),
            metadata=_require_optional_mapping(data.get("metadata"), "metadata", cls),
        )


# --- Extractor determinista (puro, sin I/O) ---------------------------

_EXTRACTOR_VERSION = "skillgraph-rules/0.1.0"

_RE_IMPORT = re.compile(r"^\s*(?:from\s+(\S+)\s+)?import\s+(\S+)")
_RE_DEF = re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _procedencia(method: str) -> SignatureProcedencia:
    """Procedencia con la version del extractor ya puesta.

    La version es un dato del extractor, no de cada signature: escribirla
    en cada construccion son cinco oportunidades de divergir.
    """
    return SignatureProcedencia(
        extraction_method=method,
        extractor_version=_EXTRACTOR_VERSION,
    )


def _vigencia(state: ExtractionState) -> SignatureVigencia:
    """Deriva ``fresh``/``stale`` del estado. Fuente unica de la regla.

    ``SignatureVigencia.__post_init__`` **rechaza** la incoherencia entre
    el estado y el par, asi que escribir el par a mano en cada
    construccion no es estilo: es dejar cuatro bombas armed con un
    fichero valido. Aqui la inferencia es unica y no se puede errar.
    """
    return SignatureVigencia(
        state=state,
        fresh=(state == "complete"),
        stale=(state != "complete"),
    )


def _summary(
    foco: str,
    *,
    cobertura: int,
    method: str,
    state: ExtractionState,
) -> FileSignature:
    """Signature ``file_summary``: siempre la primera de la tupla."""
    return FileSignature(
        foco=foco,
        contrato="file_summary",
        cobertura=cobertura,
        procedencia=_procedencia(method),
        vigencia=_vigencia(state),
    )


def _module_signature(file_path: str, module: str) -> FileSignature:
    return FileSignature(
        foco=f"{file_path}::{module}",
        contrato="module",
        cobertura=1,
        procedencia=_procedencia("regex_import"),
        vigencia=_vigencia("complete"),
    )


def _def_signature(file_path: str, name: str) -> FileSignature:
    return FileSignature(
        foco=f"{file_path}::def::{name}",
        contrato="def",
        cobertura=1,
        procedencia=_procedencia("regex_def"),
        vigencia=_vigencia("complete"),
    )


def _scan_lines(file_path: str, lines: list[str]) -> tuple[tuple[FileSignature, ...], bool, bool]:
    """Aplica las heuristicas linea a linea.

    Devuelve ``(signatures, hay_imports, hay_defs)``. El ``continue``
    tras un import no es cosmetico: sin el, una linea ``import`` caeria
    tambien en la rama de ``def`` y generaria signatures duplicadas.
    """
    sigs: list[FileSignature] = []
    has_imports = False
    has_defs = False
    for line in lines:
        m_imp = _RE_IMPORT.match(line)
        if m_imp:
            has_imports = True
            # Grupo 2 primero: para `import os` es el modulo, y para
            # `from x import y` es el simbolo importado. Es el
            # comportamiento vigente y lo fija un test explicito.
            module = m_imp.group(2) or m_imp.group(1) or "?"
            sigs.append(_module_signature(file_path, module))
            continue
        m_def = _RE_DEF.match(line)
        if m_def:
            has_defs = True
            sigs.append(_def_signature(file_path, m_def.group(1)))
    return tuple(sigs), has_imports, has_defs


def extract_file_signatures(*, file_path: str, content: str) -> tuple[FileSignature, ...]:
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

    Puro: sin Storage, sin Adapter, sin reloj (AGENTS 1.1/1.3).
    """
    # Caso 1: archivo ausente (sentinel).
    if file_path == "<absent>":
        return (
            _summary(
                file_path,
                cobertura=0,
                method="absent_sentinel",
                state="absent",
            ),
        )

    lines = content.splitlines()
    n_lines = len(lines)

    # Caso 2: archivo vacio.
    if n_lines == 0:
        return (
            _summary(
                file_path,
                cobertura=0,
                method="line_count",
                state="empty",
            ),
        )

    # Caso 3: extraer imports + defs.
    sigs, has_imports, has_defs = _scan_lines(file_path, lines)

    # Summary final: `complete` si alguna heuristica fue aplicable,
    # `partial` si el fichero tiene lineas pero ninguna coincidio.
    summary_state: ExtractionState = "complete" if (has_imports or has_defs) else "partial"
    summary = _summary(
        file_path,
        cobertura=n_lines,
        method="line_count",
        state=summary_state,
    )
    # Summary primero; signatures especificas despues.
    return (summary, *sigs)
