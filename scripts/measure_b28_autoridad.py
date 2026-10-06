"""B28 — mide si un conflicto se puede resolver POR INTENCION y no por ranking.

**POR QUE ESTE SCRIPT.** La fila de B28 afirma dos cosas: que resolver un
conflicto «es un ranking global» y que «la respuesta correcta depende de para
que se pregunta». La primera es una accuses —una forma de hacerlo que seria un
error— y la segunda es la propiedad. Este script hace la pregunta que decide
cual de las dos es verdad en el codigo, y su salida es la evidencia.

Salida: una linea por pregunta y `RESULTADO: N/5 ABIERTAS`. Codigo de salida 0
siempre: es una medicion, no un gate.

# LO QUE ESTA ARMADO, Y ES LA MEDIDA MAS UTIL DEL INSTRUMENTO

La spec dice que este ranking fijo seria un error:

    runtime > tests > code > ADR > docs > human > agent

**MEDIDO: el repo ya tiene el eje para construir ese ranking, y no tiene nada
que diga en que orden.** `AssertionOrigin` (`core/runtime_types.py`) declara
cuatro valores —`observed`, `derived-deterministically`, `agent-inferred`,
`human-asserted`— con un docstring largo que explica que NO son un ranking, sino
«quien afirma». Y `SourceKind` declara cinco mas.

Es decir: la tentacion no es hipotetica. Los datos estan ahi, ordenarlos es
una linea, y el orden **depende de la pregunta**:

    ¿que status devolvio produccion?     -> observed > derived
    ¿que dependencia esta permitida?    -> human-asserted > derived

Por eso la propiedad que se mide en P2 no es «hay un ranking» sino **«el mismo
conflicto, con dos intenciones, elige afirmaciones DISTINTAS»**. Un bloque que
metiera un ranking fijo pasaria cualquier prueba que comprobara que se elige
alguien.

# QUE SIGNIFICA «CERRADA» EN ESTE INSTRUMENTO

Significa **«el comportamiento medido es el que se debe tener»**. Y hay una
distincion que aqui si importa y que B27 tuvo que explicitar: P1 estaba
«abierta» antes de B28 no porque faltara un `class`, sino porque la API que
resuelve **no tiene forma de recibir una intencion**, luego no hay nada que
dependa de ella.

P5 es el CONTRA SALTO, y sin el este instrumento solo sabe ponerse en rojo: un
resolver que devolviera TODAS las afirmaciones y no eligiera ninguna cerraria
P2 y P3 sin resolver nada. Ademas P5 exige que el conflicto que resuelve sea
REAL —si `conflicts_for` devolviera vacio, «determinista» se cumple en
vacio— y por eso lleva su propio contra contra salto.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Final

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

SUJETO: Final[str] = "file:a.py"


# ---------------------------------------------------------------------------
# El escenario: UN conflicto, dos intenciones, dos respuestas distintas
# ---------------------------------------------------------------------------


def _base(tmp: str) -> object:
    """Una base con el sujeto y dos fuentes de origen distinto.

    MEDIDO que hace falta mas de una: el `UNIQUE` de `claims` es
    `(subject_entity_id, predicate, source_id, checked_at_revision)`, luego dos
    afirmaciones opuestas solo coexisten si vienen de fuentes distintas. Es la
    misma mitad de B27 que quedo «cerrada a favor», y aqui es la que permite que
    haya algo que resolver.
    """
    from skillgraph.knowledge.graph import Entity, Source, source_id
    from skillgraph.platform.storage import Storage

    s = Storage(Path(tmp) / "x.sqlite")
    s.upsert_entity(
        tenant_id="t",
        project_id="p",
        entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
    )
    for sid in ("local:runtime.log", "local:adr-0042.md"):
        s.register_source(
            tenant_id="t",
            project_id="p",
            source=Source(
                source_id=source_id(sid),
                kind="local_file",
                content_hash="h",
                locator={"path": sid},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-06T00:00:00Z",
                freshness="current",
            ),
        )
    return s


def _claim(cid: str, valor: object, sid: str, origen: str, rev: str = "r1") -> object:
    """Una afirmacion con su `assertion_origin`, que es el eje que se rankea."""
    from skillgraph.knowledge.graph import Claim

    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="imports_module",
        object_literal=valor,
        source_id=sid,
        assertion_origin=origen,
        checked_at_revision=rev,
    )


def _conflicto_real() -> object:
    """El conflicto que P2 y P3 van a resolver: dos afirmaciones OPUESTAS.

    **POR QUE ESTAS DOS Y NO OTRAS.** `observed` («lo vi en produccion») frente
    a `human-asserted` («lo decidi yo, con un ADR»): son los dos extremos del
    eje, y un ranking global tiene que elegir entre ellos. Un conflicto de dos
    afirmaciones del mismo origen no distinguiria nada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim("c-observed", "sqlite3", "local:runtime.log", "observed"),
        )
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim("c-adr", "psycopg", "local:adr-0042.md", "human-asserted"),
        )
        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
        s.close()
    return conflictos[0] if conflictos else None


