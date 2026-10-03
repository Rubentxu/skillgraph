#!/usr/bin/env python3
"""Medidor del bloque B5 — Graph Diff Gate.

Salida 1 = el hueco esta ABIERTO. Salida 0 = ya no esta.

No enumera clases: DERIVA lo que hay del arbol y de los simbolos reales.
Una lista escrita en el propio medidor seria el guard que compara contra
su propia copia, el error de WI-106, y daria verde el dia que la verdad
se mueva.

Que mide, y por que cada pregunta:

  P1  ¿existe una representacion COMPARABLE de un cambio estructural?
      El roadmap dice «que toda evolucion estructural significativa tenga
      una representacion comparable». Sin un tipo que represente el
      cambio, no hay nada comparable: hay un parche.

  P2  ¿el parche esta TIPADO?
      `operations: tuple[object, ...]` no dice quekind de operacion es
      cada elemento. Un gate semantico que quisiera preguntar «¿esto
      invalida el nodo X?» no tendria nada que mirar.

  P3  ¿existe el paso DIFF entre propuesta y politica?
      El gate de B5 es `Proposal -> Diff -> Policy -> Decision ->
      Evidence -> Apply`. Si el `Diff` no esta, la secuencia es
      `Proposal -> Policy -> ...` y el diff no es una etapa: es un
      detalle de la politica.

  P4  ¿el diff es SEMANTICO y no un diff de YAML?
      El roadmap lo dice literalmente: «no un diff de YAML». Se mide
      buscando si las operaciones del parche setipan por su efecto
      sobre el grafo (nodo, relacion, capability, policy, budget,
      priority, evidencia) o si son texto.

  P5  ¿el diff responde a las 7 preguntas que el roadmap le exige?
      que cambia, por que, que evidencia lo justifica, que coste anade,
      que capacidades exige, que nodos invalida, si es reversible.
      Cada una necesita un dato que exista en el tipo.

  P6  ¿existen las CUATRO VISTAS del mismo sistema?
      Execution, Knowledge, Decision/Evidence y Capability/Control. El
      roadmap dice que no son cuatro bases de datos sino cuatro
      PROYECCIONES TIPADAS sobre recursos y relaciones comunes. Sin las
      cuatro no hay sobre que proyectar, y sin proyeccion no hay diff
      que sea semantico y no textual.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

# Las preguntas del roadmap, escritas por el operador. Se declaran AQUI y
# no se deducen del arbol, porque la fuente de verdad de la PREGUNTA es
# ROADMAP.md y no el codigo: el codigo se deduce, la pregunta no.
PREGUNTAS_DIFF = (
    "que cambia",
    "por que",
    "que evidencia lo justifica",
    "que coste anade",
    "que capacidades exige",
    "que nodos invalida",
    "si es reversible",
)

VISTAS_GRAPH = (
    "ExecutionGraph",
    "KnowledgeGraph",
    "DecisionEvidenceGraph",
    "CapabilityControlGraph",
)


@dataclass(frozen=True, slots=True)
class Hallazgo:
    """Una pregunta del bloque y lo que el arbol responde de verdad.

    `en_alcance` distingue lo que este bloque cierra de lo que solo
    REGISTRA. P6 —las cuatro vistas— esta fuera de alcance a proposito
    y sigue abierta; que siga visible en la salida es lo que la hace
    deuda y no un olvido. El codigo de salida lo decide el alcance,
    nunca el olvido: si una pregunta fuera de alcance hiciera bajar el
    veredicto, apagar este bloque seria tapar un hueco, no cerrarlo.
    """

    clave: str
    pregunta: str
    abierta: bool
    detalle: str
    en_alcance: bool = True


def _modulos() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _arbol() -> ast.Module:
    # Un solo arbol sintetico de todo `src/`. La alternativa —parsear cada
    # fichero y descartar— haria que un simbolo de un modulo-shadow no se
    # viera nunca, que es como se pierden los hallazgos.
    cuerpo = "\n".join(p.read_text(encoding="utf-8") for p in _modulos())
    return ast.parse(cuerpo)


def _clases_por_fichero() -> dict[Path, list[ast.ClassDef]]:
    """Clase -> fichero de origen, parseando de verdad.

    El atributo se pone en el nodo, no en una tabla aparte: una tabla
    aparte puede desincronizarse del arbol, y un medidor que miente
    sobre su propia fuente no mide nada.
    """
    salida: dict[Path, list[ast.ClassDef]] = {}
    for ruta in _modulos():
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        clases = [n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef)]
        for c in clases:
            c.fichero = ruta  # type: ignore[attr-defined]
        if clases:
            salida[ruta] = clases
    return salida


def _clases(desde_fichero: dict[Path, list[ast.ClassDef]]) -> dict[str, list[ast.ClassDef]]:
    salida: dict[str, list[ast.ClassDef]] = {}
    for clases in desde_fichero.values():
        for c in clases:
            salida.setdefault(c.name, []).append(c)
    return salida


def _campos(clase: ast.ClassDef) -> dict[str, ast.expr]:
    campos: dict[str, ast.expr] = {}
    for stmt in clase.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            campos[stmt.target.id] = stmt.annotation
    return campos


def _texto(anotacion: ast.expr) -> str:
    return ast.unparse(anotacion)


def p1_existe_representacion_comparable(clases: dict[str, list[ast.ClassDef]]) -> Hallazgo:
    """Un tipo solo cuenta como diff de GRAFO si declara sobre que opera.

    La primera version de esta pregunta buscaba 'diff' o 'change' en el
    NOMBRE y devolvio CERRADO porque existe `ChangedFile`. `ChangedFile`
    es un cambio de fichero de git —`path`, `old_blob_sha`,
    `new_blob_sha`— y no tiene nada que ver con un grafo. Un predicado
    que acepta de mas no mide: da verde falso, que es el peor resultado
    que puede dar un medidor.

    Por eso el nombre ya no basta: el tipo tiene que declarar ALGO del
    vocabulario del grafo (nodo, relacion, arista, transicion) en sus
    campos, o vivir en el modulo que gobierna el grafo.
    """
    vocabulario_grafo = ("node", "relacion", "relation", "edge", "transition", "arista")
    candidatas: list[str] = []
    for nombre, definiciones in clases.items():
        for clase in definiciones:
            if "diff" not in nombre.lower() and "change" not in nombre.lower():
                continue
            campos = {n.lower() for n in _campos(clase)}
            toca_grafo = any(any(v in c for v in vocabulario_grafo) for c in campos)
            en_gobernanza = "governance" in getattr(clase, "fichero", Path(".")).parts
            if toca_grafo or en_gobernanza:
                candidatas.append(nombre)
                break
    return Hallazgo(
        "P1",
        "¿existe un tipo que represente un cambio estructural comparable?",
        not candidatas,
        f"tipos diff DE GRAFO: {sorted(set(candidatas)) or 'NINGUNO'}. "
        f"(Se excluyen los que no declaran nada del grafo: un cambio de "
        f"fichero de git no es un cambio de grafo.)",
    )


def p2_parche_tipado(clases: dict[str, list[ast.ClassDef]]) -> Hallazgo:
    """`operations` esta anotado, y la anotacion dice algo.

    `tuple[object, ...]` NO dice nada: `object` es la anotacion que
    admite cualquier valor, luego no restringe nada. Se mide si la
    anotacion menciona `object` o `Any` como elemento de la tupla.
    """
    clase = next(
        (c for cs in clases.values() for c in cs if c.name == "GraphExpansionProposal"),
        None,
    )
    if clase is None:
        return Hallazgo(
            "P2",
            "¿el parche de la propuesta esta tipado?",
            True,
            "NO EXISTE GraphExpansionProposal",
        )
    anot = _texto(_campos(clase).get("operations", ast.Constant(value="?")))
    sin_tipo = "object" in anot or "Any" in anot
    ops = sorted(n for n in clases if n.startswith(("Add", "Remove", "Update", "Set", "Change")))
    return Hallazgo(
        "P2",
        "¿el parche de la propuesta esta tipado?",
        sin_tipo,
        f"GraphExpansionProposal.operations: {anot}; "
        f"clases de operacion que existen: {ops or 'NINGUNA'}",
    )


def p3_paso_diff_entre_propuesta_y_politica(
    desde_fichero: dict[Path, list[ast.ClassDef]],
) -> Hallazgo:
    """La secuencia del gate: ¿existe el paso `Diff` y lo USA `apply`?

    **POR QUE BUSCA EN `governance/` Y NO EN UN FICHERO.** La segunda
    version buscaba funciones de diff solo en `graph_expansion.py` y dio
    ABIERTO despues de que el codigo quedara bien: la funcion se mudó a
    `graph_diff.py` porque habla de diffs, no de expansiones, y un
    predicado que busca la funcion en un fichero mide la UBICACION, no la
    propiedad. Mudar el codigo para que el medidor se quedara tranquilo
    habria sido mudarlo al sitio equivocado a proposito.

    **Y POR QUE BUSCA EL CALL-SITE.** Que exista una funcion de diff no
    pone el `Diff` en la secuencia: lo pone que `apply_expansion` la
    llame. Es *conectar != contener* (WI-102), y una pregunta que solo
    mira la definicion se responderia que si con una funcion muerta.

    El contrasalto se queda: si no se derivan funciones de nivel superior
    en el modulo, el medidor dice que esta ROTO en vez de decir que no
    hay nada. Un medidor roto que devuelve lista vacia daria «hueco
    abierto» por el motivo equivocado.
    """
    ruta = SRC / "governance" / "graph_expansion.py"
    if not ruta.exists():
        return Hallazgo(
            "P3",
            "¿existe el paso DIFF entre la propuesta y la politica?",
            True,
            f"MEDIDOR ROTO: {ruta} no existe.",
        )
    arbol_exp = ast.parse(ruta.read_text(encoding="utf-8"))
    libres_exp = sorted(n.name for n in arbol_exp.body if isinstance(n, ast.FunctionDef))
    if not libres_exp:
        return Hallazgo(
            "P3",
            "¿existe el paso DIFF entre la propuesta y la politica?",
            True,
            f"MEDIDOR ROTO: {ruta.name} no declara funciones de nivel superior.",
        )

    # (a) la funcion de diff, en cualquier modulo de governance
    definiciones: list[str] = []
    for ruta_g in sorted((SRC / "governance").glob("*.py")):
        for n in ast.parse(ruta_g.read_text(encoding="utf-8")).body:
            if isinstance(n, ast.FunctionDef) and (
                "diff" in n.name.lower() or "corresponde" in n.name.lower()
            ):
                definiciones.append(f"{ruta_g.name}::{n.name}")

    # (b) que apply_expansion la llame: el call-site, derivado del arbol
    llamadas: set[str] = set()
    for n in ast.walk(arbol_exp):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            llamadas.add(n.func.id)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            llamadas.add(n.func.attr)
    usada = [d for d in definiciones if d.split("::", 1)[1] in llamadas]

    abierta = not definiciones or not usada
    return Hallazgo(
        "P3",
        "¿existe el paso DIFF entre la propuesta y la politica?",
        abierta,
        f"definiciones de diff en governance/: {definiciones or 'NINGUNA'}; "
        f"de esas, las que `apply_expansion` (y el resto del modulo) "
        f"LLAMAN: {usada or 'NINGUNA'}. Una funcion que existe y nadie "
        f"llama pone el diff DISPONIBLE, no en la secuencia.",
    )


def p4_diff_semantico(desde_fichero: dict[Path, list[ast.ClassDef]]) -> Hallazgo:
    """El roadmap: «no un diff de YAML».

    La primera version miraba el NOMBRE de las clases buscando a la vez
    una palabra del vocabulario y una de «cambio». No podia encontrar
    nada, porque el significado no esta en el nombre: esta en la
    ENUMERACION que el campo declara. `GraphChange` se llama asi, y su
    campo `subject` es un `Literal` con las siete clases de cambio.

    Un predicado que busca la palabra en el sitio equivocado no mide
    que falte el tipo: mide que el tipo no se llame como el predicado
    espera. Se mide la enumeracion, que es donde vive la semantica, y
    se cuenta contra el vocabulario del roadmap.
    """
    esperado = {
        "node",
        "relation",
        "capability",
        "policy",
        "budget",
        "priority",
        "evidence_requirement",
    }
    # Los type aliases de `Literal` son `AnnAssign` a nivel de modulo, no
    # `ClassDef`, asi que `_clases_por_fichero` no los ve. Se recorren
    # los ficheros del proyecto de la misma manera.
    encontradas: dict[str, set[str]] = {}
    for ruta in desde_fichero:
        for nodo in ast.parse(ruta.read_text(encoding="utf-8")).body:
            if not isinstance(nodo, ast.AnnAssign):
                continue
            if not isinstance(nodo.target, ast.Name):
                continue
            # `X: TypeAlias = Literal[...]` pone el Literal en el
            # VALOR, no en la anotacion: `X: TypeAlias` es lo que hay en
            # `annotation`. Recorrer solo la anotacion no encuentra nada,
            # y se lee como «no hay enumeracion»: el fallo que hizo que
            # P4 saliera abierto con la enumeracion delante.
            valores = {
                e.value
                for parte in (nodo.annotation, nodo.value)
                if parte is not None
                for e in ast.walk(parte)
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            if valores & esperado:
                encontradas[nodo.target.id] = valores & esperado

    completa = [n for n, v in encontradas.items() if v == esperado]
    return Hallazgo(
        "P4",
        "¿el cambio se nombra por su efecto semantico y no como texto?",
        not completa,
        f"enumeraciones de sujeto de cambio: "
        f"{ {k: sorted(v) for k, v in encontradas.items()} or 'NINGUNA' }. "
        f"Una enumeracion que cubre las 7 clases del roadmap: "
        f"{completa or 'NINGUNA'}",
    )


def p5_responde_las_preguntas(clases: dict[str, list[ast.ClassDef]]) -> Hallazgo:
    """Cada pregunta del roadmap necesita un dato que EXISTA en el tipo.

    La primera version devolvia `abierta=False` en cuanto encontraba un
    tipo con «diff» o «change» en el nombre —o sea, siempre que existiera
    `ChangedFile`—. No miraba los campos: afirmaba que el diff
    respondia a las siete preguntas sin comprobar si podia.

    Ahora se cruzan los CAMPOS reales con el dato que cada pregunta
    necesita, y se dice una por una cuales no puede responder.
    """
    candidatos = [
        c
        for cs in clases.values()
        for c in cs
        if ("diff" in c.name.lower() or "change" in c.name.lower())
        and any(
            v in n.lower()
            for n in _campos(c)
            for v in ("node", "relacion", "relation", "edge", "transition")
        )
    ]
    if not candidatos:
        return Hallazgo(
            "P5",
            "¿el diff responde a las 7 preguntas del roadmap?",
            True,
            "no hay tipo diff de grafo, luego no responde a ninguna de las 7",
        )
    campos = {n.lower() for c in candidatos for n in _campos(c)}

    # Que dato necesita cada pregunta. La lista de preguntas es del
    # operador (esta en ROADMAP.md) y los datos que necesita son de aqui:
    # si el tipo no lleva el campo, la pregunta no tiene respuesta.
    necesita: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("que cambia", ("node", "relacion", "relation", "edge", "transition", "kind")),
        ("por que", ("reason", "problema", "problem", "motivo", "rationale")),
        ("que evidencia lo justifica", ("evidence", "evidencia")),
        ("que coste anade", ("cost", "coste", "budget", "effort")),
        ("que capacidades exige", ("capabilit",)),
        ("que nodos invalida", ("invalid", "afect", "impact")),
        ("si es reversible", ("revers", "rollback", "deshace")),
    )
    faltan = [
        pregunta
        for pregunta, claves in necesita
        if not any(any(k in c for k in claves) for c in campos)
    ]
    return Hallazgo(
        "P5",
        "¿el diff responde a las 7 preguntas del roadmap?",
        bool(faltan),
        f"tipos diff de grafo: {[c.name for c in candidatos]}; "
        f"preguntas que NO puede responder ({len(faltan)}/7): {faltan or 'ninguna'}",
    )


def p6_cuatro_vistas(clases: dict[str, list[ast.ClassDef]]) -> Hallazgo:
    presentes = [v for v in VISTAS_GRAPH if v in clases]
    return Hallazgo(
        "P6",
        "¿existen las cuatro proyecciones tipadas del mismo sistema?",
        len(presentes) < len(VISTAS_GRAPH),
        f"vistas presentes: {presentes or 'NINGUNA'} de {len(VISTAS_GRAPH)}. "
        f"FUERA DEL ALCANCE DE B5 y por eso no baja el veredicto: son "
        f"cuatro proyecciones tipadas sobre recursos comunes, y el diff "
        f"que este bloque entrega se calcula sobre el grafo de ejecucion. "
        f"Construirlas sin el diff seria construirlas sin criterio.",
        en_alcance=False,
    )


def main() -> int:
    desde_fichero = _clases_por_fichero()
    clases = _clases(desde_fichero)
    hallazgos = [
        p1_existe_representacion_comparable(clases),
        p2_parche_tipado(clases),
        p3_paso_diff_entre_propuesta_y_politica(desde_fichero),
        p4_diff_semantico(desde_fichero),
        p5_responde_las_preguntas(clases),
        p6_cuatro_vistas(clases),
    ]

    print("Medidor B5 — Graph Diff Gate")
    print("=" * 72)
    for h in hallazgos:
        marca = "ABIERTO " if h.abierta else "CERRADO "
        print(f"\n[{marca}] {h.clave}  {h.pregunta}")
        print(f"          {h.detalle}")
    print()
    print("=" * 72)
    print(f"preguntas del roadmap que el diff debe responder: {len(PREGUNTAS_DIFF)}")
    for p in PREGUNTAS_DIFF:
        print(f"  - {p}")
    en_alcance = [h for h in hallazgos if h.en_alcance]
    fuera = [h for h in hallazgos if not h.en_alcance]
    abiertos = [h for h in en_alcance if h.abierta]
    print()
    print(f"huecos ABIERTOS EN ALCANCE: {len(abiertos)} de {len(en_alcance)}")
    for h in abiertos:
        print(f"  - {h.clave}: {h.pregunta}")
    if fuera:
        print()
        print(f"REGISTRADO FUERA DE ALCANCE: {len(fuera)}")
        for h in fuera:
            estado = "ABIERTO" if h.abierta else "CERRADO"
            print(f"  - {h.clave} [{estado}]: {h.pregunta}")

    if abiertos:
        print()
        print("VEREDICTO: el Graph Diff Gate NO EXISTE todavia. Salida 1.")
        return 1
    print()
    print(
        "VEREDICTO: el hueco de este bloque esta cerrado ("
        f"{len(en_alcance)} de {len(en_alcance)} en alcance). "
        f"{len(fuera)} queda registrado fuera de alcance. Salida 0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
