#!/usr/bin/env python3
"""Sonda de mutación del gate de B4.

Que un guard pase no dice que mida. Este script rompe cada propiedad a
propósito y exige que ALGO se ponga rojo; si algo sobrevive, el guard
tenia un agujero y lo dice por cual sonda.

**VERSIONADO, Y POR QUE.** Es la deuda que B3 midio y dejo registrada
(`bl-bl-01M41DFZEZ0003882TZNP7NPM0`): `.gitignore:81` excluye
`.pipelinek/*` y la evidencia del repo cita instrumentos que no estan en el
repo. Un instrumento que certifica y no se puede reproducir no certifica.

**Y LAS CUATRO LECCIONES DE B3, PAGADAS Y APLICADAS.**

1. Restaurar desde una COPIA del fichero entero, no invirtiendo el
   `replace`: `replace(viejo, nuevo, 1)` NO es simetrico cuando el texto no
   es unico, y asi se perdio un fichero mutado en el arbol.
2. La referencia es `git diff` de salida contra el de entrada, no un sha
   tomado del arbol antes de mutar — que hace invisible un fallo de
   restauracion justo cuando mas importa verlo.
3. `py_compile` despues de aplicar: una sonda que rompe la SINTAXIS es
   `SIN_SONDA`, no `NO_CAZADA`. Son categorias distintas, y la segunda seria
   una sonda rota disfrazada de medicion.
4. `PYTHONHASHSEED=0`, por la mutacion intermitente de la tercera entrega de
   B3 (el orden de un `set` de cadenas depende del hash).

Y CERO sondas no es exito: si el script no encuentra ninguna que aplicar,
sale con error. El defecto de la segunda entrega de B3 fue dar `0/12` con
`SIN_SONDA` en las doce y contarlo como una medicion.

Uso:
    uv run python scripts/mutate_b4_observed_state.py
    uv run python scripts/mutate_b4_observed_state.py --verbose
"""

from __future__ import annotations

import argparse
import hashlib
import os
import py_compile
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

GUARDS = ("tests/test_b4_observed_state.py",)

CAZADA = "CAZADA"
NO_CAZADA = "NO_CAZADA"
SIN_SONDA = "SIN_SONDA"


@dataclass(frozen=True, slots=True)
class Sonda:
    nombre: str
    fichero: str
    viejo: str
    nuevo: str
    porque: str


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1 el status se escribe pero vacio",
        fichero="src/skillgraph/platform/knowledge_repository.py",
        viejo="(status_to_json(observado), uid),",
        nuevo="('{}', uid),",
        porque="escribir un '{}' deja la fila igual que antes y el nodo "
        "parece avoir observado algo: es el fallo silencioso con la "
        "columna NOT NULL",
    ),
    Sonda(
        nombre="M2 el status declara su propia generacion",
        fichero="src/skillgraph/platform/knowledge_repository.py",
        viejo='            observed_generation=fila["generation"],',
        nuevo="            observed_generation=status.observed_generation,",
        porque="el status deja de LEER que spec observa y pasa a DECLARARlo: "
        "el campo miente en cuanto el spec cambia por debajo, y nada falla",
    ),
    Sonda(
        nombre="M3 escribir status sube generation",
        fichero="src/skillgraph/platform/knowledge_repository.py",
        viejo="                    resource_version = resource_version + 1",
        nuevo="                    resource_version = resource_version + 1,\n"
        "                    generation = generation + 1",
        porque="LA INVARIANTE R4. La separacion desired/observed se vuelve "
        "decorativa y el sistema sigue funcionando EXACTAMENTE igual: es el "
        "defecto que no se nota y por eso necesita guard propio",
    ),
    Sonda(
        nombre="M4 escribir status no sube resource_version",
        fichero="src/skillgraph/platform/knowledge_repository.py",
        viejo="                    resource_version = resource_version + 1",
        nuevo="                    resource_version = resource_version",
        porque="dos escrituras se vuelven indistinguibles y no hay forma de saber que algo cambio",
    ),
    Sonda(
        nombre="M5 se puede repetir un type de condicion",
        fichero="src/skillgraph/resources/status.py",
        viejo="            if cond.type in vistos:",
        nuevo="            if False:",
        porque="`Ready=True` y `Ready=False` a la vez dejan de ser un "
        "error, y un status que no sabe que observa se persiste igual",
    ),
    Sonda(
        nombre="M6 to_dict pierde un campo y el round-trip no lo nota",
        fichero="src/skillgraph/resources/status.py",
        viejo='            "observed_generation": self.observed_generation,',
        nuevo='            "observed_generation": 1,',
        porque="SUSTITUYE a una sonda anterior que sobrevivio, y el motivo "
        "importa mas que la sonda. La primera M6 quitaba `sort_keys=True` y "
        "NO fue cazada: el orden de las claves lo fija el literal de "
        "`to_dict`, luego dos escrituras del mismo objeto dan el mismo "
        "texto con o sin el, y la propiedad que la sonda queria medir era "
        "VACUA. Un guard que mide una propiedad que se cumple por "
        "construccion no mide nada, y la sonda no puede arreglarlo: hay que "
        "cambiar la PROPIEDAD. El round-trip si carga con algo, porque si "
        "`to_dict` pierde un campo la fila guarda menos de lo que el status "
        "dice y el operador ve un status distinto del que se escribio, sin "
        "ningun error",
    ),
    Sonda(
        nombre="M7 las condiciones dejan de ser tupla",
        fichero="src/skillgraph/resources/status.py",
        viejo='            object.__setattr__(self, "conditions", tuple(self.conditions))',
        nuevo="            pass",
        porque="una list que entra por la frontera se queda dentro del "
        "dominio y quien la recibe la muta. La anotacion no lo impedia",
    ),
    Sonda(
        nombre="M8 Brick gana el campo status",
        fichero="src/skillgraph/resources/bricks.py",
        viejo='    markdown_body: str = ""',
        nuevo='    status: dict = field(default_factory=dict)\n    markdown_body: str = ""',
        porque="R5. El tipo DECLARADO pasa a llevar el status, y entonces un "
        "pack declara el estado de su propio recurso: la mitad observada "
        "deja de estar observada y el sistema no puede distinguir "
        "`observed` de `human-asserted`",
    ),
)


