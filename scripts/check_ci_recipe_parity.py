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
C3  las etapas canónicas se leen **del script**, no de una lista paralela;
C4  quien ejecuta `pytest` está conectado a la receta canónica: o es un
    fragmento que ella invoca, o delega en ella (WI-99).

Por qué C2 está aquí y no en un documento
-----------------------------------------
Cumplir C1 sin C2 produce una promesa inejecutable: el remoto invoca la
receta canónica y falla en el primer `ls` porque la ruta no existe en su
disco. Las dos cosas son la misma regla mirada desde los dos lados, y medirlas
por separado produce un falso verde en cualquiera de las dos.

Por qué C4 está aquí y no en un documento
-----------------------------------------
`scripts/audit_bundle.sh` existe para dar evidencia reproducible a una
auditoría independiente. Medido en WI-99, la producía llamando a un script
que corría `pytest` a pelo, es decir, con el instrumento que **no ve el CLI
ejecutado por subproceso**. Un documento que dijera «delega en la receta
canónica» no habría cambiado nada la próxima vez que alguien añadiera una
línea a un script; un contrato que mira los ficheros, sí.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

CODIGO_RECETA_PROPIA: Final = "sg_ci_receta_propia"
CODIGO_RUTA_ABSOLUTA: Final = "sg_ci_ruta_absoluta"
CODIGO_ETAPA_DESCONOCIDA: Final = "sg_ci_etapa_desconocida"
CODIGO_RUNNER_INEXISTENTE: Final = "sg_ci_runner_inexistente"
CODIGO_RECETA_SUYA: Final = "sg_ci_receta_suya"

#: La receta local, por nombre. Es el unico nombre que significa «la canonica».
RECETA_CANONICA: Final = ".pipeline.kts"

#: Directorios donde un runner remoto puede declararse. Se recorren en vez de
#: mantener una lista de ficheros: un `.gitlab-ci.yml` nuevo tiene que entrar
#: solo en el contrato, no cuando alguien se acuerde de anadirlo.
DIRECTORIOS_RUNNER: Final[tuple[str, ...]] = (".github/workflows", ".gitlab")

#: Ficheros que declaran un runner remoto dentro de esos directorios.
PATRONES_RUNNER: Final[tuple[str, ...]] = ("*.yml", "*.yaml")

#: Cómo tiene que resolver la raíz un script portable: por entorno (el runner
#: la define) o por el cwd del proceso (el repo, cuando se invoca desde su
#: raíz). MEDIDO en WI-98: el motor v0.39.0 sí propaga el entorno a los
#: `sh()`, así que esto no es un truco sino una línea.
_RESUELVE_RAIZ: Final = re.compile(r'System\.getenv\(|System\.getProperty\(\s*"user\.dir"\s*\)')

#: Directorios de `scripts/` cuyos ficheros **no** son recetas de verificación.
#:
#: MEDIDO en WI-99: `scripts/hooks/pre-push` ejecuta la suite completa de
#: `pytest` a pelo y emite un veredicto sobre el árbol antes de dejar pushear.
#: Con el mismo instrumento, ese veredicto no ve el CLI ejecutado por
#: subproceso (`cli/commands/runs.py`: 39 % frente al 87,96 % de la
#: instrumentada). Queda como **deuda medida y no resuelta**, no como
#: conformidad: un hook de git tiene un presupuesto de tiempo fijo y corto
#: (el `pre-commit` es un smoke de ~10 s) y su salida es un filtro de evento,
#: no el veredicto que `AGENTS.md` («CI Local Obligatorio») declara como
#: fuente de verdad. Convergerlo con la receta canónica es un workitem
#: propio, no una excepción disguise de este guard.
DIRECTORIOS_NO_RECETA: Final[tuple[str, ...]] = ("scripts/hooks",)


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
    raiz_repo: str
    runners: dict[str, str]
    etapas_canonicas: tuple[str, ...]
    #: Scripts de `scripts/` que una persona ejecutaría esperando un
    #: veredicto, como `ruta -> contenido`.
    scripts: dict[str, str] = field(default_factory=dict)
    #: Scripts que `.pipeline.kts` invoca. Se leen del script, no de una
    #: lista: un guard que lleva su propia lista de fragmentos solo vigila
    #: los fragmentos que ya conocía.
    fragmentos: frozenset[str] = frozenset()
    hubo_error: bool = False
    error: str = ""


# =====================================================================
# CAPA PURA — de aqui abajo no se lee disco.
# =====================================================================


