"""Comprobacion manual del harness: que `verificar()` note un arbol sucio.

No es parte de la sonda de mutacion. Es la misma comprobacion que la sexta
entrega hacia a mano con la sonda rota: un instrumento que verifica la
restauracion tiene que Demonstrate que verifica.

Ejecutar: uv run python scripts/check_mutation_restore.py
"""

from __future__ import annotations

import importlib.util
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _cargar() -> object:
    ruta = RAIZ / "scripts" / "mutate_b3_production_gate.py"
    spec = importlib.util.spec_from_file_location("harness", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def main() -> int:
    h = _cargar()
    r = h._Restaurador()  # type: ignore[attr-defined]
    limpio = r.verificar()  # type: ignore[attr-defined]

    objetivo = RAIZ / "src" / "skillgraph" / "runtime" / "capability_controller.py"
    original = objetivo.read_bytes()
    objetivo.write_bytes(original + b"\n# -*- sucio a proposito -*-\n")
    sucio = r.verificar()  # type: ignore[attr-defined]
    objetivo.write_bytes(original)
    restaurado = r.verificar()  # type: ignore[attr-defined]

    print(f"arbol limpio      -> verificar() = {limpio}")
    print(f"arbol sucio       -> verificar() = {sucio}")
    print(f"re-restaurado     -> verificar() = {restaurado}")

    if limpio and restaurado and not sucio:
        print("OK: verificar() detecta un arbol sucio. No es decoracion.")
        return 0
    print("FALLO: verificar() no distingue un arbol sucio de uno limpio.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
