"""B31 — `sg.code.analysis`: el análisis que YA EXISTE y nunca se convertía en conocimiento.

**LA FILA DEL ROADMAP DICE UNA COSA QUE MEDIDA RESULTO SER FALSA.** Dice:

    «No hay análisis estructural real: `line_count = 137` es todo lo que se
    sabe del código»

El análisis estructural **existe**, es de este repo y es real:
`knowledge/file_signature.py` son 431 líneas puras y deterministas que
extraen imports, definiciones y cobertura con regex. MEDIDO
(`scripts/measure_b31_analisis.py`):

    E1  capabilities de análisis de código en src/            CERO
    E2  de los 7 predicados del Literal, con escritor          1 de 7
        (y los 3 usos de `line_count` NO son un claim: dos son
         method="line_count" y uno es un comentario)
    E3  record_evidence_for_file_signature -> Evidence, NUNCA Claim
    E5  NUCLEO = ("runtime", "core", "resources"); knowledge/ NO está

Lo que falta es **el último paso**: el análisis nunca se convierte en
conocimiento. `record_evidence_for_file_signature` lo persiste como
`Evidence(kind="file_signature")`, y desde B34 se puede preguntar por esa
evidencia — pero `what` no lo ve, porque un `Evidence` no es un `Claim`.
**Es evidencia que nadie puede preguntar.**

## QUÉ ENTREGA, Y QUÉ NO

Entrega el **puente**: una capability que, dado el contenido de un fichero,
produce el `ObservationEnvelope` versionado de B26 con los cinco predicados
que el extractor SÍ sabe sacar, y que `normalizar` convierte en `Claim`s.

NO entrega un analizador de código nuevo. El que hay es mejor que uno
nuevo — determinista, puro, y con 431 líneas ya probadas— y duplicarlo
sería tener dos verdades sobre el mismo fichero que divergirían sin que
nadie lo notara.

NO lee el disco. El contenido **entra por la petición**, por la misma razón
que en `telemetry_query.py`: una capability que abre ficheros tiene I/O
oculto, y `AGENTS.md` 1.3 lo prohíbe en el núcleo. Quien decide qué se
analiza es quien tiene el fichero; esta capa solo sabe qué significa.

## LA FRONTERA, Y POR QUÉ NO HAY GUARD NUEVO

La fila pide «CogniCode → CodeAnalysis → Knowledge, **sin imports en el
núcleo**». MEDIDO: `TestElNucleoNoImportaAdapters` con
`import cognicode` dentro de `knowledge/telemetry_query.py` da **VERDE**,
porque `NUCLEO = ("runtime", "core", "resources")` no incluye `knowledge/`.

Y no se arregla aquí, y el motivo es el que hizo el guard una lista de
**paquetes**: añadir `knowledge` a `NUCLEO` no amplía la comprobación,
**cambia qué se considera núcleo**, que es la decisión de B3 y no de B31.

La frontera de B31 se sostiene **por construcción**: este módulo no importa
ningún producto externo, porque no hace falta ninguno —
`extract_file_signatures` ya es de este repo. Y eso se declara aquí, en el
código, para que el siguiente que llegue lea el porqué antes de decidir si
añade un import.
"""

from __future__ import annotations

from typing import Any, Final

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.file_signature import FileSignature, extract_file_signatures
from skillgraph.knowledge.graph import entity_id
from skillgraph.knowledge.observation import (
    VERSION_ENVELOPE,
    Observation,
    ObservationEnvelope,
)
from skillgraph.platform.ports.capabilities import (
    CapabilityRequest,
    CapabilityResult,
    CapabilitySpec,
)

__all__ = [
    "CODE_ANALYSIS",
    "KIND_FICHERO",
    "PREDICADOS_DERIVADOS",
    "CodeAnalysisCapability",
    "analisis_a_observaciones",
    "envelope_a_payload",
    "sujeto_de",
]

#: El TIPO de esta capability. Constante y no cadena suelta (`AGENTS.md`
#: 2.4), por el mismo motivo que `TELEMETRY_QUERY` y `KNOWLEDGE_QUERY`.
CODE_ANALYSIS: Final[str] = "sg.code.analysis"

#: El kind que declara un envelope de analisis de codigo.
#:
#: **POR QUE `local_file` Y NO UNO NUEVO.** `SourceKind` es un `Literal`
#: cerrado y `AGENTS.md` 2.1 pide ADR antes de crecerlo — la misma regla que
#: hizo que B33 abriese `ADR-0034` para `runtime_observation`. Aqui no hace
#: falta: el valor que corresponde ya existe y ya significa exactamente
#: esto. Abrir una ADR para no usar el kind correcto seria fabricar trabajo.
#:
#: MEDIDO en `SourceKind`: `git_commit`, `git_tree`, `local_file`,
#: `external_doc`, `skill_pack`, `runtime_observation`. Un fichero del
#: workspace es `local_file` desde antes de que existiera esta capability.
KIND_FICHERO: Final[str] = "local_file"