def sin_comentarios_linea(linea: str, marca: str) -> str:
    """Una línea de shell o de Kotlin sin su comentario.

    Un comentario empieza por la marca **al inicio de la línea o tras un
    espacio**, nunca en cualquier posición: partir por el primer `#` rompe
    `echo "## CI Summary"` y partir por el primer `//` rompe
    `https://mise.jdx.dev`. La misma regla sirve para los dos lenguajes
    porque los dos la tienen, y por eso es una función y no dos.
    """
    pos = linea.find(marca)
    if pos == 0 or (pos > 0 and linea[pos - 1].isspace()):
        return linea[:pos]
    return linea


def logicas_de(contenido: str, marca: str) -> tuple[str, ...]:
    """Las órdenes que un script ejecuta: sin comentarios y sin cortar en dos.

    Las continuaciones con barra invertida se unen ANTES de devolver. Sin
    eso, la invocación canónica de este repo

        mise exec -- pipelinek run --rerun \\
            --db .pipelinek/db.sqlite ... .pipeline.kts

    se leería como dos órdenes, ninguna de las cuales contiene a la vez
    `pipelinek` y `.pipeline.kts`, y el invariante concluiría que el
    script no delega cuando sí delega.
    """
    unidas: list[str] = []
    buffer = ""
    for cruda in contenido.splitlines():
        limpia = sin_comentarios_linea(cruda, marca).rstrip()
        if not limpia.strip():
            continue
        buffer = f"{buffer} {limpia}".strip() if buffer else limpia
        if limpia.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue
        unidas.append(buffer)
        buffer = ""
    if buffer:
        unidas.append(buffer)
    return tuple(unidas)


#: `pytest` como palabra suelta precedida de inicio, espacio o barra.
#: `pytest-cov` también cuenta, y debe: es la misma corrida.
_INVOCA_PYTEST: Final = re.compile(r"(?:^|[\s/])pytest(?:\s|$)")

#: Un `scripts/<algo>.sh` dentro de una orden, sea invocado con `bash`, sea
#: con su ruta relativa. No matchea `scripts/check_x.py`: un contrato en
#: Python invocado directamente por la receta no es un script de shell.
_RUTA_SCRIPT: Final = re.compile(r"[\w./-]*scripts/[\w.-]+\.sh")


def ejecuta_pytest(contenido: str) -> bool:
    """¿El script lanza pytest en algún momento?"""
    return any(_INVOCA_PYTEST.search(orden) for orden in logicas_de(contenido, "#"))


def delega_en_canonica(contenido: str) -> bool:
    """¿El script entrega su veredicto a la receta canónica?

    Se exige que `pipelinek` y el nombre de la receta estén en la **misma
    orden**: `pipelinek` sin `.pipeline.kts` sería un pipeline distinto, y
    `.pipeline.kts` sin `pipelinek` sería un fichero que se pasa como
    argumento de otra cosa.
    """
    return any(
        "pipelinek" in orden and RECETA_CANONICA in orden for orden in logicas_de(contenido, "#")
    )


def scripts_invocados_por(canonica: str) -> frozenset[str]:
    """Qué scripts de shell invoca la receta canónica.

    Se lee del script y no de una constante: los fragmentos de la receta
    cambian con ella, y una lista aparte sólo sabría de los que ya había.
    """
    return frozenset(
        ruta for orden in logicas_de(canonica, "//") for ruta in _RUTA_SCRIPT.findall(orden)
    )


def evaluar_recetas(informe: InformeRunners) -> tuple[Problema, ...]:
    """C1. Cada runner remoto invoca la receta canónica **en un paso**.

    Dos decisiones, y las dos se ganaron midiendo:

    *Se busca el nombre del script, no una lista de comandos.* Exigir que el
    remoto mencione «lint» y «pytest» es aceptar una reimplementación
    parcial que se queda sin los contratos que la local sí ejecuta. Esa es
    exactamente la divergencia que este bloque cierra.

    *Se buscan los PASOS, no el fichero.* Un guard que busca `.pipeline.kts`
    en el contenido entero encuentra la cadena en el comentario que explica
    que se usa, y aprueba un workflow que ejecuta otra cosa. MEDIDO: las
    cinco mutaciones de este contrato dieron `rc=0` por eso — el defecto
    estaba en el diseño del invariante, no en los tests.

    Y se exigía lo segundo por el primero: si el remoto reimplementa la
    receta, la cadena aparece en el fichero pero no en ningún paso.
    """
    problemas: list[Problema] = []
    for ruta in sorted(informe.runners):
        pasos = pasos_ejecutables(informe.runners[ruta])
        if any(RECETA_CANONICA in paso for paso in pasos):
            continue
        problemas.append(
            Problema(
                CODIGO_RECETA_PROPIA,
                f"{ruta} no ejecuta {RECETA_CANONICA}: sus pasos no la invocan. "
                f"Si un runner remoto produce PASS y la receta local produce FAIL, "
                f"nadie sabe cuál de las dos estaba mintiendo",
            )
        )
    return tuple(problemas)


