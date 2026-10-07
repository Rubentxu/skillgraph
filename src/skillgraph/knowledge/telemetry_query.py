"""B33 — `telemetry.query.v1`: la vertical que produce lo que se VIO.

**POR QUE ESTE MODULO EXISTE Y NO ES E1 DE UNA SERIE DE CAPABILITIES.**
El gate que el roadmap escribe para B33 dice «un claim runtime que
contradicen un ADR abre conflicto; `actual_behavior` prefiere runtime e
`intended_architecture` prefiere la decisión aceptada». MEDIDO sobre un store
de verdad, ese gate **ya se cumplía antes de escribir una línea de B33**:

```
fuentes:  adr:0001  kind=external_doc        c-adr       "psycopg"  human-asserted
          runtime:ventana-1  kind=external_doc  c-runtime  "sqlite3"  observed
conflicts_for       -> 1 conflicto: [c-adr, c-runtime]
resolver actual_behavior    -> c-runtime
resolver intended_behavior  -> c-adr
```

Y es exactamente el ejemplo con el que **B28 certificó su propio bloque**:
su `_el_conflicto_del_bloque` se llama `c-runtime` contra `c-adr`. Un gate
que otro bloque ya certified se puede «cerrar» sin escribir nada, y eso no
es un gate: es una segunda lectura del mismo resolver.

Lo que faltaba era lo que se mide aquí, y es una sola cosa: **nadie
producía una afirmación de runtime**. El resolver estaba preparado desde
B28 y el lado de la vertical era un hueco con forma exacta:

```
E1 telemetry.query.v1       CERO en src/, fuera de prosa
E2 adapter Chronos/OTel     CERO; no hay adapters/ en ninguna parte
E3 ventana temporal         CERO: checked_at y observed_at son INSTANTES,
                            y la ventana de Claim es por REVISION (B29)
E4 runtime claims           la mecánica existe, la fuente salia external_doc
E5 perfil actual_behavior   YA EXISTE (B28)
```

Y para registrar una observación de runtime había que **mentir**: se
declaraba `kind="external_doc"`, que no es lo que es. Eso era una decisión
de B26 con un motivo escrito —`SourceKind` es un `Literal` cerrado y
`AGENTS.md` 2.1 pide ADR antes de crecerlo— y la ADR se abrió en este bloque
como `ADR-0034`.

**LO QUE ESTE MODULO ENTREGA Y LO QUE NO.** Entrega el **contrato**: una
capability que, dado un sujeto, una ventana y un instante, produce un
`ObservationEnvelope` que declara `kind="runtime_observation"` y el periodo
que cubrió, que `normalizar` (B26) convierte en una `Source` con ventana.

NO entrega un cliente de Chronos ni de OpenTelemetry, y no se finge que sí.
La razón es la misma que `KnowledgeQueryCapability` ya declara y por la que
este repo no reconstruye herramientas externas: **el adaptador que sabe es
el despliegue, y lo recibe**. Lo que este sistema sabe es qué forma tiene la
respuesta; quién la busca en Chronos es del despliegue. Por eso el lector
entra por un `Protocol` y no por un import.

Medido, no supuesto: `chronos`, `opentelemetry` y `otel` **no aparecen en
`pyproject.toml`**, y añadir un cliente de red para poder medir un contrato
sería comprar una dependencia sin criterio para no medir nada.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final, Protocol, runtime_checkable

from skillgraph.core.errors import ValidationError
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
    "KIND_RUNTIME",
    "TELEMETRY_QUERY",
    "LectorTelemetria",
    "TelemetryQueryCapability",
    "Ventana",
    "envelope_a_payload",
]

#: El TIPO de esta capability. Constante y no cadena suelta (`AGENTS.md`
#: 2.4), por el mismo motivo que `KNOWLEDGE_QUERY` en el modulo de al lado.
TELEMETRY_QUERY: Final[str] = "sg.telemetry.query"

#: El kind que declara un envelope de runtime. Vive aqui y no repetido, por
#: la misma regla que `REGLAS_DE_NOMBRE_SEGURO` en `platform/paths.py`: dos
#: enunciados de la misma regla son dos fuentes que se desincronizan, y una
#: ya se ha desincronizado en este repo (el mensaje de nombre de proyecto
#: anunciaba `[a-z0-9-_]` mientras `is_safe_name` aceptaba mayusculas).
KIND_RUNTIME: Final[str] = "runtime_observation"


@dataclass(frozen=True, slots=True)
class Ventana:
    """El periodo que se pregunta. `[desde, hasta)`, y el `hasta` puede faltar.

    **POR QUE `[desde, hasta)` Y NO `[desde, hasta]`.** No es una elección de
    gusto, y el mismo razonamiento ya está escrito para las ventanas de
    vigencia de B29: dos observaciones que se tocan en el borde tienen el
    final de la primera igual al principio de la segunda, y con el extremo
    superior **inclusivo** una consulta en ese instante devolvería las dos
    —media mitad de una respuesta—. Se declara aquí porque esta ventana la
    escribe quien pregunta, no quien observa, y es el que puede equivocarse.

    `hasta=None` significa «hasta ahora»: una consulta abierta. Es una
    declaración distinta de `desde=None`, y por eso `desde` **no** puede
    faltar — una ventana sin principio no es una ventana.
    """

    desde: str
    hasta: str | None = None

    def __post_init__(self) -> None:
        if not self.desde or not self.desde.strip():
            raise ValidationError(
                "Ventana sin `desde`: una ventana sin principio no es una ventana. "
                "Una consulta de telemetria empieza en algun momento, y si lo que "
                "se quiere es «siempre», eso se dice con un `desde` de la historia"
            )
        if self.hasta is not None and not self.hasta.strip():
            raise ValidationError(
                f"Ventana con `hasta` vacio ({self.hasta!r}): una ventana no se cierra "
                "en la nada. Dejalo en None si lo que quieres es una consulta abierta"
            )

    @property
    def abierta(self) -> bool:
        """Si la ventana sigue abierta. `hasta=None` lo dice, y no hay que
        deducirlo mirando el reloj."""
        return self.hasta is None


@runtime_checkable
class LectorTelemetria(Protocol):
    """Lo que el despliegue tiene que saber leer. **Solo el contrato.**

    Es un `Protocol` y no una clase concreta por el motivo que declara
    `AGENTS.md` 4.3: el núcleo depende del puerto, no de la implementación.
    Lo que se implementa fuera —Chronos, OTel, un fichero, un stub de test—
    no lo decide este repo, y escribirlo aquí sería lo que la propia
    `KnowledgeQueryCapability` llama «el camino corto a que un adapter se
    confunda con un puerto».

    `tuple`, nunca `list`: lo que sale de aquí cruza una frontera y entra en
    un envelope `frozen`, y una lista mutable metida en una estructura
    inmutable es una lista que alguien va a mutar.
    """

    def observaciones(self, *, sujeto: str, ventana: Ventana) -> tuple[Observation, ...]:
        """Lo que se vio de `sujeto` durante `ventana`."""
        ...


class TelemetryQueryCapability:
    """La capability que convierte **una ventana** en **una observación**.

    Es el lado de la vertical que B28 no tenía. No decide nada: pregunta por
    un periodo a quien sabe, y devuelve un envelope que ya dice de dónde
    viene, cuándo se miró y **qué periodo cubrió**. Esa última frase es la
    que B26 no podía decir, y la que hace que una afirmación de runtime no
    tenga que disfrazarse de documento.
    """

    def __init__(
        self,
        lector: LectorTelemetria,
        *,
        source_id: str,
        revision: str,
    ) -> None:
        """Inyecta el lector **por constructor**, como `Protocol` que es.

        `source_id` y `revision` también entran aquí y no se leen del reloj:
        el envelope que sale es una **frontera** (B26), y una frontera que
        lee el reloj hace que la misma consulta produzca dos envelopes
        distintos cada vez — que es la idempotencia rompiéndose sola, sin
        que nada lo indique.

        Args:
            lector: quien sabe leer. No se valida que sea un `Protocol`
                aquí: se valida al invocar, y una validación en el
                constructor solo produciría el error antes de que el
                llamante pueda dar contexto.
            source_id: la identidad de la fuente que producirá este envelope.
            revision: contra qué revisión se registró lo observado. Es el
                reloj de B29 (`checked_at_revision`) y **no** es la ventana:
                una cosa es cuándo se miró el código y otra qué periodo se
                vio funcionando.
        """
        self._lector = lector
        self._source_id = source_id
        self._revision = revision

    @property
    def spec(self) -> CapabilitySpec:
        """La identidad. La `version` la hereda del puerto y no se escribe
        aquí, por el motivo que declara `KnowledgeQueryCapability.spec`: si
        el adapter declarase la suya, cada uno podría inventarla."""
        return CapabilitySpec(
            type_name=TELEMETRY_QUERY,
            summary=(
                "Pregunta a una fuente de telemetria por un periodo y devuelve "
                "el envelope versionado de lo que se vio"
            ),
        )

    def invoke(self, request: CapabilityRequest) -> CapabilityResult:
        """La vertical entera, en una llamada.

        Lo que **no** hace, y es deliberado: no escribe en el store. Un
        adaptador que escribe deja de ser un adaptador y se convierte en la
        razón por la que hay que confiar en él — que es exactamente lo que
        `ADR-0027` rechazó (`escribir Storage desde adapter`). Lo que hace
        es devolver la frontera, y que la ingesta la aplique.
        """
        ventana = ventana_de(request)
        observado_en = _instante_de(request)
        observaciones = self._lector.observaciones(sujeto=request.subject, ventana=ventana)
        envelope = self._envelope(request.subject, observaciones, ventana, observado_en)
        return CapabilityResult(
            spec=self.spec,
            adapter=type(self).__name__,
            payload={
                "subject": request.subject,
                "ventana": {"desde": ventana.desde, "hasta": ventana.hasta},
                "envelope": envelope_a_payload(envelope),
            },
        )

    def _envelope(
        self,
        sujeto: str,
        observaciones: tuple[Observation, ...],
        ventana: Ventana,
        observado_en: str,
    ) -> ObservationEnvelope:
        """El envelope, y la DECLARACIÓN de que esto se vio.

        **POR QUE `observed_at` ENTRA POR ARGUMENTO Y NO SE DERIVA.** Con una
        ventana cerrada la respuesta obvia sería `ventana.hasta`, y con una
        abierta no hay respuesta: «hasta ahora» es un instante que esta
        capability **no puede saber sin leer el reloj**, y leerlo rompe la
        idempotencia por la razon que `B26` ya escribio en el docstring de
        `observed_at`. Por eso lo declara quien pregunta —que sabe cuando
        esta preguntando— y no quien responde. Para una ventana cerrada lo
        natural es pasar `ventana.hasta`; para una abierta, el instante en
        que se pregunta.

        Cuando no hay observaciones se levanta el error, y no se devuelve un
        envelope vacío: `ObservationEnvelope` ya rechaza los vacios, y
        hacerlo aquí cambia el mensaje de sitio — quien lo lee necesita saber
        que la ventana no dio nada, no que el envelope se rompió.
        """
        if not observaciones:
            raise ValidationError(
                f"la ventana [{ventana.desde}, {ventana.hasta}) no devolvio ninguna "
                f"observacion de {sujeto!r}: no hay nada que afirmar, y un envelope "
                "vacio se ingeria como no-op y parece que funciono"
            )
        return ObservationEnvelope(
            producer=self.spec,
            adapter=type(self).__name__,
            source_id=self._source_id,
            subject=sujeto,
            observed_at=observado_en,
            revision=self._revision,
            observations=observaciones,
            version=VERSION_ENVELOPE,
            kind=KIND_RUNTIME,
            observed_from=ventana.desde,
            observed_to=ventana.hasta,
        )


def ventana_de(request: CapabilityRequest) -> Ventana:
    """La ventana, leída de la petición y validada en la frontera.

    Se construye `Ventana` —que valida— en vez de leer dos cadenas sueltas,
    para que una ventana sin `desde` falle aquí y no tres capas más abajo.

    **POR QUE ES PUBLICA Y NO UNA `_privada`.** La ingesta, el CLI y los
    tests tienen que leer la misma ventana que la capability, y tres
    lectores de un `dict` son tres formas de leerlo que se separan. Es la
    misma razón que hace pública `query_intent()` en `knowledge/authority.py`.

    Raises:
        ValidationError: si `arguments['ventana']` no trae las claves
            esperadas, o no es un mapping.
    """
    crudo = request.arguments.get("ventana")
    if not isinstance(crudo, dict):
        raise ValidationError(
            f"{TELEMETRY_QUERY} necesita request.arguments['ventana'] con las claves "
            f"'desde' y 'hasta' (esta puede faltar), y recibio {crudo!r}"
        )
    if "desde" not in crudo:
        raise ValidationError(
            f"{TELEMETRY_QUERY} necesita request.arguments['ventana']['desde']: "
            "una ventana sin principio no es una ventana"
        )
    return Ventana(desde=crudo["desde"], hasta=crudo.get("hasta"))


def _instante_de(request: CapabilityRequest) -> str:
    """El instante en que se pregunta, declarado por quien pregunta.

    Se valida que no venga vacío por la misma razón que `Ventana.__post_init__`
    valida `desde`: un `observed_at` vacío se colaría hasta `ObservationEnvelope`,
    que sí lo rechaza, pero con un mensaje que habla del envelope cuando el
    que lo escribió estaba llamando a una capability.
    """
    instante = request.arguments.get("observed_at")
    if not isinstance(instante, str) or not instante.strip():
        raise ValidationError(
            f"{TELEMETRY_QUERY} necesita request.arguments['observed_at']: el instante "
            "en que se pregunta. Esta capability NO lee el reloj —leerlo haria que la "
            "misma consulta diera dos envelopes distintos cada vez— y con una ventana "
            "abierta no hay ningun instante que se pueda deducir"
        )
    return instante


def envelope_a_payload(envelope: ObservationEnvelope) -> dict[str, Any]:
    """El envelope, en la forma que viaja por `CapabilityResult.payload`.

    Se hace con `asdict` y no a mano porque **la serialización es el punto
    donde se pierde la fidelidad**: un campo añadido al envelope y olvidado
    aquí es un dato que sale del sistema sin que nadie lo note. Ese es el
    modo de fallo que `ADR-0027` cerró con `schemaRef`, y el que Justamente
    evita repetir el mismo nombre de campo en dos sitios.
    """
    return asdict(envelope)