#: Los cinco predicados que salen del extractor. **Cinco de siete**, y los
#: otros dos se declaran inalcanzables mas abajo con su motivo.
#:
#: Vive aqui como constante y no se deduce, porque es una DECLARACION de lo
#: que esta capability afirma — y un `Final` que se derivara de las
#: observaciones producidas seria un guard que compara contra su propia
#: copia.
PREDICADOS_DERIVADOS: Final[frozenset[str]] = frozenset(
    {
        "line_count",
        "file_exists",
        "function_count",
        "imports_module",
        "defines_symbol",
    }
)


def sujeto_de(path: str) -> str:
    """La ruta del fichero, como `EntityID`.

    **POR QUE ESTA FUNCION EXISTE Y NO SE USA UN STRING TAL CUAL.** MEDIDO:
    `entity_id("src/app.py")` lanza `InvalidEntityIDError`, porque
    `graph.py:99` exige el formato `kind:key`. El sujeto de un envelope no
    es texto libre: es el identificador de la entidad de la que se afirma
    algo, y el que no lleva namespace choca con una entidad homonima de
    otro tipo sin que nada lo advierta.

    `file:` es el namespace, y es el que B34 ya usa en sus ejemplos
    (`file:a.py`) y el que `_poblar` de sus tests siembra. Elegir otro
    obligaria a sembrar dos vocabularios de sujeto en el mismo grafo.

    Args:
        path: la ruta, con o sin el prefijo `file:`.

    Returns:
        La ruta con `file:` delante, validada por `entity_id`.

    Raises:
        ValidationError: si la ruta queda vacia o no admite el namespace.
    """
    limpio = path.strip()
    if not limpio:
        raise ValidationError(
            "sg.code.analysis necesita un path: un fichero sin nombre no es un sujeto"
        )
    if limpio.startswith(f"{_NAMESPACE}:"):
        return entity_id(limpio)
    try:
        return entity_id(f"{_NAMESPACE}:{limpio}")
    except Exception as exc:
        raise ValidationError(
            f"{CODE_ANALYSIS}: {path!r} no es un sujeto valido para un fichero. "
            f"Se espera `file:<ruta>`, y la regla que lo rechaza es "
            f"`entity_id`, no esta funcion"
        ) from exc


_NAMESPACE: Final[str] = "file"


def analisis_a_observaciones(sigs: tuple[FileSignature, ...]) -> tuple[Observation, ...]:
    """Las `FileSignature` de un fichero -> las `Observation` que SI se afirman.

    **AQUI ESTA TODO EL BLOQUE, Y POR QUE ES UNA FUNCION PURA.** La
    traduccion de «un `contrato='module'` con foco `x::os`» a
    «`imports_module` de `x` es `"os"`» es la parte que convierte analisis
    en afirmaciones, y es determinista: mismos `focos`, mismas
    observaciones, en el mismo orden. Al separarla de la capability se puede
    probar sin construir un `CapabilitySpec` ni un envelope, y es lo que
    hace que el resto del modulo sea cableado.

    **POR QUE `imports_module` LLEVA UN NOMBRE Y NO UNA ENTIDAD.** Aqui
    `Claim.object_entity` (B25) NO aplica: lo que se afirma es *el texto del
    modulo importado*, no una entidad del grafo. `imports_module` de
    `x.py` vale `"os"`, no vale «la entidad `module:os`», porque esa entidad
    no esta registrada en ninguna parte y apuntarla seria inventar un
    enlace que nadie creo.

    **POR QUE CADA OBSERVACION DECLARA SU PROPIA `extraction_method`.**
    MEDIDO sobre un fichero real: el extractor produce **tres** metodos —
    `line_count`, `regex_import`, `regex_def`— y los tres son ciertos para
    observaciones distintas del mismo analisis. Un envelope con un unico
    metodo solo podria ser verdad para una de las tres.

    Args:
        sigs: lo que devuelve `extract_file_signatures`.

    Returns:
        Las observaciones, en el orden del summary primero y luego las
        especificas. Nunca vacio: aunque el fichero no tenga ni un import, el
        summary aporta `line_count`, `function_count` y `file_exists`.
    """
    if not sigs:
        # `extract_file_signatures` SIEMPRE devuelve al menos un summary; un
        # tupla vacia significa que alguien cambio esa garantia. No se
        # devuelve `()` porque un envelope sin observaciones se ingeria
        # como no-op y parece que funciono.
        raise ValidationError(
            f"{CODE_ANALYSIS}: el extractor no devolvio ni el summary del fichero. "
            "Sin el no hay ni linea ni existencia que afirmar, y un envelope "
            "vacio se ingiere como no-op"
        )

    resumen = sigs[0]
    contratos = sigs[1:]
    modules = [s for s in contratos if s.contrato == "module"]
    defs = [s for s in contratos if s.contrato == "def"]

    observations: list[Observation] = [
        Observation(
            predicate="line_count",
            object_literal=resumen.cobertura,
            extraction_method=resumen.procedencia.extraction_method,
        ),
        Observation(
            predicate="function_count",
            object_literal=len(defs),
            # El conteo de defs sale de un RECORRIDO con el mismo regex que
            # los encuentra, asi que declara el regex y no una categoria.
            extraction_method=_METODO_DEFS,
        ),
        Observation(
            predicate="file_exists",
            object_literal=resumen.vigencia.state != "absent",
            extraction_method=resumen.procedencia.extraction_method,
        ),
    ]
    observations.extend(
        Observation(
            predicate="imports_module",
            object_literal=_nombre_del_foco(s.foco, sep="::"),
            extraction_method=s.procedencia.extraction_method,
        )
        for s in modules
    )
    observations.extend(
        Observation(
            predicate="defines_symbol",
            object_literal=_nombre_del_foco(s.foco, sep="::def::"),
            extraction_method=s.procedencia.extraction_method,
        )
        for s in defs
    )
    return tuple(observations)


