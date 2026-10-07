"""B29 — mide si un cambio a lo largo del tiempo se distingue de una contradiccion.

**POR QUE ESTE SCRIPT.** La fila de B29 dice: *«No se puede preguntar que se
sabia en una revision, ni como fue reemplazado»*. La primera mitad exagera —el
dato de revision esta en cada claim desde antes de esta serie— y la segunda es
cierta pero no es la que mas duele.

Lo que **si** duele, y MEDIDO antes de escribir nada (`/tmp/b29_explore.py`):

    filas en claims:   c-A "psycopg" @revA    c-B "sqlite3" @revB
    conflicts_for  ->  1 conflicto: [c-A, c-B]
    resolver       ->  gana NADIE

El sistema **responde «nadie gana» a algo que tiene respuesta definite en cada
instante**. En revA era `psycopg`; en revB es `sqlite3`. Las dos afirmaciones
estan ahi, con su revision, y aun asi no sabe.

Y la causa es precisa: `conflicts_for` agrupa por predicado y compara valores,
**sin mirar el tiempo**. Un hecho que CAMBIO se lee igual que un hecho que se
CONTRADICE. Es la consecuencia que ADR-0030 nombra textualmente: *«menos falsos
conflictos»*.

**Y POR QUE ES DE B29 Y NO DE B28.** B28 dio la politica de autoridad y la
aplico a lo que B27 le entrego. Lo que B27 entrego —conflict sets— no lleva
tiempo, porque no lo tenia. El sintoma (resolver dice «nadie») es de B28; la
causa (no hay ventanas) es de B29. Un bloque que arreglara solo el sintoma
tendria que filtrar por revision en el resolver, y entonces dejaria de poder
decir «estas dos afirmaciones se contradicen», que es verdad y que B28 prometio.

Salida: una linea por pregunta y `RESULTADO: N/5 ABIERTAS`. Codigo de salida 0
siempre: es una medicion, no un gate.

# QUE SIGNIFICA «CERRADA» EN ESTE INSTRUMENTO

Significa **«el comportamiento medido es el que se debe tener»**. Y aqui hay
una distincion que conviene no perder: un cambio en el tiempo **no deja de ser
un conflicto en todas partes**. Se deja de serlo en HEAD, donde el hecho viejo
caduco, y **sigue siendolo en la revision donde ambos eran ciertos a la vez**.
P5 mide las dos mitades, y sin la segunda, un arreglo que borrase todos los
conflictos pasaria.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Final

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

SUJETO: Final[str] = "file:a.py"
ORIGEN: Final[str] = "local:runtime.log"
SEGUNDA: Final[str] = "local:adr-0042.md"


# ---------------------------------------------------------------------------
# El escenario: el caso del GATE de la spec (06-SPEC §9)
# ---------------------------------------------------------------------------


def _base(tmp: str) -> object:
    """Una base con el sujeto y **dos** fuentes.

    **LAS DOS, Y NO UNA, Y POR QUE ESTA EN UN INSTRUMENTO QUE MIDE UNA COSA
    MAS.** P2 y P4 necesitan una sola fuente —el caso es un CAMBIO, no una
    discrepancia—, y P5 necesita dos para construir el solapamiento. MEDIDO al
    ejecutar: con una sola, la escena de P5 reventaba con `FOREIGN KEY
    constraint failed` al registrar la afirmacion de la segunda fuente.

    El fallo era del **instrumento** y no del codigo —lo delata que venia de
    `register_source`, no de la ventana—, pero un instrumento que revienta a
    mitad de la tercera pregunta no mide: es la misma clase de hueco que B22
    cerro con «cada predicado da su veredicto aunque lance». Aqui no se
    anything: la escena completa levanta las dos fuentes de entrada y cada
    pregunta usa las que necesita.
    """
    from skillgraph.knowledge.graph import Entity, Source, source_id
    from skillgraph.platform.storage import Storage

    s = Storage(Path(tmp) / "x.sqlite")
    s.upsert_entity(
        tenant_id="t",
        project_id="p",
        entity=Entity(entity_id=SUJETO, kind="file", stable_key="a.py"),
    )
    for sid in (ORIGEN, SEGUNDA):
        s.register_source(
            tenant_id="t",
            project_id="p",
            source=Source(
                source_id=source_id(sid),
                kind="local_file",
                content_hash="h",
                locator={},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-06T00:00:00Z",
                freshness="current",
            ),
        )
    return s


def _claim(cid: str, valor: str, rev: str) -> object:
    from skillgraph.knowledge.graph import Claim

    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="imports_module",
        object_literal=valor,
        source_id=ORIGEN,
        assertion_origin="observed",
        checked_at_revision=rev,
    )


def _tras_el_cambio() -> object:
    """El gate de 06-SPEC §9: commit A dice `calls B`, commit B dice `calls C`."""
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c-A", "psycopg", "revA"))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c-B", "sqlite3", "revB"))
        return s


# ---------------------------------------------------------------------------
# Las cinco preguntas
# ---------------------------------------------------------------------------


def p1_hay_ventanas_de_vigencia() -> tuple[bool, str]:
    """¿Un claim declara DESDE CUANDO y HASTA CUANDO es cierto?

    **LA DISTINCION DE LA SPEC 06-SPEC §1, Y ES EL CORAZON DEL BLOQUE.** Hay dos
    ejes temporales y no se pueden confundir:

        valid time  -> cuando es cierto el hecho en el sistema observado
        knowledge time -> cuando SkillGraph lo observo

    El segundo YA EXISTE: es `checked_at_revision`, y esta en `claims` desde el
    principio. **Lo que no existe es el primero.** MEDIDO: `claims` no tiene
    `valid_from_revision` ni `valid_until_revision`.

    Y por eso la confusion no es academica: sin ventanas, «lo que se observo en
    revB» y «lo que es cierto en revB» son la misma frase, y el sistema no puede
    decir si un hecho que cambio lo estaba diciendo.
    """
    from skillgraph.knowledge.graph import Claim

    campos = {f.name for f in Claim.__dataclass_fields__.values()}
    tiene = {"valid_from_revision", "valid_until_revision"} <= campos
    return tiene, (
        "Claim declara valid_from_revision y valid_until_revision"
        if tiene
        else f"Claim declara {sorted(campos)}: NO hay ventana de vigencia, "
        "solo checked_at_revision (knowledge time, no valid time)"
    )


def p2_hay_cadena_de_supersession() -> tuple[bool, str]:
    """¿Se puede saber que claim REEMPLAZO a cual? (spec §2)

    **MEDIDO ANTES DEL BLOQUE: NO.** `claims` no tiene `supersedes_claim_id`, y
    no hay ninguna columna ni funcion que diga que `c-B` sustituyo a `c-A`.

    Lo que hay son dos filas con dos revisiones distintas, y nada mas. Podrian
    ser un cambio, o podrian ser dos herramientas que discrepan, y el sistema no
    puede distinguirlo porque **la unica diferencia esta en un campo que nadie
    consulta**.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c-A", "psycopg", "revA"))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c-B", "sqlite3", "revB"))
        columnas = {f[1] for f in s._conn.execute("PRAGMA table_info(claims)")}
        s.close()
    tiene = "supersedes_claim_id" in columnas
    return tiene, (
        "claims.supersedes_claim_id existe"
        if tiene
        else f"claims NO tiene supersedes_claim_id ({len(columnas)} columnas); "
        "nada dice que c-B haya sustituido a c-A"
    )


