"""B35 — la DECISION de conflicto, fuera del componente que escribe.

**POR QUE ESTA PIEZA VIVE SOLA, MEDIDO.** `knowledge_claims.py` estaba en el
limite del ratchet arquitectónico —el umbral de god module es 800 LoC— y las
decisiones de B35 lo pasaron de ~810 a **901**. B35 lo hizo crecer sin querer,
y la respuesta correcta no es bajar el suelo: el ratchet dice, literalmente,
que «cada propiedad que llega a cero se queda en cero». Se arregla
extrayendo, y esta es la pieza que mas crecio, porque es donde vive la
semantica de `conflicto` que B35 cambio.

Y moverla no es solo una cuenta de lineas: es que `_registro` **no toca la
base**. Toma lo que el motor ya decidio —la fila previa y si el INSERT entro—
y responde una sola pregunta. Dejarla dentro del componente que escribe
mezcla dos asuntos con refrigeratedores distintos: uno es COMO se escribe y
otro es QUE SIGNIFICA lo que se escribio. La segunda pregunta se puede
cambiar sin tocar la primera, y despues de B35 cambio: antes `conflicto` se
deducía de comparar valores, y ahora lo decide el `UNIQUE`.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from skillgraph.knowledge.graph import Claim, ClaimRecorded

__all__ = ["registro_de_escritura"]


def registro_de_escritura(
    claim: Claim,
    previo: sqlite3.Row | None,
    *,
    insertado: bool,
) -> ClaimRecorded:
    """Traduce la fila previa a `ClaimRecorded`, y dice si hubo conflicto.

    **B35: `conflicto` YA NO SE DEDUCE DE LA COMPARACION, LO DICE EL MOTOR.**
    La tabla de tres estados de abajo la sostengo B27, y el tercero lo declara
    `ADR-0035` con la migracion `0008`: el `UNIQUE` de `claims` lleva el objeto,
    luego dos hechos ciertos sobre el mismo sujeto, predicado, fuente y
    revision **caben los dos** y el `UNIQUE` no rechaza ninguno. Antes esta
    funcion contestaba «hubo conflicto» comparando valores, y contestaba bien
    mientras el `UNIQUE` y la comparacion decian lo mismo — que es justo lo que
    `0008` dejo de ser cierto.

    **POR QUE NO SE ARREGLA AÑADIENDO EL OBJETO A LA CONSULTA PREVIA.** MEDIDO:
    se hizo, y es PEOR. La consulta previa solo encuentra entonces filas con el
    MISMO objeto, luego `previo_valor != intento_valor` es siempre `False` y
    `conflicto` se queda **permanentemente en `False`**. Una señal muerta es
    peor que una falsa: la falsa molesta y la muerta deja de avisar, y nadie lo
    nota hasta que un conflicto real pasa sin decir nada. Es la quinta vez que
    sale este defecto de fondo en el repo —un guard que mide la mitad de una
    propiedad y da verde porque esa mitad esta bien— y por eso el test de B35
    mide `conflictos`, y no filas.

    **`insertado` es la respuesta del motor, no una reconstruccion.** Con
    `INSERT OR IGNORE` no hay excepcion que capturar: se calla. `rowcount == 0`
    es lo unico que dice si la fila entro.

    **Y LA CONSULTA PREVIA SE QUEDA, porque B27 PIDIO ALGO MAS QUE EL SI O NO.**
    Quien recibe el aviso necesita saber QUE habia antes y QUE se intento, para
    poder decidir si lo que toca es resolver, superseder o nada. Esa pregunta no
    la responde el `UNIQUE` y por eso la consulta no se borra: lo que cambia es
    que ya no DECIDE, solo INFORMA.

    **LA DISTINCION SIGUE SIENDO DE TRES ESTADOS, Y HAY UN CUARTO:**

        no habia nada        -> se escribe, NO es conflicto
        habia lo MISMO      -> idempotente, NO es conflicto
        habia OTRA COSA     -> el `UNIQUE` rechaza el INSERT: CONFLICTO

    y el que `0008` creo:

        habia OTRA COSA y el `UNIQUE` la ADMITE
        (`imports_module='os'` y `imports_module='sys'`)
                              -> se escribe, NO es conflicto

    El segundo estado es el que hace que esto **no rompa la idempotencia de
    B26**. Si reingerir lo mismo se reportara como conflicto, `ingerir` dos
    veces dejaria de ser una operacion inocua y todo el bloque anterior se
    desharia para tapar un defecto que no es un defecto. MEDIDO, no supuesto:
    es el primer test que pasa en verde de este fichero, y pasa precisamente
    porque los tres estados estan separados.

    **Y LAS DOS CONDICIONES JUNTAS, PORQUE CON UNA SOLA LA SEÑAL SE MUERE.**
    MEDIDO, las dos formas de quedarse solo con una:

    ```
    solo `not insertado`          -> MEDIDO: el estado 2 (reingerir lo MISMO)
                                      daba conflicto=True, y con eso B26
                                      deja de ser idempotente
    solo `previo_valor != intento`-> es el estado de antes de B35, que hacia
                                      `imports_module='sys'` parecer un
                                      conflicto con `'os'`
    ```

    Juntas dicen una sola frase, y es la que B27 queria: **tu escritura se
    perdio, y se perdio porque estabas diciendo otra cosa**. Si se perdio y
    decias lo mismo, no se perdio nada — hay fila, con el mismo contenido— y
    no hay nada que avisar. Si no se perdio nada, no hay conflicto, por muy
    distinta que sea la frase.

    **Y LA SEÑAL NO MUERE.** Con `0008`, el `UNIQUE` rechaza el INSERT solo
    cuando coincide la tupla natural COMPLETA —que incluye el objeto— y eso
    implica que el valor era el mismo, luego la comparacion anula el aviso. Es
    decir: tras `0008`, `conflicto` solo puede ser `True` cuando el `UNIQUE`
    rechaza por la **clave primaria** —dos afirmaciones distintas con el mismo
    `claim_id`—, que es la unica colision que significa «no se escribio lo
    que dijiste». Se declara aqui porque es un caso al que nadie llega por
    `normalizar` (que deriva el `claim_id` del contenido) y por eso no lo
    cubre ningun camino de la ingesta: lo cubre quien construya el `Claim` a
    mano.

    `valor_previo` se devuelve DESERIALIZADO, no como el string crudo de la
    base: quien recibe el aviso necesita comparar `true` con `false`, no
    `'true'` con `'false'`.
    """

    # **NO HAY RETORTO TEMPRANO CUANDO NO HAY FILA PREVIA, Y ANTES SI LO HABIA.**
    # MEDIDO: con `previo is None` se devolvia `conflicto=False` sin mirar
    # `insertado`, y eso hacia que el `UNIQUE` que rechaza por la **clave
    # primaria** —dos afirmaciones distintas con el mismo `claim_id`— pasara
    # sin avisar. Es decir: se perdia una escritura y el que escribia no se
    # enteraba, que es exactamente el defecto que B27 abrio en su primer test.
    #
    # Y es el caso que hace que la senal NO ESTE MUERTA. Con `0008`, el
    # `UNIQUE` de la tupla natural —que ahora incluye el objeto— solo rechaza
    # cuando el valor era el mismo, luego ahi no hay conflicto que avisar. La
    # unica colision que significa «no se escribio lo que dijiste» es la clave
    # primaria, y no la puede encontrar una consulta por tupla natural.
    if previo is None:
        return ClaimRecorded(claim_id=claim.claim_id, conflicto=not insertado)

    ref_previo = previo["object_entity_id"]
    if ref_previo:
        previo_valor: Any = {"kind": "entity", "entity_id": ref_previo}
    else:
        try:
            previo_valor = json.loads(previo["object_literal_json"])
        except (TypeError, ValueError):
            previo_valor = previo["object_literal_json"]

    if claim.object_entity is not None:
        intento_valor: Any = {"kind": "entity", "entity_id": claim.object_entity.entity_id}
    else:
        intento_valor = claim.object_literal

    return ClaimRecorded(
        claim_id=claim.claim_id,
        conflicto=(not insertado) and previo_valor != intento_valor,
        valor_previo=previo_valor,
        valor_intento=intento_valor,
    )