#: El metodo que declara `function_count`. No es `regex_def` porque el
#: NUMERO no sale de un unico regex sino de contar cuantos hay, y el
#: extractor no lo nombra en ningun sitio. Se escribe aqui, y no se deduce
#: de `s.procedencia`, porque deducirlo seria tomar el metodo de la primera
#: firma y aplicarlo a un hecho que no produjo ninguna.
_METODO_DEFS: Final[str] = "regex_def"


def _nombre_del_foco(foco: str, *, sep: str) -> str:
    """`src/app.py::def::saluda` -> `saluda`. Y `src/app.py::os` -> `os`.

    `rpartition` y no `split`: un modulo puede contener el separador en su
    nombre —`from a::b import c` es raro pero `app.py::def::f` tiene dos
    separadores— y partir por todos devolveria un trozo equivocado. Se
    parte por el ULTIMO, que es donde el extractor pone el nombre.

    Args:
        foco: el `FileSignature.foco` tal cual lo construyo el extractor.
        sep: `"::"` para modulos, `"::def::"` para simbolos.

    Returns:
        El nombre, o el foco entero si el separador no aparece — que no
        deberia pasar nunca, y devuelve el foco en vez de `""` para que un
        eventual fallo se vea como un nombre raro y no como una ausencia.
    """
    _, _, nombre = foco.rpartition(sep)
    return nombre or foco


