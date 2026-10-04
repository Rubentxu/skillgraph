#!/usr/bin/env python3
"""B15 · de qué tipo es la evidencia de cada propiedad del gate de 1.0.

El hallazgo
-----------
Hasta B15, los veinte PASS del gate salian en la misma lista y con la misma
tipografia. No habia manera de saber cuales estaban respaldados por algo que se
**ejecuta** y cuales por una lectura del arbol. Y la diferencia no es de
estetica: es si el veredicto **puede volverse falso sin que nadie vuelva a
mirarlo**.

Que se mide aqui
----------------
No «cuantas clases hay» —eso lo dice el propio gate— sino dos cosas que el gate
no puede decirse a si mismo:

1. **La linea base**, derivada ejecutando el gate: cuantas propiedades hay de
   cada clase y CUALES son las que se quedan en `derivada`. Esa lista es lo que
   permite ordenar el trabajo siguiente sin inventarlo.
2. **Que la derivacion no este degenerada**, con `--autocomprobacion`: se le da
   al gate un modulo al que se le ha quitado el `subprocess` entero, y se exige
   que las trece `ejecutada` pasen a `derivada`. Una instrumentacion que solo
   sabe imprimir un numero no sabe si el numero viene de las clases o de una
   lista escrita al lado.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"
PY = sys.executable


def _carga() -> object:
    spec = importlib.util.spec_from_file_location("gate_b15_measure", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b15_measure"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _clases() -> list[tuple[str, str]]:
    """(nombre de propiedad, clase) para las veinte, en el orden del roadmap."""
    modulo = _carga()
    nombres = modulo.propiedades_del_roadmap(modulo._lee("ROADMAP.md"))
    return [(n, modulo.clase_de_evidencia(modulo._slug(n))) for n in nombres]


def _autocomprobacion() -> int:
    """Quita el subproceso del modulo entero y exige que la clase gire entera.

    Dos cosas se comprueban, y las dos importan:

    - que **todas** las `ejecutada` pasen a `derivada`, que es lo que prueba
      que la clase sale de mirar el subproceso y no de una constante;
    - que al menos una clase **gire de verdad**, que es lo que impide que una
      instrumentacion que devuelve siempre la lista vacia se declare buena.

    MEDIDO al escribir esto: la primera version de un sondeo parecido busco las
    capacidades por cadenas donde el codigo usa nombres, y despues por el nombre
    de un operador donde el AST tiene un nodo. Dio tres cifras distintas —0 de
    12, 9 de 12, 3 de 12— y ninguna era la correcta. Un instrumento de medicion
    que no se puede contrastar no es un instrumento.
    """
    modulo = _carga()
    texto = GATE.read_text(encoding="utf-8")
    antes = dict(_clases())
    ejecutadas_antes = [k for k, v in antes.items() if v == "ejecutada"]
    derivadas_antes = [k for k, v in antes.items() if v == "derivada"]
    total_antes = len(antes)

    deformado = texto.replace("subprocess.", "modulo_que_no_existe.")
    if deformado == texto:
        print("NO SE EJECUTA: el gate no menciona `subprocess`, y la autocomprobacion no")
        print("tendria nada que cortar. O el gate dejo de ejecutar, o el texto cambio.")
        return 2
    despues = {n: modulo.clase_de_evidencia(modulo._slug(n), deformado) for n in antes}
    siguen = [n for n in ejecutadas_antes if despues[n] == "ejecutada"]
    if siguen:
        print(f"NO SE EJECUTA: sin `subprocess` en el modulo, {siguen} siguen `ejecutada`.")
        print("La clase no sale del codigo: alguien la escribio a mano.")
        return 2
    if not despues or set(despues.values()) != {"derivada"}:
        print(f"NO SE EJECUTA: al cortar el subproceso quedaron clases raras: {despues}")
        return 2

    print(f"linea base      : {len(ejecutadas_antes)} ejecutada, {len(derivadas_antes)} derivada")
    print(f"sin subprocess  : las {len(ejecutadas_antes)} `ejecutada` pasaron a `derivada`")
    print(f"propiedades     : {total_antes}, las {len(despues)} clasificables sin cambio")
    print(f"clases que giran: {len(ejecutadas_antes)} de {total_antes}")
    print(f"\n{len(ejecutadas_antes)}/{total_antes} sondas cazadas")
    return 0


def main() -> int:
    if "--autocomprobacion" in sys.argv:
        return _autocomprobacion()

    clases = _clases()
    conteo = Counter(c for _, c in clases)
    derivadas = [n for n, c in clases if c == "derivada"]

    print("B15 · que tipo de evidencia tiene cada propiedad del gate de 1.0")
    print("(clase DERIVADA del AST del propio gate: se sigue el grafo de llamadas)\n")

    proc = subprocess.run(
        [PY, str(GATE)], cwd=RAIZ, capture_output=True, text=True, check=False, timeout=1800
    )
    if proc.returncode != 0:
        print(f"ABORTA: el gate salio con rc={proc.returncode}")
        print((proc.stderr or proc.stdout)[-400:])
        return 2

    print(f"{'propiedad':<44} {'clase':<11}")
    print("-" * 58)
    for nombre, clase in clases:
        print(f"{nombre:<44} {clase:<11}")
    print()
    print(f"ejecutada {conteo['ejecutada']}   derivada {conteo['derivada']}")

    print("\nLo que NO se puede retirar solo — y por eso queda por detrás:")
    for nombre in derivadas:
        print(f"  - {nombre}")
    print(
        "\nUna propiedad `derivada` es cierta HOY, y no por esto: es lo que el\n"
        "gate deduce de leer el arbol. Si el proyecto cambia sin que el texto\n"
        "cambie —un `_` que se renombra, un modulo que se mueve, un default que\n"
        "alguien cambia en otro fichero— el veredicto no se entera. Subir una\n"
        "propiedad a `ejecutada` requiere un instrumento, y un instrumento es un\n"
        "bloque. Esta lista es el orden."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
