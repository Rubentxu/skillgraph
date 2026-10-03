"""B3 — el CONTRATO de una capability, y su resolucion. Sin adapters.

Este modulo es la pieza que B1 identifico como ausente. B1 midio 32
`Protocol` en `platform/ports` y escribio, con la honestidad que exige el
bloque: *«NO es un defecto: es que el concepto de capability que pide B3
todavia no existe como tal — lo que hay son puertos de persistencia»*.

Aqui es lo que faltaba. Un `Capability` es **un tipo con un contrato y
un adaptador**, no un `str` que viaja en el handoff y no ejecuta nada.

**LO QUE MEDIDO HACE ESTE MODULO.** Antes de escribirlo, sobre el árbol
real:

```
WorkflowNode.capabilities          : tuple[str, ...]      (src/skillgraph/resources/workflow.py:71)
graph_expansion._check_capabilities: comprueba contra un registry Mapping[str, str]
knowledge.build_capabilities       : produce ('stale',)    un marcador sintetico
http_adapter._build_prompt         : las imprime en el prompt
alguien que las RESUELVA           : —— NINGUNO ——
```

Se declaraban, se transportaban, se serializaban, se imprimian en el
prompt y se validaban contra un registro de strings. **Nunca se
resolvian a nada ejecutable.** Ese es el hueco que B3 cierra, y es un
hueco de ARQUITECTURA, no de una funcion que falte.

**POR QUE UN REGISTRO INYECTADO Y NO UN REGISTRO GLOBAL.** Podria parecer tentador registrar capabilities al importarse (`@register` sobre
la clase): seria menos codigo. Es exactamente lo que `AGENTS.md 1.4` prohibe
—estado global mutable, singletons implicitos— y lo haria por una
razon concreta: dos tests que registraran capabilities distintas en el
mismo proceso se contaminarian, y el orden de importacion decidiria el
resultado. Un `CapabilityRegistry` es un **valor**: se construye, se pasa
por constructor, y dos registros con las mismas capabilities son
identicos. Eso es lo que hace que B3 sea comprobable.

**Y POR QUE `resolve` LANZA UN ERROR TIPADO Y NO DEVUELVE `None`.** Un
`Optional[Capability]` obliga a que cada llamante decida que hacer con
la ausencia, y uno de ellos decidira seguir como si no hubiera pasado
nada. Una capability pedida y no encontrada **es un fallo del
operador** —el plan declara algo que el despliegue no sabe hacer— y tiene
que salir como `CapabilityNotFound`, que es un `SkillGraphError`, que la
CLI traduce a exit code (el mecanismo de WI-109). Un `None` se
convierte en un fallo silencioso tres capas mas abajo.

**POR QUE NO SE REEXPORTA DESDE `ports/__init__.py`.** `__init__` es el
indice que WI-69 cerro con un contrato explicito de **catorce** tipos —
`tests/test_wi69_ports_split.py:78` afirma `len(ALL) == 14`— y su
docstring dice que reexporta `dto` y `repositories`. Anadir capabilities
seria cambiar el contrato de WI-69 desde dentro de B3, que es
justamente la mezcla de bloques que este repo evita. Ademas, lo que se
importa aqui es un **contrato**, no un tipo almacenado: se usa por su
ruta completa (`from skillgraph.platform.ports.capabilities import ...`),
que ademas deja el origen a la vista cuando se busca de donde sale una
capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from skillgraph.core.errors import NotFoundError, ValidationError

__all__ = [
    "CAPABILITY_VERSION",
    "Capability",
    "CapabilityNotFound",
    "CapabilityRegistry",
    "CapabilityRequest",
    "CapabilityResult",
    "CapabilitySpec",
]

#: Version del CONTRATO, no de una capability concreta.
#:
#: B8 pide un formato de compatibilidad explicito
#: (`requires.capabilities: [code.analysis.v1]`), y para que ese formato
#: tenga sentido tiene que haber una version que versionar. Se pone aqui,
#: en el puerto, porque es el core el que decide que forma tiene el
#: contrato: si la version viviera en cada adapter, cada adapter podria
#: inventar la suya y no habria nada que comparar.
CAPABILITY_VERSION: Final[str] = "v1"


class CapabilityNotFound(NotFoundError):
    """Se pidio una capability que el registro no tiene.

    `NotFoundError` y no `ValidationError`: el plan es valido —declara
    una capability con nombre correcto— lo que falta es el **despliegue**.
    La distincion importa porque el operador arregla cosas distintas en
    cada caso: un `ValidationError` se arregla editando el plan, este se
    arregla instalando el adapter.

    El mensaje dice CUAL se pidio y CUALES hay. Un "capability no
    encontrada" sin las dos mitades obliga a buscar a mano en el
    despliegue, que es el trabajo que el error existe para evitar.
    """

    code = "sg_capability_not_found"


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """La identidad de una capability: tipo, version y que es.

    Inmutable y **comparable por valor**: dos adapters del mismo tipo y
    version son la misma capability, y eso es lo que hace que un registro
    pueda detectar que dos adapters se solapan en vez de acceptarlos en
    silencio.
    """

    type_name: str
    version: str = CAPABILITY_VERSION
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.type_name or not self.type_name.strip():
            raise ValidationError("CapabilitySpec.type_name no puede estar vacio")
        if not self.version or not self.version.strip():
            raise ValidationError("CapabilitySpec.version no puede estar vacio")


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """Lo que se pide a una capability.

    `arguments` es un `Mapping` inmutable y el dataclass es `frozen`, por
    la regla de `AGENTS.md 1.1`: el request que sale de la frontera no
    puede ser modificado por quien lo recibio. Es el mismo motivo por el
    que WI-113 metio `deepcopy` en `AgentResult.result`.
    """

    spec: CapabilitySpec
    subject: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.subject or not self.subject.strip():
            raise ValidationError("CapabilityRequest.subject no puede estar vacio")


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Lo que devuelve una capability. SIEMPRE con su procedencia.

    `adapter` es parte del resultado, no un campo del log. Es lo que
    permite despues responder «¿quien afirmo esto?» — que es la pregunta
    que B6 quiere poder hacer de todo lo que hay en el Knowledge Graph,
    y que sin este campo no tiene respuesta.
    """

    spec: CapabilitySpec
    adapter: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return True


