#!/usr/bin/env python3
"""Sondas de mutacion del gate de B5.

Cada sonda ROMPE una propiedad del gate en el arbol real y exige que la
red lo note. Una sonda que no es cazada no es una sonda debil: es la
evidencia de que el guard que queria reforzar no miraba nada.

Distingue tres resultados, y la distincion es lo que hace que el
harness diga la verdad:

  CAZADA    el guard se puso rojo
  SIN_SONDA el patron no se encontro en el texto, luego la mutacion NO
            se aplico y no se cuenta como victoria. Contarla seria
            mentir: es el error 32 de WI-113, repetido
  ROTA      la sonda se aplico pero el harness no pudo ejecutarlo

El arbol se restaura byte a byte y se verifica con `git diff`, no con
la palabra del harness.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = RAIZ / ".venv" / "bin" / "python"
TESTS = "tests/test_b5_graph_diff.py"
MEDIDOR = "scripts/measure_b5_graph_diff.py"

DIFF = RAIZ / "src" / "skillgraph" / "governance" / "graph_diff.py"
EXP = RAIZ / "src" / "skillgraph" / "governance" / "graph_expansion.py"


@dataclass(frozen=True, slots=True)
class Sonda:
    clave: str
    titulo: str
    fichero: Path
    viejo: str
    nuevo: str
    porque: str
    # Segunda sustitucion de la MISMA sonda, para las propiedades que
    # estan garantizadas en dos sitios y por tanto no se rompen
    # quitando uno. Ver M5.
    nuevo2: tuple[str, str] = ("", "")


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        "M1",
        "el diff se lee de la propuesta en vez de calcularse",
        DIFF,
        "        required_capabilities=tuple(sorted(capacidades_requeridas)),",
        "        required_capabilities=tuple(sorted(proposal.capabilities_needed)),",
        "EL GUARD ANTI-TAUTOLOGIA. Copia la DECLARACION en vez de "
        "derivar de las operaciones: el diff sigue contestando las 7 "
        "preguntas y sigue siendo un GraphDiff, pero ya no ve que la "
        "propuesta y su parche discrepen. Sin esto, un gate que valida "
        "la intencion del autor en vez de su cambio.",
    ),
    Sonda(
        "M2",
        "la huella del plan se deja de calcular",
        DIFF,
        "        base_fingerprint=huella_del_plan(plan),",
        '        base_fingerprint="",',
        "R6 sin su atadura. Sin la huella, un diff calculado sobre otro "
        "grafo pasaria por suyo siempre que coincida la revision, y el "
        "gate dejaria de ser una etapa para volverse un parametro. Es "
        "el fallo que se Midio: con el parche vacio el diff es vacio en "
        "cualquier plan.",
    ),
    Sonda(
        "M3",
        "apply_expansion acepta cualquier diff",
        EXP,
        "        if (error := el_diff_corresponde(diff, proposal, plan)) is not None:\n"
        '            return _rechazar(proposal, error, ("B5-DIFF",))',
        "        pass",
        "CONECTAR != CONTENER. La funcion de diff sigue existiendo y "
        "sigue siendo correcta, y el gate deja de comprobarla. Es la "
        "distincion que la spec llama R6 y la que un guard que solo "
        "mira la definicion no veria.",
    ),
    Sonda(
        "M4",
        "el sujeto del cambio se ensancha",
        DIFF,
        'ChangeSubject: TypeAlias = Literal[\n    "node",',
        'ChangeSubject: TypeAlias = Literal[\n    "nodo",\n    "node",',
        "R2 pierde la propiedad: anadir un valor al Literal es abrir el "
        "vocabulario del gate, y un gate cuyo vocabulario es abierto no "
        "es un gate. El `Literal` cerrado es lo que hace que la pregunta "
        "«que clase de cambio es esto?» tenga respuesta.",
    ),
    Sonda(
        "M5",
        "el diff deja de ser estable entre procesos",
        DIFF,
        "        required_capabilities=tuple(sorted(capacidades_requeridas)),",
        "        required_capabilities=tuple(capacidades_requeridas),",
        "La determinacion del diff. Esta sonda tiene HISTORIA y es la "
        "segunda vez que esta clase de fallo aparece en este repo (la "
        "M6 de B4), asi que va contada.\n\n"
        "La version 1 quitaba el `sorted()` de `to_dict` y no fue cazada: "
        "`to_dict` recibe campos que el constructor YA entrego ordenados, "
        "luego quitar el orden ahi no cambia nada. La propiedad era "
        "vacia.\n\n"
        "La version 2 lo quito del CONSTRUCTOR y tampoco fue cazada, y "
        "este si es el hallazgo: la garantia esta puesta DOS VECES —el "
        "constructor ordena y `to_dict` vuelve a ordenar—, luego quitar "
        "una no rompe nada. Eso no es un defecto, es defensa en "
        "profundidad, y significa que la PROPIEDAD no se puede sondear "
        "quitando una linea.\n\n"
        "Asi que la sonda quita las dos, que es lo que rompe la propiedad "
        "de verdad: sin `sorted()` en ningun sitio, las capacidades "
        "llegan en el orden que les da la tabla hash, ese orden cambia "
        "con `PYTHONHASHSEED`, y dos procesos que representan el mismo "
        "cambio producen textos distintos. Dos difss que no se comparan "
        "no son una etapa del gate.",
        nuevo2=(
            '            "required_capabilities": sorted(self.required_capabilities),',
            '            "required_capabilities": list(self.required_capabilities),',
        ),
    ),
    Sonda(
        "M6",
        "una operacion fuera de la union se acepta",
        DIFF,
        "    return isinstance(valor, AddNode | AddTransition | RemoveTransition)",
        "    return True",
        "R4 pierde su teeth: `object` vuelve a admitir cualquier valor por "
        "la puerta de atras. El parche quedaria «tipado» en la anotacion "
        "y sin tipo en la practica, que es peor que antes porque el "
        "codigo parece correcto.",
    ),
    Sonda(
        "M7",
        "el diff dice que es reversible sin mirar el rollback",
        DIFF,
        "        reversible=bool(proposal.rollback_plan),",
        "        reversible=True,",
        "La septima pregunta del roadmap pasa a contestarse siempre que "
        "si. Un diff que dice «es reversible» sin mirar el plan de "
        "rollback es la forma mas peligrosa de mentir: el gate leeria "
        "«reversible» y dejaria pasar un cambio que no lo es.",
    ),
    Sonda(
        "M8",
        "el diff de la propuesta se compara contra si mismo",
        DIFF,
        "    esperado = diff_graph(plan, proposal)\n    if diff != esperado:",
        "    esperado = diff\n    if diff != esperado:",
        "La comprobacion se vuelve tautologica: `diff != diff` es siempre "
        "falso, luego el gate acepta cualquier diff que llegue. Y sigue "
        "pareciendo que comprueba: el codigo esta entero y la asercion "
        "sigue escribiendo un mensaje. Es el error de WI-106 dado la "
        "vuelta: el guard que compara contra su propia copia.",
    ),
)


def _correr_red() -> tuple[int, str]:
    proc = subprocess.run(
        [str(PY), "-m", "pytest", TESTS, "-q", "-p", "no:randomly"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        timeout=600,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _correr_medidor() -> int:
    proc = subprocess.run(
        [str(PY), MEDIDOR],
        capture_output=True,
        text=True,
        cwd=RAIZ,
        timeout=120,
    )
    return proc.returncode


def _diff_arbol() -> str:
    proc = subprocess.run(["git", "diff"], capture_output=True, text=True, cwd=RAIZ, timeout=60)
    return proc.stdout


def main() -> int:
    base = _diff_arbol()
    rc, salida = _correr_red()
    if rc != 0:
        print("BASE: la red NO pasa sin mutacion. No se cuentan victorias.")
        print(salida[-2000:])
        return 2
    print("Base: la red pasa sin ninguna mutacion aplicada.")
    if _correr_medidor() != 0:
        print("BASE: el medidor sale != 0 sin mutacion. Algo esta roto.")
        return 2
    print("Base: el medidor sale 0 (el hueco esta cerrado).\n")

    cazadas = 0
    sin_sonda = 0
    rotas = 0
    fallos: list[str] = []

    for sonda in SONDAS:
        texto = sonda.fichero.read_text(encoding="utf-8")
        if texto.count(sonda.viejo) != 1:
            print(f"[SIN_SONDA] {sonda.clave} {sonda.titulo}")
            print(f"           el patron aparece {texto.count(sonda.viejo)} veces, se esperaba 1")
            sin_sonda += 1
            continue
        # El segundo sitio se aplica SOLO si la sonda lo declara, y se
        # COMPRUEBA que tambien queda aplicado antes de contar. Sin esa
        # comprobacion, una sonda de dos sitios que se aplicara a medias
        # se contaria como victoria: es el error 32 de WI-113 en su
        # forma mas incomoda, porque la sonda parece ejecutarse.
        mutado = texto.replace(sonda.viejo, sonda.nuevo)
        if sonda.nuevo2[0]:
            assert sonda.nuevo2[0] in mutado, (
                f"{sonda.clave}: el segundo sitio a mutar no existe ya en el "
                f"texto, luego la sonda NO esta midiendo lo que dice"
            )
            mutado = mutado.replace(*sonda.nuevo2)
            assert sonda.nuevo2[1] in mutado, f"{sonda.clave}: el segundo sitio no se aplico"
        try:
            sonda.fichero.write_text(mutado, encoding="utf-8")
            rc, salida = _correr_red()
        except Exception as exc:
            print(f"[ROTA] {sonda.clave} {sonda.titulo} -> {exc}")
            rotas += 1
            sonda.fichero.write_text(texto, encoding="utf-8")
            continue
        finally:
            sonda.fichero.write_text(texto, encoding="utf-8")

        if rc != 0:
            cazadas += 1
            print(f"[CAZADA] {sonda.clave} {sonda.titulo}")
            print(f"           {sonda.porque}")
        else:
            fallos.append(f"{sonda.clave}: {sonda.titulo}")
            print(f"[NO CAZADA] {sonda.clave} {sonda.titulo}")
            print(f"             {sonda.porque}")
        assert _diff_arbol() == base, "el arbol no quedo como estaba"

    print()
    print("-" * 72)
    print(
        f"cazadas {cazadas}/{len(SONDAS)}   NO cazadas {len(fallos)}   "
        f"sin sonda {sin_sonda}   rotas {rotas}"
    )
    if fallos:
        print("ESTAS SONDAS NO MIEREN NADA:")
        for f in fallos:
            print(f"  - {f}")
    restaurado = _diff_arbol() == base
    print(f"arbol restaurado byte a byte: {restaurado}")
    if not restaurado or sin_sonda or rotas or fallos:
        print("FALLO: el gate no muerde en todas las propiedades medidas.")
        return 1
    print("OK: el gate muerde en todas las propiedades medidas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
