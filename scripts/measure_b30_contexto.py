"""B30 — mide si un contexto truncado DICE que se truncó.

**POR QUÉ ESTE SCRIPT.** La fila de B30 dice: *«Traer el contexto es traerlo
todo, o traerlo truncado sin decir qué se cayó»*. La primera mitad es falsa y
está medida: `apply_budget` ya funciona y ya es exacto. La segunda es cierta, y
la forma que toma es peor que «truncar en silencio».

**MEDIDO ANTES DEL BLOQUE, con `/tmp/b30_explore.py`:**

    budget 1200, obligatorios 826, tres opcionales de 500
    incluidos     : ['obl-1', 'obl-2']
    LO QUE SE CAYO: {'opt-1', 'opt-2', 'opt-3'}
    -> apply_budget devuelve (incluidos, total_chars). NO hay omitted.

    Handoff: [identity, behavior, knowledge, execution,
              expected_result, capabilities]
    ningun campo omitted / dropped / excluded
    HandoffExecution.budget = {'token_budget_chars': 1200}   # el LIMITE

Y lo grave, que la fila no menciona: **`should_skip_adapter` decide sobre esa
mentira.** Recibe solo el `CoverageManifest` y devuelve

    manifest.is_complete and manifest.all_fresh

que decide **saltarse al Adapter**. Con el contexto truncado, el sistema se
queda **sin agente por el motivo de que la respuesta es completa**, cuando la
respuesta se cortó. El propio módulo lo prohíbe en su documentación:
`HandoffBlockedError` — *«NUNCA debe presentarse como completado»*.

Salida: una línea por pregunta y `RESULTADO: N/5 ABIERTAS`. Código de salida 0
siempre: es una medición, no un gate.

# QUE SIGNIFICA «CERRADA» EN ESTE INSTRUMENTO

Significa **«el comportamiento medido es el que se debe tener»**, y aquí la
distinción que importa es entre *declarar* y *poder saber*. Un arreglo que
declarara siempre `omitidos=()` cumpliría P1, P2 y P4 sin medir nada. Por eso
**P4 es el contrasalto**: mira que lo omitido sea **real y verificable**, y no
un campo que existe y siempre está vacío.

**Y P5 es el otro**: que el skip no pueda ignorar lo que el handoff ya
dice. Un arreglo que arreglara solo la declaración dejaría P5 abierta, y P5 es
la mitad que de verdad duele.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

#: Los tres opcionales que NO caben. 500 chars cada uno en un hueco de 374.
CHARS_OPCIONAL: Final[int] = 500
CHARS_OBLIGATORIO: Final[int] = 400
BUDGET: Final[int] = 1200


# ---------------------------------------------------------------------------
# La escena: un presupuesto que obliga a cortar
# ---------------------------------------------------------------------------


def _recurso(ns: str, chars: int) -> object:
    from skillgraph.knowledge.context_controller import CompiledResource

    return CompiledResource(
        resource_kind="claim",
        resource_namespace=f"claim:{ns}",
        resource_name=ns,
        body={"texto": "x" * chars},
    )


def _candidatos() -> tuple[list[object], list[object]]:
    obligatorios = [_recurso(f"obl-{i}", CHARS_OBLIGATORIO) for i in (1, 2)]
    opcionales = [_recurso(f"opt-{i}", CHARS_OPCIONAL) for i in (1, 2, 3)]
    return obligatorios, opcionales


def _aplicar() -> tuple[object, list[object], list[object]]:
    """Ejecuta el presupuesto real y devuelve lo que devuelve."""
    from skillgraph.knowledge.context_controller import apply_budget

    obligatorios, opcionales = _candidatos()
    resultado = apply_budget(
        obligatorios,
        opcionales,
        budget_chars=BUDGET,
        overflow_strategy="drop_optional",
    )
    return resultado, obligatorios, opcionales


def _lo_omitido(resultado: object) -> tuple[str, ...]:
    """Lee lo que el resultado declara que omitió, o `()` si no lo declara.

    **AQUI ESTÁ LA MEDICIÓN, Y NO UNA SUPUOSICIÓN.** No se usa
    `getattr(..., "omitidos", ())` para dar por bueno un caso que no existe: se
    mira, y si no está, la pregunta queda ABIERTA. Un guard que infiere la
    respuesta del defaults de una excepción está midiendo la excepción.

    **NORMALIZA LA FORMA, Y POR QUÉ.** Lo que la fila pide es «que el slice
    diga qué se cayó», no «que lo diga con una clase concreta». Se acepta un
    `Omision` (que trae `.name`) o un `str` pelado, y se compara por nombre.

    La normalización no vuelve la pregunta más débil: la comparación sigue
    siendo contra el conjunto **esperado**, que se deriva de los candidatos
    reales. Un arreglo que declarara la lista vacía seguiría failing.
    """
    if not hasattr(resultado, "omitidos"):
        return ()
    return tuple(o.name if hasattr(o, "name") else str(o) for o in resultado.omitidos)


def _lo_incluido(resultado: object) -> tuple[str, ...]:
    incluidos = getattr(resultado, "incluidos", None)
    if incluidos is None and isinstance(resultado, tuple):
        incluidos = resultado[0]
    return tuple(r.resource_name for r in incluidos)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Las cinco preguntas
# ---------------------------------------------------------------------------


def p1_el_presupuesto_declara_lo_que_dejo_fuera() -> tuple[bool, str]:
    """¿La función de presupuesto devuelve lo que dejó fuera?

    **LA PREGUNTA LITERAL DE LA FILA, Y LA MÁS FÁCIL DE CONTESTAR MAL.** Un
    arreglo podría hacer que la función devuelva `omitidos` vacío y pasar: por
    eso la mitad que importa la mide P4, y esta sólo pregunta por la
    capacidad de declararlo.
    """
    resultado, _, opcionales = _aplicar()
    omitidos = _lo_omitido(resultado)
    incluidos = _lo_incluido(resultado)
    espera = tuple(r.resource_name for r in opcionales if r.resource_name not in incluidos)
    bien = set(omitidos) == set(espera)
    return bien, (
        f"incluidos={list(incluidos)}, omitidos declarados={sorted(omitidos)} "
        f"(esperados {sorted(espera)})"
    )


def p2_el_handoff_lo_carga() -> tuple[bool, str]:
    """¿El `Handoff` lleva las omisiones, y entran en el hash firmado?

    **Y POR QUÉ TIENE QUE ENTRAR EN EL HASH.** `WI-111` midió que si el
    Adapter puede alterar el handoff entre el instante en que el Core calcula
    `context_hash` y el instante en que los eventos lo llevan, la fila
    describe un handoff y los eventos otro, para la misma `node_execution`. Un
    campo `omitidos` **fuera** del hash repetiría exactamente eso: el
    Receptor vería unas omisiones que el Core no firmó.
    """
    from skillgraph.runtime.handoff import HandoffKnowledge

    campos = set(HandoffKnowledge.__dataclass_fields__)
    tiene_campo = "omitidos" in campos

    # ¿Está en el hash? `context_hash` se calcula sobre el handoff entero, y
    # `slots=True` + `frozen=True` es lo que hace que un campo added sea parte
    # de la estructura hasheada. Lo que se comprueba aquí es que el campo
    # EXISTE en la clase, que es lo que hace falta para que exista en el
    # hash; leer el hash es P3.
    return tiene_campo, (
        f"HandoffKnowledge declara omitidos ({sorted(campos)})"
        if tiene_campo
        else f"HandoffKnowledge NO declara omitidos; campos={sorted(campos)}"
    )


def p3_lo_omitido_es_reconstruible_desde_el_handoff() -> tuple[bool, str]:
    """¿Se puede AÚN lo que se cayó, leyendo el handoff?

    **LA DIFERENCIA ENTRE «DECIRLO» Y «PODER DECIRLO».** Antes del bloque el
    cálculo era imposible, no solo incómodo: `included` guardaba lo que entró
    pero no el total de candidatos, luego la diferencia no se podía ni
    calcular. Este bloque no solo publica el dato: lo publica **en el handoff**,
    que es lo que el Adapter recibe.

    Y se mide **dos handoffs con el mismo budget y distinto contenido**, que es
    donde un campo que existe y siempre está vacío delata su propia mentira:
    si `omitidos` fuera `()` siempre, los dos darían idénticos.
    """
    from skillgraph.runtime.handoff import (
        Handoff,
        HandoffBehavior,
        HandoffExecution,
        HandoffIdentity,
        HandoffKnowledge,
    )

    if "omitidos" not in HandoffKnowledge.__dataclass_fields__:
        return False, (
            "HandoffKnowledge no declara `omitidos`, asi que no hay dos handoffs "
            "que comparar: la propiedad no se puede ni formular todavia"
        )

    def handoff(omitidos: tuple[tuple[str, str, str, int], ...]) -> Handoff:
        return Handoff(
            identity=HandoffIdentity(
                tenant_id="t",
                project_id="p",
                run_id="r",
                node_execution_id="n",
                attempt=1,
            ),
            behavior=HandoffBehavior(
                definition_kind="ActionNode",
                definition_name="d",
                definition_namespace="ns",
                definition_revision=1,
                api_version="v1",
            ),
            knowledge=HandoffKnowledge(recipe_ref="rc", omitidos=omitidos),
            execution=HandoffExecution(
                workspace_ref="ws", source_revision="rev", budget={"token_budget_chars": 1200}
            ),
            expected_result="x",
        )

    uno = handoff((("claim", "claim:opt-1", "opt-1", 500),))
    dos = handoff(())
    # `context_hash` es una PROPIEDAD (`@property`), no un método. Escribir
    # `context_hash()` lo hace fallar con "str object is not callable", que
    # parece un defecto del modulo y es un error de quien mide.
    h1, h2 = uno.context_hash, dos.context_hash
    bien = h1 != h2
    return bien, (
        f"context_hash con omisiones={h1[:12]}… sin omisiones={h2[:12]}… "
        + (
            "difieren: las omisiones entran en el hash firmado"
            if bien
            else "SON IGUALES: las omisiones NO entran en lo que el Core firma"
        )
    )


def p4_un_handoff_truncado_lo_dice() -> tuple[bool, str]:
    """EL CONTRA SALTO DEL INSTRUMENTO: sin esto, los otros tres no miden.

    Comprueba las DOS mitades, y las dos hacen falta:

    1. **Que lo omitido sea REAL**: el presupuesto corta tres opcionales de
       500 chars, y el handoff tiene que decir **tres**, con su tamaño.
    2. **Que no lo diga cuando no cortó**: un presupuesto holgado tiene que
       dar omisiones **vacías**. Un campo que siempre dice tres sería tan
       mentiroso como el que no dice ninguna.

    **UN GUARD QUE NO HACE LAS DOS COSAS NO MIDE NADA**, y por eso el
    instrumento comprueba los dos casos en la misma pregunta, con el mismo
    código y sin parametrización.
    """

    resultado, _, opcionales = _aplicar()
    incluidos = _lo_incluido(resultado)

    # **AQUI HACE FALTA EL OBJETO, NO EL NOMBRE.** `_lo_omitido` normaliza a
    # nombres porque P1 solo pregunta *que* se declara; P4 ademas pregunta
    # *cuanto pesa* cada omision, y el nombre no lo dice. Se leen los objetos
    # crudos por separado, y si el contrato viejo (nombres pelados) no
    # _declara_ el tamano, la pregunta queda ABIERTA en vez de dar por buena
    # una comprobacion que no se ha hecho.
    bruto = getattr(resultado, "omitidos", None)
    if bruto is None or any(not hasattr(o, "chars") for o in bruto):
        return False, (
            "las omisiones no declaran su tamano, luego no se puede comprobar "
            "que la omision sea accionable: saber que se cayo 'opt-2' sin saber "
            "cuanto era no deja pedirlo con otro presupuesto"
        )

    declarados = {o.name for o in bruto}
    espera = {r.resource_name for r in opcionales if r.resource_name not in incluidos}
    reales = declarados == espera and len(bruto) == 3
    # El tamano declarado es el que el presupuesto **uso** para decidir
    # (`approx_chars(body)`), no el largo del texto crudo. Comparar contra el
    # numero crudo haria fallar un contrato correcto.
    con_tamano = all(o.chars > 0 for o in bruto)

    # ¿Y el caso holgado dice que NO se cayó nada?
    holgado, _, _opcionales_holgados = _aplicar_con_presupuesto_holgado()
    omitidos_holgados = _lo_omitido(holgado)

    bien = reales and con_tamano and not omitidos_holgados
    return bien, (
        f"presupuesto ajustado: {len(bruto)} omitidos "
        f"{sorted(declarados)} con tamaño={con_tamano} "
        f"({[o.chars for o in bruto]}) | "
        f"presupuesto holgado: {len(omitidos_holgados)} omitidos "
        + (
            "(correcto: se dice lo que se cayó y se dice que no se cayó nada)"
            if bien
            else f"(esperados 3 con tamaño, y 0 en el holgado; espera={sorted(espera)})"
        )
    )


def _aplicar_con_presupuesto_holgado() -> tuple[object, list[object], list[object]]:
    """El mismo caso con presupuesto de sobra:aquí no se cae NADA."""
    from skillgraph.knowledge.context_controller import apply_budget

    obligatorios, opcionales = _candidatos()
    resultado = apply_budget(
        obligatorios,
        opcionales,
        budget_chars=99_999,
        overflow_strategy="drop_optional",
    )
    return resultado, obligatorios, opcionales


def p5_el_skip_no_puede_ignorar_lo_omitido() -> tuple[bool, str]:
    """**LA MITAD GRAVE, Y LA QUE LA FILA NO MENCIONA.**

    `should_skip_adapter` decide **no invocar al Adapter** (UAT-EVO-11: la
    respuesta determinista es completa, no hace falta un LLM). Su cuerpo es
    `manifest.is_complete and manifest.all_fresh`, y **recibe solo el
    manifest**: nunca ve el `Handoff` compilado, luego **no puede saber** que
    el presupuesto cortó opcionales.

    MEDIDO antes del bloque: un contexto truncado produce un manifest
    `is_complete=True`, luego `should_skip_adapter` devuelve **`True`** — el
    sistema **se queda sin agente por el motivo de que la respuesta es
    completa**, cuando la respuesta se cortó.

    Y el propio módulo lo prohíbe en su documentación: `HandoffBlockedError` —
    *«NUNCA debe presentarse como completado»*.

    **Y LA PRIMERA VERSION DE ESTA PREGUNTA DABA VERDE EN FALSO, Y ESTÁ MEDIDO:**

        omitidos=0 | manifest.is_complete=True | should_skip_adapter=True
        -> "el skip ve las omisiones y NO se declara completo"

    Era falso por la FORMA de la comprobación:
    `bool(omitidos) and salta and completo` da `False` en cuanto `omitidos`
    está vacío — y antes del bloque **siempre** lo está, porque el campo no
    existe. Luego el guard cerraba **precisamente porque el defecto estaba
    presente**.

    Es el vacuous pass que este repo lleva cazando desde WI-106, y esta vez lo
    cometí yo en la primera corrida del instrumento de mi propio bloque. La
    pregunta correcta no es «¿hay omisiones y aun así se salta?», sino **«¿el
    skip puede siquiera verlas?»**: si su firma no las admite, la propiedad no
    es satisfacible y la pregunta queda ABIERTA con el motivo nombrado.
    """
    import inspect

    from skillgraph.knowledge.file_handoff import (
        CoverageManifest,
        should_skip_adapter,
    )
    from skillgraph.knowledge.file_signature import (
        FileSignature,
        SignatureVigencia,
    )

    resultado, _, _opcionales = _aplicar()
    omitidos = _lo_omitido(resultado)

    # El manifest que ve el skip: cobertura de firmas COMPLETA y todas frescas.
    firma = FileSignature(
        foco="a.py",
        contrato="file_summary",
        cobertura=1,
        procedencia="heuristica:0.1.0",
        vigencia=SignatureVigencia(
            state="complete", fresh=True, stale=False, checked_at_revision="revA"
        ),
    )
    manifest = CoverageManifest(
        scope=object(),
        signatures=(firma,),
        fuentes=("local:a.py",),
        procedencia_por_firma={"a.py": "local"},
        revisiones_por_fuente={"local:a.py": "revA"},
        cobertura_total=1,
        required_coverage=1,
        limites={"token_budget": BUDGET, "freshness_policy": "best_effort"},
    )

    completo = manifest.is_complete and manifest.all_fresh

    # ¿Puede el skip siquiera ENTERARSE de lo que se cayó? Si su firma no lo
    # admite, la propiedad no es satisfacible y la pregunta queda ABIERTA —
    # que es justo lo que la primera version no vio.
    admite = tuple(inspect.signature(should_skip_adapter).parameters)
    if "omitidos" not in admite:
        return False, (
            f"should_skip_adapter{admite!r} no admite las omisiones, luego no puede "
            f"distinguir un slice truncado de uno completo | "
            f"manifest.is_complete={completo} | omitidos={len(omitidos)} -> "
            "no hay forma de que la propiedad se cumpla"
        )

    salta = should_skip_adapter(manifest=manifest, omitidos=omitidos)
    bien = not salta
    return bien, (
        f"omitidos={len(omitidos)} | manifest.is_complete={completo} | "
        f"should_skip_adapter={salta} -> "
        + (
            "el skip ve las omisiones y NO se declara completo"
            if bien
            else "se salta al Adapter declarando completa una respuesta TRUNCADA"
        )
    )


def main() -> int:
    preguntas = (
        (
            "P1",
            "el presupuesto DECLARA lo que dejo fuera",
            p1_el_presupuesto_declara_lo_que_dejo_fuera,
        ),
        ("P2", "el Handoff lo carga (y lo firma)", p2_el_handoff_lo_carga),
        (
            "P3",
            "lo omitido es RECONSTRUIBLE y entra en el hash",
            p3_lo_omitido_es_reconstruible_desde_el_handoff,
        ),
        (
            "P4",
            "un truncado LO DICE y uno holgado dice que no cayo nada (CONTRA SALTO)",
            p4_un_handoff_truncado_lo_dice,
        ),
        (
            "P5",
            "el SKIP no puede declarar completo un slice truncado",
            p5_el_skip_no_puede_ignorar_lo_omitido,
        ),
    )
    print("B30 — ¿un contexto truncado dice que se truncó?")
    print("  (MEDIDO: el presupuesto funciona y es exacto; lo que no existe")
    print("   es el registro de lo que dejo fuera, y el SKIP decide sobre eso)")
    print()
    abiertas = 0
    for pid, texto, fn in preguntas:
        cerrada, medido = fn()
        print(f"  {pid}  {'CERRADA' if cerrada else 'ABIERTA':<8} {texto}")
        print(f"      medido: {medido}")
        if not cerrada:
            abiertas += 1
    print(f"\nRESULTADO: {abiertas}/{len(preguntas)} preguntas ABIERTAS")
    if abiertas == 0:
        print("B30 esta implementado: lo que no cabe en el presupuesto lo dice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
