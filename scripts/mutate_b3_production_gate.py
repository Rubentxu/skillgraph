#!/usr/bin/env python3
"""Sonda de mutacion para el gate de B3-cierre.

Que un guard pase no dice que mida. Este script rompe cada propiedad a
propósito y exige que ALGO se ponga rojo; si algo sobrevive, el guard
tenia un agujero y lo dice por cual sonda.

**POR QUE ESTA VERSIONADO Y NO EN `.pipelinek/`.** Es la deuda que B3
midio y escribio en su §11: `.gitignore:81` excluye `.pipelinek/*`, hay
318 instrumentos ahi y 1 versionado, y la evidencia de B0, B1, B2 y B3
cita rutas de ahi. O sea: **la evidencia de este repo, en su mayor parte,
no es recuperable por quien la lee.** Es una decision de politica del repo
y esta registrada como item de backlog en SDDK; lo que se hace aqui es no
amplificar el problema, escribiendo el instrumento de ESTE bloque en un
sitio que si se versiona. Un instrumento que certifica y no se puede
reproducir no certifica.

**LAS TRES LECCIONES DE LA SEXTA ENTREGA, QUE ESTAN PAGADAS Y SE APLICAN.**

1. **Restaurar desde una COPIA del fichero entero**, no invirtiendo el
   `replace`. `replace(viejo, nuevo, 1)` NO es simetrico cuando el texto
   no es unico: cambia la primera ocurrencia de `viejo` y luego la
   primera de `nuevo`, que puede no ser la misma linea. Se perdio un
   fichero mutado en el arbol por esto.

2. **La referencia de verificacion es `git diff`**, tomado ANTES y
   DESPUES. Antes se comparaba contra un sha tomado del arbol ya
   posiblemente sucio, con lo que un fallo de restauracion hacia
   INVISIBLE el defecto justo cuando mas importaba verlo. `git` compara
   contra el commit, que es lo unico que este script no controla.

3. **`py_compile` despues de aplicar.** Una sonda que rompe la SINTAXIS
   no es una sonda: no llego a plantear la pregunta. Antes se contaba como
   "medida y no cazada", que es una sonda rota disfrazada de medicion.
   Ahora es `SIN_SONDA`, que es una categoria distinta y honesta.

Y dos antidotos que este repo ya se ha ganado:

- **`PYTHONHASHSEED=0`**, por la mutacion intermitente de la tercera
  entrega (el orden de un `set` de cadenas depende del hash, que Python
  aleatoriza por proceso: 8 ordenes distintos en 8 corridas).
- **CERO sondas no es exito.** Si este script no encuentra ninguna sonda
  que aplicar, sale con error. Un instrumento que dice «0 mutaciones
  cazadas» sin haberlas buscado es el defecto de la segunda entrega, que
  dio `0/12` con `SIN_SONDA` en las doce y lo conto como medida.

Uso:
    uv run python scripts/mutate_b3_production_gate.py
    uv run python scripts/mutate_b3_production_gate.py --verbose
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

#: Los guards que tienen que ponerse rojos. Se derivan del nombre del
#: fichero: uno vacio haria que el harness no mirase nada.
FICHEROS_DE_GUARD: tuple[str, ...] = ("tests/test_b3_production_adapter.py",)

CAZADA = "CAZADA"
NO_CAZADA = "NO_CAZADA"
SIN_SONDA = "SIN_SONDA"


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una mutacion, y que se espera que rompa."""

    nombre: str
    fichero: str
    viejo: str
    nuevo: str
    porque: str
    espera: str = "rojo"


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1 la validacion de `kind` desaparece entera",
        fichero="src/skillgraph/knowledge/knowledge_query.py",
        viejo="""        if crudo is None:
            raise ValidationError(
                f"{KNOWLEDGE_QUERY} necesita 'kind' en arguments. Opciones: {sorted(CONSULTAS)}"
            )
        if not isinstance(crudo, str) or crudo not in CONSULTAS:
            raise ValidationError(
                f"consulta {crudo!r} no soportada por {KNOWLEDGE_QUERY}. "
                f"Opciones: {sorted(CONSULTAS)}"
            )
        return crudo""",
        nuevo="""        return _CLAIMS if crudo is None else crudo""",
        porque="sin validar, una consulta mal formada o inexistente cae en "
        "la rama de `claims` y devuelve una lista vacia: el fallo silencioso "
        "que el contrato existe para evitar. LA PRIMERA VERSION de esta "
        "sonda quitaba solo el `if crudo is None` y NO fue cazada —la "
        "comprobacion siguiente hacia de respaldo y el test seguia "
        "pasando—, o sea que media una redundancia y no la propiedad",
    ),
    Sonda(
        nombre="M2 la procedencia por elemento se pierde",
        fichero="src/skillgraph/knowledge/knowledge_query.py",
        viejo='                "source_id": c.source_id,',
        nuevo='                "source_id": "",',
        porque="B6 no puede distinguir `observed` de lo que afirmo un "
        "agente si el elemento no dice de que source salio",
    ),
    Sonda(
        nombre="M3 el kernel ejecuta a medias",
        fichero="src/skillgraph/runtime/capability_controller.py",
        viejo="        faltan = self._registry.missing_from(required)",
        nuevo="        faltan = ()",
        porque="sin comprobar antes, se ejecuta lo que hay y el nodo parece "
        "haberse ejecutado cuando no pudo",
    ),
    Sonda(
        nombre="M4 el kernel reescribe la procedencia",
        fichero="src/skillgraph/runtime/capability_controller.py",
        viejo="        return CapabilityOutcome(requested=type_name, result=resultado)",
        nuevo="        return CapabilityOutcome(requested=resultado.adapter, result=resultado)",
        porque="poniendo el nombre de la clase en `requested`, una "
        "divergencia entre lo pedido y lo servido deja de ser visible y "
        "el despliegue deja de poder auditarse",
    ),
    Sonda(
        nombre="M5 el resultado deja de ser inmutable",
        fichero="src/skillgraph/runtime/capability_controller.py",
        viejo="        return tuple(self._uno(tipo, subject=subject, arguments=arguments) for tipo in required)",
        nuevo="        return [self._uno(tipo, subject=subject, arguments=arguments) for tipo in required]",
        porque="una `list` que el llamante muta cambia el numero de "
        "capabilities ejecutadas sin que nadie lo vea",
    ),
    Sonda(
        nombre="M6 el nucleo nombra la capability",
        fichero="src/skillgraph/runtime/capability_controller.py",
        viejo='__all__ = ["CapabilityController", "CapabilityOutcome"]',
        nuevo='__all__ = ["CapabilityController", "CapabilityOutcome"]\n\n'
        '_NOMBRE_CONOCIDO = "sg.knowledge.query"',
        porque="es la propiedad ESTRUCTURAL del gate del roadmap: un "
        '`if tipo == "sg.knowledge.query"` en el nucleo rompe el '
        "acoplamiento aunque el resultado sea identico. Un test de "
        "comportamiento NO la cazaria",
    ),
)


