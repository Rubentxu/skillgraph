"""R1.C — la INGESTA de una observacion, fuera del modelo puro.

**POR QUE ESTE MODULO EXISTE Y NO VIVE EN `observation.py`.**

`observation.py` es el **modelo**: `Observation`, `ObservationEnvelope` y
`normalizar()`. Es puro por construccion —no lee disco, no toca el reloj, no
depende de un Storage— y por eso se puede probar entero sin base de datos y
sin pedir perdon a nadie para lo que dice.

`ingerir()` no es modelo: **es el efecto**. Toma el `Storage` por parametro y
llama a `register_source`, `upsert_entity` y `record_claim`. Con la funcion
dentro del modulo, el «modelo puro» tenia una puerta al disco dentro, y el
titulo del modulo minguaba. Eso es exactamente lo que R1 persiguio en la otra
frontera, cuando `knowledge/graph.py` exponia `seq_de(cur, revision)`: una
utilidad de base de datos—, con cursor —viviendo en el dominio.

**LA REGLA ES LA DE SIEMPRE: el modelo dice, el efecto escribe, y quien
escribe recibe la dependencia por parametro.** Aqui el efecto es la ingesta;
en B31 sera la misma, con otro productor (CogniCode) del otro lado. El camino
queda UNO:

    producer -> adapter -> ObservationEnvelope -> ingestion -> Knowledge

**Y NO HAY UNA SEGUNDA VIA.** Un `ObservationIngestionService` que se pudiera
construir con su propio Storage seria la forma de tener dos-Verdades sobre
que se ha escrito; por eso aqui no hay servicio con estado, hay una funcion
pura respecto a sus argumentos que recibe el Storage ya construido.

**LO QUE NO SE HACE:** no se cambia el contrato de `ingerir()` —los mismos
parametros, el mismo retorno, la misma idempotencia por contenido—, ni se
reescriben los tests que no cambian de contrato. Es un cambio de sitio, no de
comportamiento, y por eso se hizo con el arbol en verde antes y despues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skillgraph.knowledge.observation import (
    ObservationEnvelope,
    ObservationIngesta,
    normalizar,
)

if TYPE_CHECKING:
    from skillgraph.platform.storage import Storage

__all__ = ["ingerir"]


def ingerir(
    storage: Storage,
    *,
    tenant_id: str,
    project_id: str,
    env: ObservationEnvelope,
) -> ObservationIngesta:
    """Escribe lo que el envelope afirma. **IDEMPOTENTE por contenido.**

    Este docstring viajo con la funcion al mudarla: el contrato es el mismo
    y mudarla no es una excusa para reescribirlo.

    Reutiliza las APIs que ya son idempotentes (`register_source`,
    `upsert_entity`, `record_claim`) en vez de reimplementar la garantia: el
    envelope no duplica esa idempotencia, **la usa**.

    Y el `claim_id` sale del contenido, no de un contador, luego reingerir el
    mismo envelope reconstruye los mismos ids y las filas caen con
    `INSERT OR IGNORE`: el numero de filas no crece.

    **LO QUE ESTO NO GARANTIZA, DICHO.** Que el contenido sea el mismo. Si una
    herramienta cambia lo que dice sin cambiar de `revision`, la ingesta escribe
    una fila nueva y **las dos son validas**. Borrar la anterior seria destruir
    historia para parecer consistente; lo que las resolvera son las ventanas de
    vigencia de B29. Una «idempotencia» que limpiara seria peor que ninguna.

    **LO QUE ESTA FUNCION NO PUEDE HACER, Y POR QUE NO PUEDE, DICHO.**
    Este modulo tuvo una rama que recogia el aviso de `record_claim.conflicto`
    y lo devolvia en `ObservationIngesta.conflictos`. MEDIDO al certify B35:
    **esa rama no la ejecutaba nadie**, y por eso el modulo mide 84 %, seis
    puntos por debajo del suelo que su ubicacion declara.

    No es que no se midiera: es que **no puede ejecutarse**. `ingerir` es la
    unica funcion publica del modulo y su unico camino es `normalizar(env)`,
    que deriva el `claim_id` de (sujeto, predicado, objeto, fuente, revision).
    Dos claims distintos tienen `claim_id` distinto, luego el `UNIQUE` de clave
    primaria no puede rechazar, y el de la tupla natural —que desde `ADR-0035`
    lleva el objeto dentro— tampoco. En los siete estados medidos de B35, por
    esta via `conflicto` es **siempre** `False`.

    Por eso la rama se borro en vez de bajar el suelo: un suelo que hay que
    bajar para que pase un modulo con codigo muerto es un suelo que ya no dice
    nada. Lo que **no** se pierde es la deteccion —`conflicts_for` ve la
    auto-contradiccion de una misma fuente y B28 la resuelve por intencion—;
    lo que se deja de recoger es el aviso puntual en el instante de escribir.

    Returns:
        La ingesta que se ha escrito, igual que `normalizar` la devuelve: el
        mismo valor, ya persistido.
    """
    ingesta = normalizar(env)
    storage.register_source(
        tenant_id=tenant_id,
        project_id=project_id,
        source=ingesta.source,
    )
    storage.upsert_entity(
        tenant_id=tenant_id,
        project_id=project_id,
        entity=ingesta.entity,
    )
    for claim in ingesta.claims:
        storage.record_claim(tenant_id=tenant_id, project_id=project_id, claim=claim)
    return ingesta


#: El modulo puro NO debe poder importar este. Se vigila con un test, no con
#: una convencion: si `observation.py` importara aqui, el modelo volveria a
#: tener la puerta al disco, y ese es el defecto que este modulo separa.
MODELO_PURO: Final[str] = "skillgraph.knowledge.observation"