# ---------------------------------------------------------------------------
# Las cinco preguntas
# ---------------------------------------------------------------------------


def p1_la_intencion_es_vocabulario_cerrado() -> tuple[bool, str]:
    """¿La intencion es un ADT, o un string libre?

     **LA PREGUNTA QUE LA SPEC RESPONDE CON UN «NO» EXPRESO** (05-SPEC §3:
     *«No dejarlo como prompt libre en la policy»*). Un string libre seria
    Environ: cada quien escribiria la intencion como le pareciera, dos profiles
     con la misma intencion tendrian nombres distintos, y el sistema no podria
     ni detectar el error ni decir que dos consultas son la misma pregunta.

     MEDIDO antes del bloque: no existe ninguna intencion que una API pueda
     recibir, luego la pregunta no tiene donde apoyarse.
    """
    try:
        from skillgraph.knowledge.authority import query_intent
    except ImportError as exc:
        return False, f"no hay modulo de autoridad: {exc}"

    from skillgraph.core.errors import SkillGraphError

    try:
        query_intent("que_on_va_a_preguntar")
    except SkillGraphError as exc:
        bien = True
        medido = f"una intencion inventada se rechaza: {type(exc).__name__} code={exc.code}"
    else:
        bien = False
        medido = "una intencion inventada se acepta: el campo es un string libre"

    # Y que las de verdad se acepten, que es la otra mitad de «cerrada».
    from skillgraph.knowledge.authority import query_intent as qi

    declaradas = ("actual_behavior", "intended_behavior", "structural_fact")
    ok = all(qi(i) == i for i in declaradas)
    return bien and ok, medido + f"; y {len(declaradas)} declaradas si se aceptan: {ok}"


def p2_el_mismo_conflicto_resuelve_distinto() -> tuple[bool, str]:
    """**LA PROPIEDAD DEL BLOQUE.** Un conflicto, dos intenciones, dos ganado-
    res distintos.

    MEDIDO antes del bloque: **no hay nada que elegir**, luego menos encore
    elegir distinto. `conflicts_for` devuelve las afirmaciones y se detiene
    alli —que es exactamente lo que B27 dejo bien hecho, y que B28 NO toca.

    Y la contrasalto esta en que la P se execute sobre un conflicto REAL: si
    `conflicts_for` devolviera vacio, esta pregunta daria «no hay ganador que
    comparar» y habria que mirar el codigo para saber si es que el resolver no
    funciona o es que no hay conflicto.
    """
    conflicto = _conflicto_real()
    if conflicto is None:
        return False, "no hay conflicto real que resolver: el escenario no se construyo"

    try:
        from skillgraph.knowledge.authority import resolver
    except ImportError as exc:
        return (
            False,
            f"el conflicto existe ({len(conflicto.afirmaciones)} afirmaciones) pero no hay API: {exc}",
        )

    r_comportamiento = resolver(conflicto, intencion="actual_behavior", perfil=None)
    r_arquitectura = resolver(conflicto, intencion="intended_behavior", perfil=None)
    gano_a = tuple(c.claim_id for c in r_comportamiento.elegidas)
    gano_b = tuple(c.claim_id for c in r_arquitectura.elegidas)
    bien = bool(gano_a) and bool(gano_b) and gano_a != gano_b
    return bien, (
        f"actual_behavior -> {gano_a or 'nadie'}, "
        f"intended_behavior   -> {gano_b or 'nadie'} "
        f"({'distintos' if gano_a != gano_b else 'IGUALES: hay un ranking global'})"
    )