def p3_se_puede_preguntar_por_revision() -> tuple[bool, str]:
    """¿Hay una consulta que responda «que sabiamos en la revision R»? (spec §3)

    **LA FILA DECIA QUE NO SE PUEDE, Y ESO EXAGERA A FAVOR.** El dato esta:
    `checked_at_revision` esta en cada fila desde antes de esta serie. Lo que no
    hay es una **consulta**, luego que se pueda con SQL a mano no cuenta: la
    fila pide que se pueda PREGUNTAR.

    **Y LA PRIMERA VERSION DE ESTA PREGUNTA ESTABA MAL.** Buscaba
    `claims_at_revision` como atributo del **modulo**, cuando la consulta esta
    en la **clase** `Storage`. Un guard que mira donde no esta no esta roto:
    esta midiendo otra cosa, y da `0/5` con el bloque entero implementado. Es
    la misma clase de error que WI-112 agrupo como «un guard por lectura», y
    que en B28 se cazo con el docstring de `now_iso`.
    """
    from skillgraph.platform.storage import Storage

    metodos = [m for m in dir(Storage) if "revision" in m and not m.startswith("_")]
    tiene = "claims_at_revision" in metodos
    return tiene, (
        f"Storage expone {metodos}"
        if tiene
        else "Storage no expone ninguna consulta por revision: el dato esta, la pregunta no"
    )


def p4_un_cambio_no_es_un_conflicto() -> tuple[bool, str]:
    """**EL DEFECTO REAL.** Un hecho que CAMBIO, ¿se reporta como contradiccion?

    MEDIDO antes del bloque: **si**, y de la forma mas cara posible. Dos
    afirmaciones de la MISMA fuente en revisiones consecutivas:

        conflicts_for  ->  1 conflicto: [c-A, c-B]
        resolver       ->  gana NADIE

    «Gana nadie» es la respuesta a *«¿cual de las dos creo?»* cuando las dos
    eran ciertas y en instantes distintos. El sistema tiene la respuesta
    correcta —revB dice `sqlite3`— y no la puede dar.

    Y el contrasalto esta en que esto **NO** se arregla borrando el conflicto:
    se arregla porque el hecho viejo **caduca**. Ver P5.
    """
    s = _tras_el_cambio()
    conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id=SUJETO)
    s.close()
    bien = len(conflictos) == 0
    return bien, (
        f"un cambio entre revA y revB da {len(conflictos)} conflicto(s) "
        + ("(correcto: el hecho viejo caduco)" if bien else "(se lee como contradiccion)")
    )