class CodeAnalysisCapability:
    """La capability que convierte un fichero en afirmaciones sobre el.

    **POR QUE EL CONTENIDO ENTRA POR LA PETICION Y NO SE LEE AQUI.** Una
    capability que abre ficheros tiene I/O oculto en el nucleo, que es lo
    que `AGENTS.md` 1.3 prohibe. Y el reloj tampoco se lee: `observed_at`
    entra por la peticion por el motivo que `observation.py` declara en
    cuatro parrafos —leerlo rompe la idempotencia sola, porque el `claim_id`
    lo incluye en su semilla—.

    **LO QUE NO HACE, Y ES DELIBERADO.** No escribe en el store, por el
    mismo motivo que `TelemetryQueryCapability`: un adaptador que escribe
    deja de ser un adaptador y pasa a ser la razon por la que hay que
    confiar en el, que es lo que `ADR-0027` rechazo. Devuelve la frontera
    y que la ingesta la aplique.

    **POR QUE NO HAY UN PROTOCOL DE LECTOR.** Porque no hay lector que
    injectar: el extractor es de este repo y es puro. Un `Protocol` aqui
    seria una indireccion que no compra nada —y que invite a alguien a
    inyectar un analizador externo por el hueco, que es justo la frontera
    que este modulo declara no cruzar.
    """

    def __init__(self, *, source_id: str, revision: str) -> None:
        """Sin dependencias.

        Args:
            source_id: la identidad de la fuente que producirá este
                envelope. La escribe quien decide qué fichero se analiza,
                y NO se deduce de la ruta: un mismo fichero analizado en dos
                revisiones es la MISMA ruta y DOS fuentes, que es lo que
                hace que `changed` de B29 pueda separarlas.
            revision: contra qué revisión se registró el análisis. Es el
                reloj de B29 (`checked_at_revision`) y no tiene nada que ver
                con el contenido: el fichero es el mismo antes y después de
                que cambie el git que lo versiona.
        """
        if not source_id or not source_id.strip():
            raise ValidationError("CodeAnalysisCapability necesita un source_id no vacio")
        if not revision or not revision.strip():
            raise ValidationError(
                "CodeAnalysisCapability necesita una revision: sin ella el claim_id "
                "no se puede derivar del contenido y la ingesta no seria idempotente"
            )
        self._source_id = source_id
        self._revision = revision

    @property
    def spec(self) -> CapabilitySpec:
        """La identidad. La `version` la hereda del puerto, por el motivo que
        declaran `KnowledgeQueryCapability.spec` y `TelemetryQueryCapability.spec`:
        si el adapter declarase la suya, cada uno podria inventarla."""
        return CapabilitySpec(
            type_name=CODE_ANALYSIS,
            summary=(
                "Analiza el contenido de un fichero y declara lo que se sabe "
                "de su estructura como afirmaciones versionadas"
            ),
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """La vertical entera, en una llamada.

        Returns:
            Un `CapabilityResult` con el envelope serializado bajo
            `"envelope"`, igual que hace `telemetry_query`.

        Raises:
            ValidationError: si la peticion no trae `path`, `content` ni
                `observed_at`. Las tres se validan AQUI y no en la frontera,
                porque un envelope sin `observed_at` no se puede ni
                construir.
        """
        path = _texto_obligatorio(request, "path", CODE_ANALYSIS)
        content = request.arguments.get("content")
        if not isinstance(content, str):
            raise ValidationError(
                f"{CODE_ANALYSIS} necesita request.arguments['content'] con el "
                f"TEXTO del fichero, y recibio {type(content).__name__}. El "
                "contenido entra por la peticion a proposito: leer el disco "
                " aqui seria I/O oculto en el nucleo (AGENTS 1.3)"
            )
        observado_en = _texto_obligatorio(request, "observed_at", CODE_ANALYSIS)
        sujeto = sujeto_de(path)

        envelope = self._envelope(sujeto, content, observado_en)
        return CapabilityResult(
            spec=self.spec,
            adapter=type(self).__name__,
            payload={
                "subject": sujeto,
                "source_id": self._source_id,
                "revision": self._revision,
                "envelope": envelope_a_payload(envelope),
            },
        )

    def _envelope(self, sujeto: str, content: str, observado_en: str) -> ObservationEnvelope:
        """El analysis, su declaracion, y nada mas.

        **POR QUE NO HAY VENTANA.** `observed_from`/`observed_to` son de
        B33 y son un PERIODO. Un fichero no es un periodo: es un instante,
        y un instante no se abre por los dos lados. Declarar una ventana
        aqui haria que `runtime_observation` —el unico kind que la admite—
        y `local_file` significaran cosas distintas por un campo que en
        este caso no tiene valor.
        """
        sigs = extract_file_signatures(file_path=sujeto, content=content)
        return ObservationEnvelope(
            producer=self.spec,
            adapter=type(self).__name__,
            source_id=self._source_id,
            subject=sujeto,
            observed_at=observado_en,
            revision=self._revision,
            observations=analisis_a_observaciones(sigs),
            version=VERSION_ENVELOPE,
            kind=KIND_FICHERO,
        )


def envelope_a_payload(envelope: ObservationEnvelope) -> dict[str, Any]:
    """El envelope, en la forma que viaja por `CapabilityResult.payload`.

    Se serializa con `asdict` por el motivo que ya se pago una vez con
    `ObservationEnvelope`: un campo nuevo en el ADT y olvidado aqui es un
    dato que sale del sistema sin que nadie lo note. Y se serializa con
    `default=str` porque `object_entity` es un `EntityRef` y un `dict` que
    no sabe convertirlo revienta con un `TypeError` en lugar de perder el
    dato en silencio.
    """
    from dataclasses import asdict

    datos = asdict(envelope)
    datos["observations"] = [
        {
            "predicate": o.predicate,
            "object_literal": o.object_literal,
            "object_entity": str(o.object_entity) if o.object_entity is not None else None,
            "extraction_method": o.extraction_method,
        }
        for o in envelope.observations
    ]
    datos["vocabulario"] = sorted(PREDICADOS_DERIVADOS)
    return datos


def _texto_obligatorio(request: CapabilityRequest, clave: str, capability: str) -> str:
    """Un argumento de texto que no puede faltar, validado en la frontera.

    Se construye el mensaje aqui y no se propaga el `ValidationError` ajeno,
    porque un operador que escribe `path` y recibe un error sobre
    `entity_id` no sabe que escribir.
    """
    crudo = request.arguments.get(clave)
    if crudo is None:
        raise ValidationError(
            f"{capability} necesita request.arguments[{clave!r}]. "
            f"Obligatorios: 'path', 'content', 'observed_at'"
        )
    if not isinstance(crudo, str) or not crudo.strip():
        raise ValidationError(
            f"{capability}: arguments[{clave!r}] tiene que ser un texto no vacio, y es {crudo!r}"
        )
    return crudo