def p3_la_resolucion_es_explicable() -> tuple[bool, str]:
    """¿Se puede contestar «por que gana esta y pierde la otra»? (spec §8)

    **LO QUE PIDE LA SPEC, PALABRA POR PALABRA**: que claims compitieron, que
    policy se uso, que claims se eligieron, que evidencia los respalda, que se
    descartaron y por que.

    MEDIDO antes del bloque: nada de esto existe, y la ausencia no es un
    defecto de formato —es que **no hay resolucion**, luego no hay nada que
    explicar. Un `elegidas` sin `descartadas` seria la mitad exactamente: el
    sistema diria «esta gana» y quien preguntara no podria contradecirlo nunca.
    """
    conflicto = _conflicto_real()
    if conflicto is None:
        return False, "no hay conflicto real que resolver"

    try:
        from skillgraph.knowledge.authority import resolver
    except ImportError as exc:
        return False, f"no hay API que explique nada: {exc}"

    r = resolver(conflicto, intencion="actual_behavior", perfil=None)
    motivos = {d.motivo for d in r.descartadas}
    bien = (
        bool(r.elegidas)
        and bool(r.descartadas)
        and bool(r.perfil)
        and r.intencion == "actual_behavior"
        and len(motivos) == len({d.motivo for d in r.descartadas})
        and r.descartadas
    )
    return bien, (
        f"policy={r.perfil!r}, intencion={r.intencion!r}, "
        f"eligidas={len(r.elegidas)}, descartadas con motivo="
        f"{sorted(motivos) or 'NINGUNO'}"
    )


def p4_el_agente_no_cierra_el_conflicto() -> tuple[bool, str]:
    """Un claim `agent-inferred` puede, por si solo, cerrar el conflicto? (spec §7)

    **LA PREGUNTA DE SEGURIDAD DE LA SERIE, Y LA MAS FACIL DE MEDIR EN VACIO.**

    **EL ESCENARIO TIENE QUE PONER AL AGENTE PRIMERO, Y ESO NO ES UN DETALLE.**
    La primera version de esta pregunta usaba el perfil por defecto de
    `actual_behavior`, donde `human-asserted` esta por encima de
    `agent-inferred`. Ahi el agente pierde **por rango** aunque el guard este
    borrado, luego la pregunta contestaba «no» por una razon que no es la que
    vigila. MEDIDO por la sonda M2 del harness: poner el flag a `True` no
    abria ninguna pregunta, porque el agente seguia siendo el peor del ranking.

    Un guard medido en un escenario donde no puede cambiar el resultado no es un
    guard: es una asercion con codigo de seguridad. Este perfil pone al agente el
    PRIMERO a proposito, de modo que **la unica razon posible para que no gane
    sea el flag**.
    """

    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim("c-humano", "psycopg", "local:adr-0042.md", "human-asserted"),
        )
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_claim("c-agente", "sqlite3", "local:runtime.log", "agent-inferred"),
        )
        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
        s.close()

    if not conflictos:
        return False, "el escenario del guard no produjo conflicto"

    try:
        from skillgraph.knowledge.authority import AuthorityProfile, resolver
    except ImportError as exc:
        return False, f"nada impide que un agente cierre nada, porque no hay cierre: {exc}"

    # El agente va PRIMERO a proposito: si pierde, no es por rango.
    perfil = AuthorityProfile(
        name="agente-primero",
        intencion="actual_behavior",
        preferencia=("agent-inferred", "observed", "human-asserted"),
    )
    r = resolver(conflictos[0], intencion="actual_behavior", perfil=perfil)
    gano_el_agente = any(c.assertion_origin == "agent-inferred" for c in r.elegidas)
    bien = not gano_el_agente and any(
        d.motivo == "cerrado_por_agente_no_permitido" for d in r.descartadas
    )
    return bien, (
        "el agente NO cierra el conflicto aunque sea el primero del ranking; "
        f"gana={[c.claim_id for c in r.elegidas] or 'nadie'}, "
        f"motivos={[d.motivo for d in r.descartadas]}"
    )