def p5_las_ventanas_disjuntas_no_son_conflicto() -> tuple[bool, str]:
    """EL CONTRA SALTO DEL INSTRUMENTO. Sin esto, los otros cuatro no miden.

    Comprueba las TRES mitades, y las tres hacen falta:

    1. **Que las ventanas DISJUNTAS no sean conflicto**: en `revA` solo hay
       `c-A`, luego no hay nadie con quien oponerse, y eso NO es un conflicto.
       Es la propiedad entera del bloque.
    2. **Que las ventanas SOLAPADAS SI lo sean**: `c-B` y `c-Z` son de fuentes
       DISTINTAS y dicen cosas distintas EN LA MISMA revision. B29 no puede
       comprar «cero conflictos» apagando el detector.
    3. **Que se compare el CONJUNTO, no el numero.** `HEAD` y `revB` dan los
       MISMOS dos claims —en los dos, `c-A` ya caduco—, luego comparar
       numeros no distinguiria un filtro de ventana de uno que no filtra nada.
       La sonda que distingue mira que en `revA` NO aparece `c-B`, que es lo
       que un filtro ausente haria aparecer.

    **Y LOS VALORES ESPERADOS ESTAN MEDIDOS, NO ADIVINADOS.** La primera
    version de esta pregunta esperaba `HEAD -> 1, revA -> 1, revB -> 2`, y lo
    escribi ANTES de implementar. Los valores correctos los dao los conjuntos:
    `revA` no puede tener conflicto porque en `revA` solo una fuente hablo.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = _base(tmp)
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c-A", "psycopg", "revA"))
        s.record_claim(tenant_id="t", project_id="p", claim=_claim("c-B", "sqlite3", "revB"))
        s.record_claim(
            tenant_id="t",
            project_id="p",
            claim=_afirmacion_traidora("c-Z", "mysql"),
        )
        head = _ids_en_conflicto(s, None)
        rev_a = _ids_en_conflicto(s, "revA")
        rev_b = _ids_en_conflicto(s, "revB")
        s.close()

    bien = head == {"c-B", "c-Z"} and rev_a == set() and rev_b == {"c-B", "c-Z"}
    return bien, (
        f"HEAD -> {sorted(head) or 'ninguno'}, "
        f"revA -> {sorted(rev_a) or 'ninguno'}, "
        f"revB -> {sorted(rev_b) or 'ninguno'}"
        + ("" if bien else "  (se esperaba c-B+c-Z en HEAD y revB, y NADA en revA)")
    )


def _ids_en_conflicto(s: object, revision: str | None) -> set[str]:
    """Los claim_ids en conflicto en `revision`, como conjunto.

    **UN CONJUNTO Y NO UN NUMERO, Y POR QUE.** `HEAD` y `revB` dan el MISMO
    numero: en los dos, `c-A` ya caduco. Compararlos por cantidad no distinguiria
    un filtro de ventana de uno que filtra por otra cosa, asi que se comparan
    los identificadores, que si distinguen.
    """
    conflictos = s.conflicts_for(
        tenant_id="t",
        project_id="p",
        subject_entity_id=SUJETO,
        revision=revision,
    )
    return {cid for c in conflictos for cid in c.claim_ids}


def _afirmacion_traidora(cid: str, valor: str) -> object:
    """La segunda fuente: misma revision, otra fuente, otro valor."""
    from skillgraph.knowledge.graph import Claim

    return Claim(
        claim_id=cid,
        subject_entity_id=SUJETO,
        predicate="imports_module",
        object_literal=valor,
        source_id=SEGUNDA,
        assertion_origin="observed",
        checked_at_revision="revB",
    )


def main() -> int:
    preguntas = (
        (
            "P1",
            "hay ventanas de vigencia (valid time, no knowledge time)",
            p1_hay_ventanas_de_vigencia,
        ),
        ("P2", "hay cadena de supersession", p2_hay_cadena_de_supersession),
        ("P3", "se puede preguntar por una revision", p3_se_puede_preguntar_por_revision),
        ("P4", "un CAMBIO no se lee como contradiccion", p4_un_cambio_no_es_un_conflicto),
        (
            "P5",
            "disjuntas NO son conflicto y solapadas SI (CONTRA SALTO)",
            p5_las_ventanas_disjuntas_no_son_conflicto,
        ),
    )
    print("B29 — ¿un cambio en el tiempo se distingue de una contradiccion?")
    print("  (MEDIDO: resolver responde «gana NADIE» a dos hechos que fueron")
    print("   ciertos en instantes distintos. El dato esta; la pregunta, no)")
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
        print("B29 esta implementado: lo que caduco ya no contradice a lo que sigue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