def _diff_arbol() -> str:
    """El estado del arbol contra el commit: la referencia que no controlo."""
    return subprocess.run(
        ["git", "diff"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rojo() -> tuple[bool, str]:
    """Corre los guards con el hash de PYTHONHASHSEED fijado a 0."""
    env = dict(os.environ, PYTHONHASHSEED="0")
    proc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            *FICHEROS_DE_GUARD,
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


def _verde() -> tuple[bool, str]:
    return not _rojo()[0], ""


class _Restaurador:
    """Restaura desde una COPIA ENTERA del fichero. Leccion 1 y 2.

    Guarda el contenido original una vez, y entre sondas lo comprueba con
    `_diff_arbol` contra el diff de entrada. Si alguna vez no coincide, el
    script dice que NO RESTAURO y sale con error, en vez de seguir
    midiendo sobre un arbol sucio: medir sobre un arbol sucio es como la
    sexta entrega dejo el arbol mutado y afirmo igualmente que estaba
    restaurado byte a byte.
    """

    def __init__(self) -> None:
        self._originales: dict[Path, bytes] = {}
        for f in FICHEROS_DE_GUARD:
            self._originales[RAIZ / f] = (RAIZ / f).read_bytes()
        for s in SONDAS:
            p = RAIZ / s.fichero
            if p not in self._originales:
                self._originales[p] = p.read_bytes()
        self.diff_de_entrada = _diff_arbol()

    def restaurar(self) -> None:
        for path, contenido in self._originales.items():
            path.write_bytes(contenido)

    def verificar(self) -> bool:
        """El `git diff` de salida tiene que ser IDENTICO al de entrada."""
        return _diff_arbol() == self.diff_de_entrada


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    verde, salida = _verde()
    if not verde:
        print("FALLO: los guards ya estan rojos antes de mutar. No se mide nada.")
        print(salida)
        return 1
    print("Base: los guards pasan sin ninguna mutacion aplicada.")

    rest = _Restaurador()
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
                    f"[{SIN_SONDA}] {sonda.nombre}: el texto viejo no esta. "
                    f"Ha cambiado el codigo bajo el harness."
                )
                rest.restaurar()
                continue

            ruta.write_text(texto.replace(sonda.viejo, sonda.nuevo, 1), encoding="utf-8")
            if _sha(ruta) == antes:
                sin_sonda.append(sonda.nombre)
                print(
                    f"[{SIN_SONDA}] {sonda.nombre}: aplicada y el fichero "
                    f"NO cambio. La sonda no hace nada."
                )
                rest.restaurar()
                continue

            # Leccion 3: lo que no compila no llegó a plantear la pregunta.
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

                rojo, salida = _rojo()
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