@runtime_checkable
class Capability(Protocol):
    """El CONTRATO. Lo que el core necesita saber de una capability.

    Deliberadamente **minimo**: `spec` (quien es) e `invoke` (que hace).
    Todo lo demas que se le ocurra a un adapter —cache, reintentos,
    telemetria— es asunto del adapter, no del core.

    Un solo metodo. La tentacion de anadir `describe()`, `health()` o
    `version()` aqui es la que hace que un puerto deje de ser un puerto:
    en cuanto el contrato crece, el core empieza a depender de detalles
    que solo a un adapter le importan.
    """

    @property
    def spec(self) -> CapabilitySpec: ...

    def invoke(self, request: CapabilityRequest) -> CapabilityResult: ...


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    """El conjunto de capabilities que un despliegue sabe resolver.

    **Es un valor, no un singleton.** Se construye, se inyecta, y dos
    registros identicos son iguales. Es la diferencia entre «el
    despliegue sabe hacer esto» —un hecho, comprobable— y «hay un
    registro global que se va llenando» —un estado que depende del orden
    de importacion—.
    """

    capabilities: tuple[Capability, ...] = ()

    def __post_init__(self) -> None:
        vistos: dict[tuple[str, str], str] = {}
        for cap in self.capabilities:
            clave = (cap.spec.type_name, cap.spec.version)
            if clave in vistos:
                raise ValidationError(
                    f"dos adapters de la misma capability "
                    f"({cap.spec.type_name} {cap.spec.version}): "
                    f"{vistos[clave]!r} y {type(cap).__name__!r}. "
                    "Un despliegue tiene una implementacion por capability; "
                    "si se quiere elegir entre varias, la ELECCION es una "
                    "politica, no un accidente de construccion."
                )
            vistos[clave] = type(cap).__name__

    @property
    def types(self) -> tuple[str, ...]:
        """Los tipos que este despliegue sabe resolver, ordenados."""
        return tuple(sorted({c.spec.type_name for c in self.capabilities}))

    def resolve(self, type_name: str, *, version: str = CAPABILITY_VERSION) -> Capability:
        """La capability de ese tipo, o `CapabilityNotFound` con la lista.

        **POR QUE EL ERROR LLEVA LA LISTA.** Un "no encontrada" sin
        contexto obliga a un `ls` a mano sobre el despliegue, y en un
        despliegue con packs es una busqueda entre N fuentes. Con la
        lista, el mensaje dice que hay: normalmente es un typo, y se ve
        en la linea de error.
        """
        for cap in self.capabilities:
            if cap.spec.type_name == type_name and cap.spec.version == version:
                return cap
        raise CapabilityNotFound(
            f"capability {type_name!r} (version {version}) no la resuelve "
            f"este despliegue. Resuelve: {self.types or '(ninguna)'}"
        )

    def supports(self, type_name: str) -> bool:
        """¿La sabe? Para consultar sin pagar la excepcion.

        `resolve` lanza porque el caso «no la sabe» es un error del
        operador. Aqui se pregunta sin error, que es otra pregunta, y por
        eso son dos funciones: usar `resolve` en un `if` seria informar
        de un fallo como si fuera una condicion normal.
        """
        return any(c.spec.type_name == type_name for c in self.capabilities)

    def missing_from(self, required: tuple[str, ...]) -> tuple[str, ...]:
        """Las que faltan, para un informe o una politica.

        A diferencia de `resolve`, aqui la ausencia **no** es un fallo:
        es el dato que un policy engine necesita para decidir. Por eso
        devuelve la lista en vez de lanzar.
        """
        return tuple(sorted(r for r in required if not self.supports(r)))