def evaluar_portabilidad(informe: InformeRunners) -> tuple[Problema, ...]:
    """C2. La receta canónica sabe dónde está, y no está atada a esta máquina.

    Son dos condiciones, y las dos verificables sin heurística sobre `/`:

    **Resuelve la raíz.** Un script que no lee ni el entorno ni el `user.dir`
    no tiene manera de saber dónde está el checkout, así que sus rutas sólo
    pueden ser elcwd del motor — que no es el repo — o absolutas a una
    máquina concreta.

    **No contiene esta raíz.** Es la forma exacta del problema: antes
    llevaba diez apariciones de `/var/mnt/DiscoChino2-fast/...`. Se compara
    contra la raíz real del repo, no contra un patrón de «parece
    absoluta»: `/usr/bin/uv` es legítimo y no ata el script a nada.

    La versión primera de este invariante buscaba rutas absolutas dentro de
    `sh(...)` y no veía nada cuando la ruta estaba en una `val` de Kotlin,
    que es justo donde la muevo para arreglar el problema. Un invariante que
    solo mira una sintaxis concreta se puede esquivar cambiando de sintaxis.
    """
    problemas: list[Problema] = []
    if not _RESUELVE_RAIZ.search(informe.canonica):
        problemas.append(
            Problema(
                CODIGO_RUTA_ABSOLUTA,
                f"{informe.receta_canonica} no resuelve la raiz del checkout: "
                f"no lee ni `System.getenv` ni `user.dir`. Sin eso sus rutas solo "
                f"pueden ser el cwd del motor — que no es el repo — o absolutas "
                f"a una maquina concreta",
            )
        )
    raiz = informe.raiz_repo.rstrip("/")
    if raiz and raiz != "/" and raiz in informe.canonica:
        problemas.append(
            Problema(
                CODIGO_RUTA_ABSOLUTA,
                f"{informe.receta_canonica} contiene la ruta de este arbol de "
                f"trabajo ({raiz}): no se puede ejecutar en otra maquina, asi que "
                f"la regla «el remoto invoca la misma receta» es inejecutable",
            )
        )
    return tuple(problemas)


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


def evaluar_una_receta(informe: InformeRunners) -> tuple[Problema, ...]:
    """C4. Quien ejecuta pytest está conectado a la receta canónica.

    La propiedad es **disyuntiva**, y por eso no necesita una lista de
    excepciones:

        ejecuta pytest  ⟹  lo invoca la receta canónica
                          o delega en la receta canónica

    MEDIDO en WI-99. `scripts/ci.sh` era la contraejemplo: ejecutaba
    `ruff`, `ruff format --check` y `pytest` a pelo, y por eso
    `scripts/audit_bundle.sh` —que existe para dar evidencia reproducible a
    una auditoría independiente— producía esa evidencia con un instrumento
    que no ve el CLI ejecutado por subproceso (`cli/commands/runs.py`: 39 %
    frente al 87,96 % de la instrumentada) y sin ejecutar ninguno de los
    cuatro contratos exigibles.

    Las dos ramas son distinguibles sin instrumentar nada:
    `scripts/coverage.sh` ejecuta pytest y es un **fragmento** (la receta
    canónica lo invoca); `scripts/ci.sh` lo ejecuta y **delega** (invoca
    pipelinek con la receta). Un `verify.sh` futuro con pytest a pelo no
    cumple ninguna de las dos, y eso es exactamente lo que se quiere cazar.

    Lo que este invariante NO distingue, y conviene no vender de más: un
    script que sí delega podría ejecutar pytest *además* en su camino
    certificante y seguir cumpliendo. Para verlo haría falta un parser de
    flujo de bash, que es un instrumento mucho mayor que el problema que
    se está cerrando.
    """
    problemas: list[Problema] = []
    for ruta in sorted(informe.scripts):
        contenido = informe.scripts[ruta]
        if not ejecuta_pytest(contenido):
            continue
        if delega_en_canonica(contenido) or ruta in informe.fragmentos:
            continue
        problemas.append(
            Problema(
                CODIGO_RECETA_SUYA,
                f"{ruta} ejecuta pytest por su cuenta y no esta conectado a "
                f"{informe.receta_canonica}: ni lo invoca la receta canonica ni "
                f"delega en ella. Su veredicto se mide con otro instrumento, "
                f"y es el que produce la evidencia de auditoria",
            )
        )
    return tuple(problemas)


