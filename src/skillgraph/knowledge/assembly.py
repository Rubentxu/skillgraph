"""B35 — el punto de ensamblado: quien despliegue, por fin.

**LO QUE ESTO CONTESTA, MEDIDO ANTES DE ESCRIBIR UNA LINEA**
(`scripts/measure_b35_vertical.py`, ronda 1):

    CapabilityRegistry(...) construido en src/   : 0
    CapabilityRegistry(...) construido en tests/ : 26
    CodeAnalysisCapability    instanciada en src/ : 0
    TelemetryQueryCapability  instanciada en src/ : 0
    KnowledgeQueryCapability  instanciada en src/ : 0

Tres capabilities al 100 % de cobertura y **ningun despliegue puede
resolverlas**, porque no hay quien las meta en un registro. Y no es un
descuido de B31: es el estado que `runcontroller.py:148` declara y que
B3-cierre acepto a proposito — la costura `capabilities=` existe con default
`None`, el ensamblado no, porque la exigencia la PIDE quien despliega.

**LA PUNJA ES QUE NO HAY QUIEN DESPLIEGUE.** El repo tiene un ejecutable
(`sg`) y ninguna forma de que `sg` monte un registro. Eso no es una decision
de arquitectura; es una decision que nadie habia tomado.

## LO QUE ENTREGA

Una funcion pura que responde «que sabe hacer este despliegue» y devuelve un
`CapabilityRegistry` **valor**, no un singleton. `CapabilityRegistry` ya es un
valor por decision propia (su docstring: «se construye, se inyecta, y dos
registros identicos son iguales»), asi que aqui no se introduce ningun estado
global — que es `AGENTS.md` 1.4.

## Y LO QUE **NO** ENTREGA, CON SU MOTIVO

**NO ensambla `sg.telemetry.query`.** MEDIDO: `LectorTelemetria` es un
`Protocol` con **cero implementaciones en `src/`** — la unica que existe esta
en los tests de B33. Ensamblar esa capability seria inventar el lector que
la hace funcionar, y una capability montada con un lector de carton daria
respuestas sobre un runtime que no ha visto nunca.

Se declara aqui, en el codigo, para que quien venga lea el porque antes de
decidir si le pone un lector. Es la misma deuda con nombre que
`spec_revision` y `test_passes` de B31: dos cosas que el vocabulario promete y
que no tienen escritor.

**NO cambia la politica de `capabilities=None`.** Sigue siendo opcional y
sigue significando «este plan no exige capabilities». Lo que hace este modulo
es DAR QUIEN DESPLIEGA, que hasta ahora no existia. Si el mismo cambio
hiciera las dos cosas, seria otro bloque y habria que medirlo aparte.

**NO lee disco ni el reloj.** El `source_id` y el `revision` entran por
argumento, por el motivo que `AGENTS.md` 1.3 exige y que `telemetry_query`
ya declara en cuatro parrafos: una frontera que lee el reloj rompe la
idempotencia sola, porque el `claim_id` lo incluye en su semilla.
"""

from __future__ import annotations

from typing import Final

from skillgraph.core.errors import ValidationError
from skillgraph.knowledge.code_analysis import CODE_ANALYSIS, CodeAnalysisCapability
from skillgraph.knowledge.knowledge_query import KNOWLEDGE_QUERY, KnowledgeQueryCapability
from skillgraph.platform.ports.capabilities import Capability, CapabilityRegistry
from skillgraph.platform.ports.repositories import KnowledgeRepository

__all__ = ["CAPACIDADES_ENSAMBLADAS", "registro_de_conocimiento"]

#: Las capabilities que este despliegue sabe resolver, en orden.
#:
#: **POR QUE ES UNA CONSTANTE Y NO SE DEDUCE DEL REGISTRO.** Es una
#: DECLARACION de lo que un despliegue con esta base ofrece, y un `Final` que
#: se derivara de las capabilities construidas seria un guard que compara
#: contra su propia copia. Ademas su valor es real: `sg.telemetry.query` NO
#: esta, por el motivo del docstring del modulo, y por eso la lista tiene dos
#: entradas y no tres.
CAPACIDADES_ENSAMBLADAS: Final[tuple[str, ...]] = (CODE_ANALYSIS, KNOWLEDGE_QUERY)


def registro_de_conocimiento(
    knowledge: KnowledgeRepository,
    *,
    tenant_id: str,
    project_id: str,
    source_id: str,
    revision: str,
) -> CapabilityRegistry:
    """El registro que este despliegue sabe resolver, como **valor**.

     **POR QUE `source_id` Y `revision` SON ARGUMENTOS Y NO SE DEDUCEN.**
     MEDIDO: `CodeAnalysisCapability` exige los dos en su constructor, y no se
     pueden inventar — `source_id` identifica la fuente que produce el
     envelope, y es la que hace que `changed` de B29 pueda separar dos
     analisis del MISMO fichero en dos revisiones; `revision` es el reloj de
     `checked_at_revision`, que no tiene nada que ver con el contenido: el
     fichero es el mismo antes y despues de que cambie el git que lo versiona.

     **Y POR QUE EL REGISTRO ES UN ARGUMENTO QUE SE DEVUELVE, NO UNA COSA
     QUE SE DEJA.** `AGENTS.md` 1.4 prohibe el estado global mutable, y un
     registro que se rellena al importar el paquete tiene su contenido
    depende del orden de importacion. Este devuelve el valor y no lo guarda en
     ningun sitio: quien despliega decide cuando construirlo.

     Args:
         knowledge: el repositorio de conocimiento. Es lo que hace resolubles
             a `sg.knowledge.query`.
         tenant_id: el tenant. No se deduce de `knowledge` porque un
             repositorio puede servir a varios y confundirlos seria el peor
             fallo posible en una consulta.
         project_id: el proyecto, por el mismo motivo.
         source_id: la fuente que producira los envelopes de analisis.
         revision: la revision contra la que se registra el analisis.

     Returns:
         Un `CapabilityRegistry` con `sg.code.analysis` y `sg.knowledge.query`,
         y NO con `sg.telemetry.query`. El orden es el de
         `CAPACIDADES_ENSAMBLADAS`, para que dos despliegues iguales produzcan
         registros iguales.

     Raises:
         ValidationError: si algun identificador llega vacio. No es una
             comprobacion de ventana de cierre: cada uno de estos valores entra en un
             hash firmado o en un `UNIQUE`, y un identificador vacio ahi es
             una fila que dos analisis distintos se pelean.
    """
    for nombre, valor in (
        ("tenant_id", tenant_id),
        ("project_id", project_id),
        ("source_id", source_id),
        ("revision", revision),
    ):
        if not isinstance(valor, str) or not valor.strip():
            raise ValidationError(
                f"registro_de_conocimiento necesita {nombre} no vacio: recibo {valor!r}"
            )

    return CapabilityRegistry(
        capabilities=(
            CodeAnalysisCapability(source_id=source_id, revision=revision),
            KnowledgeQueryCapability(knowledge, tenant_id=tenant_id, project_id=project_id),
        )
    )


def declare(*caps: Capability) -> tuple[str, ...]:
    """Los tipos que un registro declara, para un mensaje de error util.

    No es la funcion que este bloque necesita —`CapabilityRegistry.types`
    existe para eso—, y se queda porque es el patron que usan
    `CapabilityNotFound` y `CapabilityController.missing`: **un error que no
    dice que hay obliga a un `ls` a mano**. Sin usar, el suelo de cobertura de
    §6.3 lo pedira y habra que fabricarle un test de carton, que es peor que
    no tener la funcion.
    """
    return tuple(sorted(c.spec.type_name for c in caps))