def p5_la_resolucion_es_determinista() -> tuple[bool, str]:
    """EL CONTRA SALTO DEL INSTRUMENTO. Sin esto, los otros cuatro no miden.

    Comprueba tres cosas a la vez:

    1. **Que el conflicto sea real** (>=2 afirmaciones opuestas). Un
       `conflicts_for` vacio haria que «determinista» se cumpla en el vacio.
    2. **Que el resultado no dependa del ORDEN de entrada.** B27 garantiza que
       `afirmaciones` viene ordenado; si el resolver depende de ese orden,
       basta reordenar las tuplas para que responda distinto, y eso es un
       resolver que no sabe.
    3. **Que dos llamadas den lo mismo.** Un resolver con estado oculto es un
       resolver cuya segunda respuesta es otra pregunta.

    Sin P5, un resolver que devolviera TODAS las afirmaciones cerraria P2 y
    P3 sin resolver nada, y el bloque habria FABRICADO una capacidad.
    """
    conflicto = _conflicto_real()
    if conflicto is None:
        return False, "no hay conflicto real: P5 se cumple en el vacio y no mide nada"

    try:
        from skillgraph.knowledge.authority import resolver
    except ImportError as exc:
        return False, f"no hay API: {exc}"

    uno = resolver(conflicto, intencion="actual_behavior", perfil=None)
    dos = resolver(conflicto, intencion="actual_behavior", perfil=None)
    invertido = resolver(
        type(conflicto)(
            subject_entity_id=conflicto.subject_entity_id,
            predicate=conflicto.predicate,
            afirmaciones=tuple(reversed(conflicto.afirmaciones)),
        ),
        intencion="actual_behavior",
        perfil=None,
    )
    a = tuple(c.claim_id for c in uno.elegidas)
    b = tuple(c.claim_id for c in dos.elegidas)
    c_ = tuple(c.claim_id for c in invertido.elegidas)
    n = len(conflicto.afirmaciones)
    bien = n >= 2 and a == b == c_ and bool(a)
    return bien, (
        f"{n} afirmaciones que se contradicen; misma llamada -> {a} == {b}; "
        f"orden invertido -> {c_} ({'igual' if a == c_ else 'CAMBIA CON EL ORDEN'})"
    )


def main() -> int:
    preguntas = (
        ("P1", "la intencion es vocabulario cerrado", p1_la_intencion_es_vocabulario_cerrado),
        (
            "P2",
            "el mismo conflicto resuelve DISTINTO por intencion",
            p2_el_mismo_conflicto_resuelve_distinto,
        ),
        ("P3", "la resolucion es explicable", p3_la_resolucion_es_explicable),
        ("P4", "un agente no cierra el conflicto por si solo", p4_el_agente_no_cierra_el_conflicto),
        ("P5", "la resolucion es determinista (CONTRA SALTO)", p5_la_resolucion_es_determinista),
    )
    print("B28 — ¿resolver un conflicto depende de para que se pregunta?")
    print("  (MEDIDO: AssertionOrigin ya tiene 4 valores y nada dice en que")
    print("   orden. La tentacion del ranking global esta ARMADA, no es teorica)\n")
    abiertas = 0
    for pid, texto, fn in preguntas:
        cerrada, medido = fn()
        print(f"  {pid}  {'CERRADA' if cerrada else 'ABIERTA':<8} {texto}")
        print(f"      medido: {medido}")
        if not cerrada:
            abiertas += 1
    print(f"\nRESULTADO: {abiertas}/{len(preguntas)} preguntas ABIERTAS")
    if abiertas == 0:
        print("B28 esta implementado: la autoridad se decide por intencion y se explica.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