def evaluar(informe: InformeRunners) -> tuple[Problema, ...]:
    """C1..C4. Si la medición falló, no dice nada más."""
    if informe.hubo_error:
        return (Problema(CODIGO_RUNNER_INEXISTENTE, f"no se pudo medir: {informe.error}"),)
    return (
        *evaluar_recetas(informe),
        *evaluar_portabilidad(informe),
        *evaluar_etapas(informe),
        *evaluar_una_receta(informe),
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


def pasos_ejecutables(contenido: str) -> list[str]:
    """Los `run:` de un workflow, incluidos los multilínea, sin comentarios.

    Vive aqui y no en el fichero de tests porque el invariante C1 depende de
    el, y duplicar un parser entre el guard y su test es la forma de que
    dejen de contar lo mismo sin que nada lo note.

    Un bloque escalar (`run: |`, `run: >`) termina cuando una línea deja de
    estar más indentada que la clave `run:`. Sin esa condición el parser se
    comería el resto del fichero y devolvería como «pasos» las claves
    siguientes.
    """
    pasos: list[str] = []
    sangria_bloque: int | None = None
    for cruda in contenido.splitlines():
        sin_comentario = sin_comentarios_linea(cruda, "#")
        if not sin_comentario.strip():
            continue
        sangria = len(sin_comentario) - len(sin_comentario.lstrip())
        if sangria_bloque is not None:
            if sangria > sangria_bloque:
                pasos.append(sin_comentario.strip())
                continue
            sangria_bloque = None
        # En YAML un paso de un `steps:` empieza por `- run:`, no por `run:`.
        # Sin quitar el guion, la mitad de los pasos no se veían.
        clave = sin_comentario.strip()
        if clave.startswith("- "):
            clave = clave[2:].strip()
            sangria = len(sin_comentario) - len(sin_comentario[2:].lstrip())
        if not clave.startswith("run:"):
            continue
        valor = clave.split("run:", 1)[1].strip()
        if valor in ("|", ">", "|-", ">-"):
            sangria_bloque = sangria
        elif valor:
            pasos.append(valor)
    return pasos


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


def scripts_de(raiz: Path) -> dict[str, str]:
    """Los scripts de shell de `scripts/`, como `ruta -> contenido`.

    Se descubren por su extensión, no por una lista de nombres: un
    `verify.sh` nuevo tiene que entrar en el contrato el día que se escribe,
    no el día que alguien se acuerde de añadirlo a la lista.

    Se recorre el directorio `scripts/` y no el árbol entero a propósito:
    es donde vive la caja de herramientas local, y donde un fichero escrito
    para ser la verificación llega a ser la receta que alguien ejecuta.
    """
    base = raiz / "scripts"
    if not base.is_dir():
        return {}
    encontrados: dict[str, str] = {}
    for fichero in sorted(base.rglob("*.sh")):
        relativa = fichero.relative_to(raiz).as_posix()
        if any(relativa.startswith(f"{d}/") for d in DIRECTORIOS_NO_RECETA):
            continue
        encontrados[relativa] = fichero.read_text(encoding="utf-8")
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
            raiz_repo=str(raiz),
            runners=runners_de(raiz),
            etapas_canonicas=etapas_de(texto),
            scripts=scripts_de(raiz),
            fragmentos=scripts_invocados_por(texto),
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
        raiz_repo="",
        runners={},
        etapas_canonicas=(),
        hubo_error=True,
        error=mensaje,
    )


def formatear(problemas: tuple[Problema, ...]) -> str:
    if not problemas:
        return (
            "OK: todo runner remoto invoca la receta canónica, "
            "la receta canónica se puede ejecutar fuera de esta máquina, "
            "y ninguna otra receta ejecuta pytest por su cuenta."
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
                        "scripts": sorted(informe.scripts),
                        "fragmentos": sorted(informe.fragmentos),
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
