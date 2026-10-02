#!/usr/bin/env python3
"""WI-98: comprueba que todo runner remoto ejecuta la MISMA receta que la local.

Por qué este script existe
--------------------------
`AGENTS.md` («CI Local Obligatorio», apartado «Compatibilidad con otros
runners») declara:

    GitHub Actions, GitLab CI, Jenkins o cualquier otro runner remoto **debe**
    invocar el mismo `.pipeline.kts` desde el mismo checkout.

Medido en WI-98, esa línea describe algo que no ocurría. `.github/workflows/
ci.yml` no invocaba `.pipeline.kts`: de los siete stages canónicos
reproducía **uno**, `unit-tests` lo hacía con otra receta, y los tres
contratos exigibles (`coverage-floors`, `package-build` y el propio
`unit-tests` con la receta de cobertura) no existían en el remoto.

Y la divergencia no era de estilo. Con el mismo instrumento:

    modulo                       canonica    remota
    cli/commands/runs.py           87.96 %    39 %
    cli/support.py                 85.71 %    69 %   <- suelo declarado: 70 %

El remoto podía dar **verde** un paquete que no cumplía el suelo que el
propio `AGENTS.md §6.3` declara, porque no ejecutaba el checker y su
medición no veía lo que el canónico ve.

Lo que este script mide
-----------------------
C1  todo runner remoto declarado invoca la receta canónica;
C2  la receta canónica es ejecutable fuera de esta máquina (no lleva rutas
    absolutas a un árbol de trabajo concreto);
C3  las etapas canónicas se leen **del script**, no de una lista paralela.

Por qué C2 está aquí y no en un documento
-----------------------------------------
Cumplir C1 sin C2 produce una promesa inejecutable: el remoto invoca la
receta canónica y falla en el primer `ls` porque la ruta no existe en su
disco. Las dos cosas son la misma regla mirada desde los dos lados, y medirlas
por separado produce un falso verde en cualquiera de las dos.

Diseno: puro por encima, efecto por debajo
------------------------------------------
`evaluar(informe)` y sus descompuestos son **funciones puras**: no leen disco y
devuelven una tupla de problemas. `medir()` es la única parte que lee ficheros.
Esa division permite construir contraejemplos con informes sintéticos en vez
de mutar `.github/workflows/ci.yml`.

Uso
---
    uv run python scripts/check_ci_recipe_parity.py            # contrato
    uv run python scripts/check_ci_recipe_parity.py --json     # informe
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CODIGO_RECETA_PROPIA: Final = "sg_ci_receta_propia"
CODIGO_RUTA_ABSOLUTA: Final = "sg_ci_ruta_absoluta"
CODIGO_ETAPA_DESCONOCIDA: Final = "sg_ci_etapa_desconocida"
CODIGO_RUNNER_INEXISTENTE: Final = "sg_ci_runner_inexistente"

#: La receta local, por nombre. Es el unico nombre que significa «la canonica».
RECETA_CANONICA: Final = ".pipeline.kts"

#: Directorios donde un runner remoto puede declararse. Se recorren en vez de
#: mantener una lista de ficheros: un `.gitlab-ci.yml` nuevo tiene que entrar
#: solo en el contrato, no cuando alguien se acuerde de anadirlo.
DIRECTORIOS_RUNNER: Final[tuple[str, ...]] = (".github/workflows", ".gitlab")

#: Ficheros que declaran un runner remoto dentro de esos directorios.
PATRONES_RUNNER: Final[tuple[str, ...]] = ("*.yml", "*.yaml")

#: Rutas absolutas que apuntan a un arbol de trabajo concreto y hacen la receta
#: inejecutable en cualquier otra maquina.
#:
#: Se busca un arbol de trabajo, no `/` en general: `/usr/bin/uv` o
#: `/tmp/pipeline` son legitimos y no atan el script a ningun sitio. Un arbol
#: tiene la forma `/algo/otro/mas` y aparece dentro de un `sh(...)`.
#: Medido en WI-98 sobre `.pipeline.kts`: 10 apariciones de
#: `/var/mnt/DiscoChino2-fast/Proyectos/python/skillgraph`.
_RAIZ_ABSOLUTA: Final = re.compile(
    r'sh\(\s*"(?:[^"]*?\s)?(/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)'
)


@dataclass(frozen=True, slots=True)
class Problema:
    """Un incumplimiento del contrato. Inmutable: se acumula en tuplas."""

    codigo: str
    mensaje: str


@dataclass(frozen=True, slots=True)
class InformeRunners:
    """Lo medido sobre los ficheros. Inmutable: lo evaluan funciones puras."""

    receta_canonica: str
    canonica: str
    runners: dict[str, str]
    etapas_canonicas: tuple[str, ...]
    hubo_error: bool = False
    error: str = ""


# =====================================================================
# CAPA PURA — de aqui abajo no se lee disco.
# =====================================================================


def evaluar_recetas(informe: InformeRunners) -> tuple[Problema, ...]:
    """C1. Cada runner remoto invoca la receta canónica.

    Se busca el nombre del script, no una lista de comandos: exigir que el
    remoto mentione «lint» y «pytest» es aceptar una reimplementación parcial
    que se queda sin los contratos que la local sí ejecuta. Esa es
    exactamente la divergencia que este bloque cierra.
    """
    problemas: list[Problema] = []
    for ruta in sorted(informe.runners):
        cuerpo = informe.runners[ruta]
        if RECETA_CANONICA in cuerpo:
            continue
        problemas.append(
            Problema(
                CODIGO_RECETA_PROPIA,
                f"{ruta} no invoca {RECETA_CANONICA}: ejecuta su propia receta. "
                f"Si un runner remoto produce PASS y la receta local produce FAIL, "
                f"nadie sabe cual de las dos estaba mintiendo",
            )
        )
    return tuple(problemas)


def evaluar_portabilidad(informe: InformeRunners) -> tuple[Problema, ...]:
    """C2. La receta canónica no lleva rutas atadas a esta máquina.

    Sin esto, C1 produce una promesa inejecutable: el remoto invoca la receta
    y falla en el primer paso porque la ruta no existe en su disco. Las dos
    invariantes son la misma regla por los dos lados.
    """
    encontrados = sorted(set(_RAIZ_ABSOLUTA.findall(informe.canonica)))
    if not encontrados:
        return ()
    return (
        Problema(
            CODIGO_RUTA_ABSOLUTA,
            f"{informe.receta_canonica} lleva rutas absolutas a un arbol concreto "
            f"({', '.join(encontrados[:3])}): no se puede ejecutar fuera de esta "
            f"maquina, asi que la regla «el remoto invoca la misma receta» es "
            f"inejecutable",
        ),
    )


def evaluar_etapas(informe: InformeRunners) -> tuple[Problema, ...]:
    """C3. Toda etapa de la receta canónica está en la lista que se vigila.

    El guard que sólo vigila la lista que el mismo mantiene no vigila nada.
    Por eso `etapas_canonicas` se lee del script: una etapa nueva entra sola
    en el contrato, y dejarla fuera es una decision visible.
    """
    declaradas = set(informe.etapas_canonicas)
    if not declaradas:
        return (
            Problema(
                CODIGO_ETAPA_DESCONOCIDA,
                f"no se ha podido leer ninguna etapa de {informe.receta_canonica}: "
                f"el script cambio de forma o esta roto, y un contrato que no "
                f"lee su fuente no puede afirmar nada sobre ella",
            ),
        )
    return ()


def evaluar(informe: InformeRunners) -> tuple[Problema, ...]:
    """C1..C3. Si la medición falló, no dice nada más."""
    if informe.hubo_error:
        return (Problema(CODIGO_RUNNER_INEXISTENTE, f"no se pudo medir: {informe.error}"),)
    return (
        *evaluar_recetas(informe),
        *evaluar_portabilidad(informe),
        *evaluar_etapas(informe),
    )


def codigos_de(problemas: tuple[Problema, ...]) -> frozenset[str]:
    return frozenset(p.codigo for p in problemas)


# =====================================================================
# CAPA DE EFECTO — de aqui abajo se lee disco.
# =====================================================================


def etapas_de(script: str) -> tuple[str, ...]:
    """Los nombres de etapa de un script de pipelinek, en orden.

    Se leen del texto y no de una lista escrita a mano: un guard que lleva su
    propia lista de etapas solo vigila las etapas que ya conocia.
    """
    return tuple(re.findall(r'\bstage\(\s*"([^"]+)"', script))


def runners_de(raiz: Path) -> dict[str, str]:
    """Todo fichero que declara un runner remoto, como `ruta -> contenido`.

    Se recorre en vez de listarse: un `.gitlab-ci.yml` nuevo tiene que entrar
    en el contrato el día que se añade, no el día que alguien se acuerde.
    """
    encontrados: dict[str, str] = {}
    for directorio in DIRECTORIOS_RUNNER:
        base = raiz / directorio
        if not base.is_dir():
            continue
        for patron in PATRONES_RUNNER:
            for fichero in sorted(base.rglob(patron)):
                encontrados[str(fichero.relative_to(raiz))] = fichero.read_text(encoding="utf-8")
    return encontrados


def medir(raiz: Path) -> InformeRunners:
    """Lee los ficheros reales y devuelve lo medido."""
    try:
        canonica = raiz / RECETA_CANONICA
        if not canonica.is_file():
            return _informe_de_error(f"no existe {RECETA_CANONICA} en {raiz}")
        texto = canonica.read_text(encoding="utf-8")
        return InformeRunners(
            receta_canonica=RECETA_CANONICA,
            canonica=texto,
            runners=runners_de(raiz),
            etapas_canonicas=etapas_de(texto),
        )
    except (OSError, UnicodeDecodeError) as exc:
        return _informe_de_error(str(exc))


def _informe_de_error(mensaje: str) -> InformeRunners:
    """Informe vacio con el error marcado: `evaluar` no dira nada mas.

    Fabricar un informe con cero etapas y cero runners parecería un repo sin
    CI remoto, que es un diagnóstico distinto del real.
    """
    return InformeRunners(
        receta_canonica=RECETA_CANONICA,
        canonica="",
        runners={},
        etapas_canonicas=(),
        hubo_error=True,
        error=mensaje,
    )


def formatear(problemas: tuple[Problema, ...]) -> str:
    if not problemas:
        return (
            "OK: todo runner remoto invoca la receta canónica, "
            "y la receta canónica se puede ejecutar fuera de esta máquina."
        )
    lineas = [f"FALLO: {len(problemas)} incumplimiento(s) del contrato de CI"]
    lineas.extend(f"  [{p.codigo}] {p.mensaje}" for p in problemas)
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Comprueba que todo runner remoto ejecuta la receta canónica."
    )
    parser.add_argument("--json", action="store_true", help="volcar el informe como JSON")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    informe = medir(args.repo.resolve())
    problemas = evaluar(informe)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not problemas,
                    "problemas": [{"codigo": p.codigo, "mensaje": p.mensaje} for p in problemas],
                    "informe": {
                        "receta_canonica": informe.receta_canonica,
                        "runners": sorted(informe.runners),
                        "etapas_canonicas": list(informe.etapas_canonicas),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(formatear(problemas))
    return 0 if not problemas else 1


if __name__ == "__main__":
    raise SystemExit(main())