def _diff_arbol() -> str:
    return subprocess.run(
        ["git", "diff"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _correr_guards() -> tuple[bool, str]:
    env = dict(os.environ, PYTHONHASHSEED="0")
    proc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            *GUARDS,
            "-q",
            "--no-header",
            "-x",
            "-p",
            "no:cacheprovider",
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode != 0, (proc.stdout + proc.stderr)[-2000:]


class _Restaurador:
    """Restaura desde COPIAS ENTERAS y verifica con `git diff`."""

    def __init__(self, ficheros: tuple[str, ...]) -> None:
        self._originales: dict[Path, bytes] = {RAIZ / f: (RAIZ / f).read_bytes() for f in ficheros}
        self.diff_de_entrada = _diff_arbol()

    def restaurar(self) -> None:
        for path, contenido in self._originales.items():
            path.write_bytes(contenido)

    def verificar(self) -> bool:
        return _diff_arbol() == self.diff_de_entrada


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    rojo, salida = _correr_guards()
    if rojo:
        print("FALLO: los guards ya estan rojos antes de mutar. No se mide nada.")
        print(salida)
        return 1
    print("Base: los guards pasan sin ninguna mutacion aplicada.")

    ficheros = tuple({s.fichero for s in SONDAS} | set(GUARDS))
    rest = _Restaurador(ficheros)
    cazadas: list[str] = []
    no_cazadas: list[str] = []
    sin_sonda: list[str] = []

    try:
        for sonda in SONDAS:
            ruta = RAIZ / sonda.fichero
            antes = _sha(ruta)
            texto = ruta.read_text(encoding="utf-8")
            if sonda.viejo not in texto:
                sin_sonda.append(sonda.nombre)
                print(
                    f"[{SIN_SONDA}] {sonda.nombre}: el texto viejo no esta; "
                    f"ha cambiado el codigo bajo el harness."
                )
                rest.restaurar()
                continue
            ruta.write_text(texto.replace(sonda.viejo, sonda.nuevo, 1), encoding="utf-8")
            if _sha(ruta) == antes:
                sin_sonda.append(sonda.nombre)
                print(
                    f"[{SIN_SONDA}] {sonda.nombre}: aplicada y el fichero no "
                    f"cambio; la sonda no hace nada."
                )
                rest.restaurar()
                continue
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    py_compile.compile(str(ruta), cfile=str(Path(tmp) / "m.pyc"), doraise=True)
                except py_compile.PyCompileError as exc:
                    sin_sonda.append(sonda.nombre)
                    print(
                        f"[{SIN_SONDA}] {sonda.nombre}: no compila, que es un "
                        f"cambio de SINTAXIS y no de comportamiento. {exc}"
                    )
                    rest.restaurar()
                    continue
                rojo, salida = _correr_guards()
            if rojo:
                cazadas.append(sonda.nombre)
                print(f"[{CAZADA}] {sonda.nombre}  <- {sonda.porque}")
            else:
                no_cazadas.append(sonda.nombre)
                print(f"[{NO_CAZADA}] {sonda.nombre}  <- {sonda.porque}")
                if args.verbose:
                    print(salida)
            rest.restaurar()
    finally:
        rest.restaurar()

    restaurado = rest.verificar()
    total = len(SONDAS)
    print("-" * 72)
    print(
        f"cazadas {len(cazadas)}/{total}  NO cazadas {len(no_cazadas)}  sin sonda {len(sin_sonda)}"
    )
    print(
        f"arbol restaurado byte a byte: {restaurado} (`git diff` de salida identico al de entrada)"
    )

    if not restaurado:
        print(
            "FALLO: el arbol NO quedo como estaba. Las mediciones de este informe no son validas."
        )
        return 1
    if sin_sonda:
        print("FALLO: hay sondas que no llegaron a plantear la pregunta.")
        return 1
    if no_cazadas:
        print(
            f"FALLO: {len(no_cazadas)} mutaciones sobreviven. El guard tiene "
            f"un agujero: {no_cazadas}"
        )
        return 1
    print("OK: el gate muerde en todas las propiedades medidas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
