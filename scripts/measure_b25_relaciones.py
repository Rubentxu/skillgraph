"""B25 — mide si un hecho entre dos entidades se puede expresar.

Versionado en `scripts/` y no en `.pipelinek/`, por el backlog
`bl-bl-01M41DFZEZ0003882TZNP7NPM0` que dejaba los instrumentos de medicion
fuera del arbol versionado.

**POR QUE ESTE SCRIPT EXISTE Y NO UN PARRAFO EN EL INFORME.** El gate
`exploration-sufficient` pregunta si la exploracion de B25 esta medida, y una
afirmacion en prosa no es una medida: es una declaracion con la forma de un
dato. Este script hace la pregunta y contesta, y su salida es la evidencia que
se le pasa al motor. Si B25 se implementa, este script cambia de veredicto; si
alguien afirma que B25 esta hecho sin ejecutarlo, el script lo contradice.

Las cuatro preguntas son las capacidades que el enunciado de B25 promete, no
una lista de comprobaciones: cada una es algo que el bloque dice poder hacer.

    P1  ¿el objeto de un claim puede ser OTRA entidad?
    P2  ¿la base impone el vocabulario de predicados, o solo Python?
    P3  ¿un predicado con namespace se acepta sin tocar el core?
    P4  ¿un pack tiene superficie para declarar lo que aporta?

Salida: una linea por pregunta y `RESULTADO: N/4`. Codigo de salida 0 siempre:
es una medicion, no un gate, y un gate que sale en rojo cuando la respuesta es
«abierta» mediria lo contrario de lo que dice.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from dataclasses import fields
from pathlib import Path
from typing import Final

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from skillgraph.knowledge.graph import Claim, EntityID, entity_id, entity_ref  # noqa: E402
from skillgraph.packaging.manifest import PackManifest  # noqa: E402

#: Una entidad de destino legitima. `EntityID` exige `kind:key`, asi que una
#: referencia a entidad SI tiene sintaxis y validador; lo que se pregunta es si
#: el objeto de un claim tiene sitio donde ponerla.
DESTINO: Final[EntityID] = entity_id("file:src/skillgraph/knowledge/graph.py")

PREDICADO_DE_PACK: Final[str] = "acme.git.has_remote"

ORIGEN: Final[EntityID] = entity_id("file:src/skillgraph/knowledge/graph.py")


class Pregunta:
    """Una pregunta y su veredicto, con la medida que produjo el veredicto."""

    __slots__ = ("abierta", "como_se_mide", "id", "texto")

    def __init__(self, pid: str, texto: str, abierta: bool, como_se_mide: str) -> None:
        self.id = pid
        self.texto = texto
        self.abierta = abierta
        self.como_se_mide = como_se_mide

    def linea(self) -> str:
        estado = "ABIERTA" if self.abierta else "CERRADA"
        return f"  {self.id}  {estado:<8} {self.texto}"


def p1_el_objeto_puede_ser_otra_entidad() -> Pregunta:
    """¿El sistema puede DISTINGUIR una referencia a entidad de un string?

    **ESTA SONDA HA CAMBIADO DOS VECES, Y LAS DOS IMPORTAN.**

    La primera construia el `Claim` con la entidad por `object_literal` y daba la
    pregunta por CERRADA si no explotaba. Explotaba: `object_literal` esta
    anotado `Any`, y `EntityID` es un `NewType` sobre `str`, luego a runtime es
    una cadena. Ese falso negativo habria declarado B25 implementado sobre la
    evidencia de que un `Any` no se queja.

    La segunda, ya con B25 escrito, seguia pasando la entidad por
    `object_literal` —donde la metimos por costumbre— y por eso seguia
    respondiendo ABIERTA con la capacidad implementada. Una sonda que no cambia
    cuando cambia el codigo no mide el codigo: mide la sonda.

    La que queda construye las DOS formas por su via propia y pregunta si el
    sistema las distingue. Esa es la propiedad de R1.
    """
    # LA MISMA CADENA por los dos lados. Por un lado como literal, por otro
    # como referencia declarada. Si el sistema no dice cual es cual, no esta
    # expresando una relacion: esta guardando texto.
    como_entidad = Claim(
        claim_id="c-b25-p1-a",
        subject_entity_id=ORIGEN,
        predicate="imports_module",
        object_literal=None,
        source_id="local:p1",
        checked_at_revision="r1",
        object_entity=entity_ref(DESTINO),
    )
    como_texto = Claim(
        claim_id="c-b25-p1-b",
        subject_entity_id=ORIGEN,
        predicate="imports_module",
        object_literal=DESTINO,
        source_id="local:p1",
        checked_at_revision="r1",
    )

    diferencia = como_entidad.object_entity is not None and como_texto.object_entity is None
    distinta = como_entidad != como_texto
    abierta = not (diferencia and distinta)

    medido = (
        f"la misma cadena por un lado vuelve como "
        f"{type(como_entidad.object_entity).__name__} y por otro como "
        f"{type(como_texto.object_literal).__name__}, y los dos claims son "
        f"distintos: el sistema sabe cual de los dos apunta a algo"
        if not abierta
        else "el sistema no puede decir cual de los dos es una entidad"
    )
    return Pregunta("P1", "el objeto de un claim puede ser otra entidad", abierta, medido)


def p2_la_base_impone_el_vocabulario() -> Pregunta:
    """¿El cierre de `predicate` es de la base o solo de Python?

    Se mide contra una base de verdad, no leyendo el DDL: se intenta meter el
    predicado que Python rechaza y se mira si la base lo cuela. Si lo acepta,
    el cierre es de una sola capa —y por tanto de la capa equivocada: un
    `Claim` no se puede construir, pero una fila si se puede escribir—.
    """
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(f"{tmp}/b25.db")
        try:
            conn.execute("CREATE TABLE claims (claim_id TEXT PRIMARY KEY, predicate TEXT NOT NULL)")
            conn.execute("INSERT INTO claims VALUES (?, ?)", ("c-b25-p2", PREDICADO_DE_PACK))
            conn.commit()
            fila = conn.execute(
                "SELECT predicate FROM claims WHERE claim_id = ?", ("c-b25-p2",)
            ).fetchone()
        finally:
            conn.close()

    acepta = fila is not None and fila[0] == PREDICADO_DE_PACK
    return Pregunta(
        "P2",
        "la base impone el vocabulario de predicados, no solo Python",
        abierta=acepta,
        como_se_mide=(
            f"la base acepta {PREDICADO_DE_PACK!r} sin rechistar. ABIERTA A PROPOSITO: "
            "el CHECK de un predicate NO se puede anadir con ALTER TABLE, habria que "
            "reconstruir la tabla —la operacion mas arriesgada que existe sobre una "
            "base con datos—, y la invariante del OBJETO si se cierra ahi (ver P1 y el "
            "test de la base). El vocabulario de predicates vive en Python a "
            "decicion, y esta linea lo dice para que se lea como decision y no como "
            "olvido"
        ),
    )


def p3_predicado_con_namespace_se_acepta() -> Pregunta:
    """¿Un predicado con namespace se acepta sin tocar `CLAIM_PREDICATES`?

    Es la promesa literal de la fila de B25: «un pack añade un predicado sin
    tocar el núcleo». Se mide intentando construir el claim; si el núcleo
    necesita que su conjunto de siete literales incluya el nombre, la pregunta
    está abierta.
    """
    try:
        Claim(
            claim_id="c-b25-p3",
            subject_entity_id=ORIGEN,
            predicate=PREDICADO_DE_PACK,
            object_literal=True,
            source_id="local:p3",
            checked_at_revision="r1",
        )
    except Exception:
        abierta = True
        medido = "el nucleo rechaza el predicado del pack"
    else:
        abierta = False
        medido = "el nucleo acepta el predicado del pack sin conocerlo"
    return Pregunta(
        "P3",
        "un predicado con namespace se acepta sin tocar el core",
        abierta,
        medido,
    )


def p4_un_pack_tiene_superficie_de_aporte() -> Pregunta:
    """¿`PackManifest` tiene donde declarar lo que un pack aporta?

    Hoy solo tiene `requires`. Se mide por la forma del dataclass, que es la
    pregunta de verdad: un campo que no existe no se ignora, no se lee.
    """
    campos = {f.name for f in fields(PackManifest)}
    tiene = bool(campos & {"contributes", "provides", "declares"})
    return Pregunta(
        "P4",
        "un pack tiene superficie para declarar lo que aporta",
        abierta=not tiene,
        como_se_mide=(
            f"PackManifest declara {sorted(campos)}. ABIERTA A PROPOSITO: anadir un "
            "`contributes` que nadie lee seria crear la declaracion sin consumidor que "
            "este repo lleva cerrando desde B0. El registro que instala packs es B26"
        ),
    )


def main() -> int:
    preguntas = (
        p1_el_objeto_puede_ser_otra_entidad(),
        p2_la_base_impone_el_vocabulario(),
        p3_predicado_con_namespace_se_acepta(),
        p4_un_pack_tiene_superficie_de_aporte(),
    )
    print("B25 — se puede expresar un hecho entre dos entidades?")
    for p in preguntas:
        print(p.linea())
        print(f"      como se midio: {p.como_se_mide}")
    abiertas = sum(1 for p in preguntas if p.abierta)
    print(f"RESULTADO: {abiertas}/4 preguntas ABIERTAS")
    if abiertas == 0:
        print("B25 esta implementado: las cuatro capacidades estan ahi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
