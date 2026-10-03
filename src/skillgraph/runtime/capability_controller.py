"""B3-cierre R2 — el controller kernel: donde un NOMBRE se ejecuta.

El contrato de B3 ya existe (`platform/ports/capabilities.py`) y ya se
resuelve (`CapabilityRegistry`). Lo que faltaba era el punto donde un
**nombre escrito en un plan** se convierte en una ejecucion.

**POR QUE NO VA EN `core/`.** El docstring de `core/__init__.py` dice, sin
ambiguedad: *«Pure types and errors that have no dependency on
infrastructure, storage, runtime, or any other bounded context»*. Este
modulo consume `platform.ports`, que es **otro contexto acotado**, luego
meterlo en `core/` seria violar la regla que el propio paquete declara
sobre si mismo. Va en `runtime/`, con el resto de la orquestacion
(`engine.py`, `runcontroller.py`), que ya importa `platform.ports`.

Medido, ademas, para no afirmar una estratificacion que este repo no
tiene: hay **10** imports de `platform/` hacia `runtime/` y `knowledge/`.
`platform` NO es una capa inferior aqui —es la razon por la que `Storage`
puede hablar con el motor—, luego no se escribe ningun guard de
"platform no importa a runtime". Seria una regla inventada, roja desde el
primer dia, y sin relacion con el gate de B3.

**LA FRONTERA QUE SI SE GUARDA, Y POR QUE ES ESTRUCTURAL.** Ningun modulo
del nucleo nombra una capability concreta. Se mide por AST porque la
propiedad es de estructura: un test de comportamiento pasaria igual con un
`if tipo == "sg.knowledge.query"` en el cuerpo de este modulo, ya que el
resultado seria el mismo. Lo que se compra es que manana aparezca
`sg.telemetry.query` y este fichero **no cambie**.

**POR QUE `CapabilityOutcome` Y NO SOLO UN `CapabilityResult`.** Porque el
`type_name` PEDIDO y el `spec` que RESPONDIO son dos cosas distintas: un
despliegue podria resolver un pedido con otra version. Guardar solo el
resultado pierde el pedido; guardar solo el pedido pierde quien respondio.
Sin el par no se puede auditar «este nodo pidio X y alguien entrego Y»,
que es la pregunta que B6 quiere poder hacer de todo lo que hay en el
grafo.

**LO QUE ESTE KERNEL NO HACE, AUNQUE EL NOMBRE LO SUGIERA.**

- **No emite eventos.** La procedencia se persiste desde `699e67d`, en el
  motor, que es quien sabe que adapter invoco. Si el kernel emitiera,
  habria dos sitios que afirmar quien produjo algo, y el segundo seria
  peor: el que no lo ejecuto.
- **No muta el grafo.** Un controller **observa y propone**, que es lo que
  dice el roadmap de B4. Este devuelve; escribir es trabajo de quien lo
  invoca.
- **No decide politica.** Dice que falta y ejecuta lo que hay. Si eso es
  admisible es decision de otro bloque.
"""

from __future__ import annotations

from dataclasses import dataclass

from skillgraph.platform.ports.capabilities import (
    CAPABILITY_VERSION,
    Capability,
    CapabilityNotFound,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResult,
)

__all__ = ["CapabilityController", "CapabilityOutcome"]


@dataclass(frozen=True, slots=True)
class CapabilityOutcome:
    """Lo que se PIDIO y lo que RESPONDIO, juntos y con nombre.

    Inmutable (`AGENTS.md 1.1`): esto sale de la frontera y lo va a
    recibir alguien que no deberia poder alterarlo. Y la tupla que devuelve
    el kernel tambien, por el mismo motivo — un `list` que el llamante
    muta cambia el numero de capabilities ejecutadas sin que nadie lo sepa.
    """

    requested: str
    result: CapabilityResult

    @property
    def served_by(self) -> str:
        """Quien respondio. Distinto de `requested`: es un TIPO."""
        return self.result.adapter

    @property
    def version_served(self) -> str:
        """La version que se sirvio, que puede no ser la que se pidio.

        Es la razon de que este tipo exista: si solo se guardara el
        resultado, esta comparacion no se podria hacer.
        """
        return self.result.spec.version


class CapabilityController:
    """Ejecuta lo que un nodo declara, contra lo que el despliegue sabe.

    El registro se **inyecta**. No hay registro por defecto, no hay
    singleton, no hay carga perezosa: un kernel que se fabricara su propio
    registro seria el estado global mutable que `AGENTS.md 1.4` prohibe, y
    es el mismo defecto por el que el primer gate de B3 no distinguia un
    valor de un singleton —un singleton siempre es igual a si mismo, y la
    asercion pasaba mientras la contaminacion seguia ahi.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    @property
    def types(self) -> tuple[str, ...]:
        """Lo que este despliegue sabe. Para un informe o un policy check."""
        return self._registry.types

    def missing(self, required: tuple[str, ...]) -> tuple[str, ...]:
        """Las que faltan, sin lanzar. Una consulta, no un fallo.

        Es la forma que necesita un motor de politica para DECIDIR; frente
        a `resolve`, que lanza porque la ausencia ahi si es un fallo del
        despliegue. Son dos preguntas y por eso son dos funciones.
        """
        return self._registry.missing_from(required)

    def execute(
        self,
        *,
        subject: str,
        required: tuple[str, ...],
        arguments: dict[str, object] | None = None,
    ) -> tuple[CapabilityOutcome, ...]:
        """Ejecuta cada capability pedida y devuelve lo que respondio.

        **Falla entero, no a medias.** Si una de las que pide el nodo no
        esta, no se ejecuta ninguna: un resultado a medias deja al
        llamante con la impression de que el nodo se ejecuto, y no se
        ejecuto. La comprobacion es ANTES del bucle, con
        `missing_from`, que ya existe en el contrato y devuelve la lista
        en vez de lanzar.

        `required=()` devuelve `()`. No «todo lo que el registro tenga»:
        un nodo que no declara capabilities no ha pedido ninguna, y
        confundirlos ejecutaria trabajo que nadie pidio.
        """
        if not required:
            return ()
        faltan = self._registry.missing_from(required)
        if faltan:
            raise CapabilityNotFound(
                f"el despliegue no resuelve {list(faltan)}. "
                f"Resuelve: {list(self._registry.types) or '(ninguna)'}"
            )
        return tuple(self._uno(tipo, subject=subject, arguments=arguments) for tipo in required)

    def _uno(
        self,
        type_name: str,
        *,
        subject: str,
        arguments: dict[str, object] | None,
    ) -> CapabilityOutcome:
        """Resuelve una y la invoca. El nucleo no sabe que hay ahi."""
        cap: Capability = self._registry.resolve(type_name, version=CAPABILITY_VERSION)
        resultado = cap.invoke(
            CapabilityRequest(
                spec=cap.spec,
                subject=subject,
                arguments=dict(arguments) if arguments else {},
            )
        )
        return CapabilityOutcome(requested=type_name, result=resultado)
