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
    fragmento que ella invoca, o delega en ella (WI-99);
C5  todo `scripts/check_*.py` lo invoca la receta canónica: un contrato
    exigible no puede desaparecer de ella sin que nada lo note (WI-102).

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

Por qué C5 está aquí y no en un documento
-----------------------------------------
C3 lee las etapas del script, y está bien: leer del script es lo que evita
un guard que vigila una lista paralela. Pero C3 comprobaba que la lista fuera
**legible**, y una lista de etapas vacía por legibilidad es tan válida como
una completa.

MEDIDO en WI-102, con el comando canónico de verdad: se borró el bloque
entero de la etapa `coverage-floors` de `.pipeline.kts` —la que impone los
suelos que `AGENTS.md §6.3` declara exigibles— y el resultado fue

    scripts/check_ci_recipe_parity.py   exit 0   («OK: ...»)
    pytest test_wi98_ci_recipe_parity    37 passed
    la receta, ejecutada de verdad       Pipeline finished with SUCCESS

Cero menciones de `coverage-floors` en su salida, y cero del `VEREDICTO` de
los suelos. Una receta que ejecuta menos se ejecuta igual de bien, y el
instrumento que certifica los contratos no comprobaba que los contratos
estuvieran. C4 exigía que quien ejecuta pytest esté *conectado* a la receta;
nadie exigía que la receta *contenga* los contratos.

Un documento que dijera «la receta ejecuta los contratos» no habría
cambiado nada la próxima vez que alguien borrara una etapa. C5 mira los
ficheros: mira qué hay en `scripts/` y qué invoca `.pipeline.kts`.


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

#: Un contrato exigible existe en `scripts/` y la receta canónica no lo
#: invoca. MEDIDO en WI-102 con la etapa `coverage-floors` borrada.
CODIGO_CONTRATO_HUERFANO: Final = "sg_ci_contrato_huerfano"
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
    #: Contratos exigibles: los `scripts/check_*.py` del repo, como `ruta`.
    #: Se descubren por convención de nombre, no de una constante: un
    #: checker nuevo entra en el contrato el día que se escribe.
    checkers: tuple[str, ...] = ()
    #: De esos, los que `.pipeline.kts` invoca en una orden real.
    checkers_invocados: frozenset[str] = frozenset()
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

#: Un path literal de pytest: un módulo `.py` o un directorio. Los dos
#: seleccionan. `pytest src/` es tan filtrado como `pytest tests/test_x.py`,
#: y reconocer solo el primero haría que el segundo se contara como suite
#: entera.
_PATH_LITERAL: Final = re.compile(r"[\w./*-]+\.py$|[\w./*-]+/$")


#: Verbos de shell que pueden MENCIONAR pytest sin invocarlo.
#:
#: No es la lista de excepciones queWI-99 quito: es una lista de PALABRAS
#: del lenguaje, no de ficheros del repo. Añadir un `verify.sh` nuevo, o un
#: hook nuevo, no la desactualiza. La lista de WI-99 growaba cada vez que
#: aparecía un caso; esta no crece nunca.
#:
#: MEDIDO en WI-100, y lo encontró una mutación, no un test. C4 llevaba dos
#: commits dando VERDE porque el `pre-commit` llevaba una línea de
#: diagnóstico
#:
#:     echo "[pre-commit] smoke: pytest sobre $N_STAGED fichero(s) .py staged"
#:
#: y esa línea tenía las tres cosas que el invariante miraba: la palabra
#: `pytest`, una variable, y estaba en una orden ejecutable. Un guard que
#: confunde un MENSAJE con una EJECUCIÓN no mide qué corre: mide qué se
#: dice.
_VERBOS_DE_MENCION: Final = frozenset(
    {"echo", "printf", "tail", "head", "grep", "cat", "sed", "awk", "test", "read"}
)


#: Palabras que abren una orden de shell sin ser el comando que la ejecuta.
#: `if run_in_toolchain run pytest` empieza por `if` y ejecuta `run_in_toolchain`.
_ABIERTURA_DE_ORDEN: Final = frozenset(
    {"if", "then", "else", "elif", "do", "done", "while", "until", "!", "(", "{", "time"}
)


def _patron_de_invocacion(orden: str) -> re.Match[str] | None:
    """Dónde empieza pytest en una orden que REALMENTE lo ejecuta.

    La regla es «qué comando lanza esta línea», no «qué palabra hay antes
    de pytest». Se probó lo segundo y no sirve: en

        echo "[pre-commit] smoke: pytest sobre $N_STAGED fichero(s) .py staged"

    la palabra anterior a `pytest` es `smoke:`, no `echo`, así que la regla
    de proximidad daba verde a un mensaje. Un verbo de shell que no
    ejecuta programas no puede estar invocando pytest, y eso decide sin
    depender de lo que haya escrito alrededor.
    """
    m = _INVOCA_PYTEST.search(orden)
    if m is None:
        return None
    comando = next((t for t in orden.split() if t not in _ABIERTURA_DE_ORDEN), None)
    if comando is not None and comando in _VERBOS_DE_MENCION:
        return None
    return m


def es_path_de_pytest(token: str) -> bool:
    """¿Este argumento de la orden de pytest selecciona ficheros?

    Tres formas, y las tres están en el repo de verdad:

    * ``tests/test_x.py`` — un path literal.
    * ``$STAGED_PY`` — una variable que los expande. Es la que usa
      `scripts/hooks/pre-commit`, y la primera versión de este invariante
      no la veía porque no sabía leer un nombre de variable como un path.
    * ``"$RC"`` — entrecomillado, que en shell es lo mismo que `$RC`.

    Lo que NO cuenta es lo que empieza por `-`. Y esa restricción es la que
    hace el invariante utilizable: sin ella, `--cov=skillgraph` y
    `--cov-config="$RC"` aportarían dos tokens más y TODA invocación
    parecería filtrada. Un invariante que se cumple siempre no vigila nada,
    y se nota tarde.
    """
    limpio = token.strip("\"'")
    if limpio.startswith("-"):
        return False
    if limpio.startswith("$"):
        return True
    return bool(_PATH_LITERAL.search(limpio))


#: Sufijos que ya delatan un script de shell.
_SUFIJOS_SCRIPT: Final = frozenset({".sh", ".bash"})

#: Un shebang de shell. Es la SEGUNDA via de descubrimiento, y hace falta
#: porque `scripts/hooks/pre-commit` y `scripts/hooks/pre-push` no tienen
#: extensión: se llaman así porque git los busca con ese nombre.
#:
#: MEDIDO en WI-100, y es la segunda vez que este guard no ve lo que vigila
#: por culpa del descubrimiento. En WI-99, `git ls-files | grep '\.sh$'`
#: dejó fuera los dos hooks al inventariarlos. En WI-100, el `rglob("*.sh")`
#: del propio checker los dejó fuera otra vez, y el invariante daba verde
#: sin haber mirado nunca el fichero. Un guard que solo descubre una
#: sintaxis no vigila la otra: se esquiva cambiando de sintaxis, que es la
#: misma trampa de WI-98 por el otro lado.
_SHEBANG_SHELL: Final = re.compile(r"^#!.*(?:/env\s+)?(?:ba)?sh\b")


def es_script_shell(contenido: str, sufijo: str) -> bool:
    """¿Este fichero es un script de shell, por extensión o por shebang?"""
    if sufijo in _SUFIJOS_SCRIPT:
        return True
    lineas = contenido.splitlines()
    return bool(lineas) and bool(_SHEBANG_SHELL.search(lineas[0]))


def rutas_de_script(contenido: str, marca: str) -> frozenset[str]:
    """Qué scripts de shell invoca un fichero, leídos de sus órdenes."""
    return frozenset(
        ruta for orden in logicas_de(contenido, marca) for ruta in _RUTA_SCRIPT.findall(orden)
    )


#: Las CADENAS de una orden, y solo ellas. Se quitan antes de buscar
#: invocaciones, y el motivo esta medido en B21: `scripts/diagnose_pytest_run.sh`
#: —un script que IMPRIME el diagnostico de una corrida y no lanza pytest en
#: ningun momento— daba `sg_ci_receta_suya` con la linea
#: `echo "=== coverage: resumen de pytest ==="`. El predicado decia «este
#: script ejecuta pytest» mirando la palabra, no la orden, que es justo lo que
#: el docstring de `filtra_por_ficheros` dice que no hace.
#:
#: Se quitan las cadenas y no las lineas que empiezan por `echo`, porque
#: `echo a && pytest` SI invoca pytest y un filtro por primer token dejaria
#: pasar justo el caso que este invariante existe para cazar.
_CADENA: Final = re.compile(r'"[^"]*"|\'[^\']*\'')


def ejecuta_pytest(contenido: str) -> bool:
    """¿El script lanza pytest en algún momento?

    Se mira la orden SIN sus cadenas, no el texto entero: un `echo` que
    menciona pytest no lo ejecuta, y un guard que lo creyera acabaria
    marcando scripts que solo imprimen —MEDIDO, ver `_CADENA`—.
    """
    return any(
        _INVOCA_PYTEST.search(_CADENA.sub("", orden)) for orden in logicas_de(contenido, "#")
    )


def filtra_por_ficheros(contenido: str) -> bool:
    """¿Alguna invocación de pytest SELECCIONA paths?

    Un hook que corre `pytest -q $STAGED_PY` no emite un veredicto sobre el
    repo: emite uno sobre lo que alguien tiene a medio escribir. Es un
    filtro de evento, no una medición, y por eso queda fuera de C4 sin
    necesitar una lista de excepciones que lo diga.

    MEDIDO en WI-100: `scripts/hooks/pre-commit` seleccionaba los `.py`
    staged y **no se los pasaba** — corría la suite entera (2636 tests,
    124 s) anunciando «smoke, ~10 s». El selector existía; la instrucción
    no. Los dos hechos son incompatibles y solo uno estaba escrito.

    Solo se miran órdenes que INVOCAN pytest, no las que lo mencionan; ver
    `_patron_de_invocacion` y el motivo, que es un falso positivo que hizo
    que este invariante diera verde dos commits seguidos.
    """
    return any(
        es_path_de_pytest(token)
        for orden in logicas_de(contenido, "#")
        if _patron_de_invocacion(orden) is not None
        for token in orden.split()
    )


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
    return rutas_de_script(canonica, "//")


#: Ruta a un contrato exigible dentro de una orden. Deliberadamente `*.py` y
#: deliberadamente `check_`: es la convención que declara C5, y lo que el
#: guard vigila es lo que la convención dice, no lo que el guard quisiera.
#:
#: El tramo ENTRE `scripts/` y `check_` admite carpetas a proposito.
#: `checkers_de` descubre con `rglob`, o sea tambien en subdirectorios, asi
#: que un lector que no los aceptara daria un **falso positivo**: el checker
#: `scripts/sub/check_x.py` apareceria en el conjunto de contratos y no
#: apareceria nunca en el de invocados, porque su ruta no matchea. Se
#: reportaria como huerfano un contrato que la receta ejecuta.
#:
#: MEDIDO en WI-102, al implementar C5: asi estaba la primera version, y lo
#: encontro la mutacion M3 del bloque, no un test. Es la tercera vez que un
#: guard descubre por una sintaxis y lee por otra — WI-99 con los hooks sin
#: extension, WI-100 con el descubrimiento por shebang, WI-102 aqui.
_RUTA_CHECKER: Final = re.compile(r"[\w./-]*scripts/(?:[\w.-]+/)*check_[\w.-]+\.py")


def checkers_invocados_por(canonica: str) -> frozenset[str]:
    """Qué contratos exigibles invoca la receta canónica, en órdenes reales.

    Se lee de las órdenes sin comentarios, como el resto: un checker
    mencionado en el comentario que explica una etapa **borrada** es
    exactamente el caso que este guard tiene que ver. MEDIDO en WI-102, y
    es la misma trampa que M7 de WI-100 y M8 de WI-101: un nombre de
    fichero en un texto no es una ejecución.
    """
    return frozenset(
        ruta for orden in logicas_de(canonica, "//") for ruta in _RUTA_CHECKER.findall(orden)
    )


def checkers_de(raiz: Path) -> tuple[str, ...]:
    """Los contratos exigibles del repo: `scripts/check_*.py`, ordenados.

    Se descubre por convención y no de una constante. Un guard que lleva su
    propia lista de contratos solo vigila los que ya conocía — que es
    exactamente el fallo que WI-92 encontró en la redacción de su propia
    documentacion, y el que este bloque lleva dos veces ya.
    """
    base = raiz / "scripts"
    if not base.is_dir():
        return ()
    return tuple(
        f"scripts/{p.relative_to(base).as_posix()}" for p in sorted(base.rglob("check_*.py"))
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
    """C4. Quien emite veredicto sobre el REPO está conectado a la receta.

    La propiedad es **disyuntiva**, y por eso no necesita una lista de
    excepciones:

        pytest sobre el repo entero  ⟹  lo invoca la receta canónica
                                     o delega en ella

    MEDIDO en WI-99. `scripts/ci.sh` era la contraejemplo: ejecutaba
    `ruff`, `ruff format --check` y `pytest` a pelo, y por eso
    `scripts/audit_bundle.sh` —que existe para dar evidencia reproducible a
    una auditoría independiente— producía esa evidencia con un instrumento
    que no ve el CLI ejecutado por subproceso (`cli/commands/runs.py`: 39 %
    frente al 87,96 % de la instrumentada) y sin ejecutar ninguno de los
    cuatro contratos exigibles.

    MEDIDO en WI-100, y es lo que hace la regla precisa. La condición es
    «pytest **sobre el repo**», no «pytest». Un hook que corre
    `pytest -q $STAGED_PY` filtra por lo que alguien tiene a medio escribir:
    es un filtro de evento, no un veredicto, y queda fuera sin necesitar una
    lista que lo diga. En WI-99 `scripts/hooks/` estaba excluido por
    constante, y esa constante era una puerta trasera: en cuanto el pre-push
    dejó de delegar, la exclusión tenía que crecer para seguir cubriendo un
    caso que ya no era el mismo. Una propiedad que hay que mantener al día
    no es una propiedad, es una suscripción.

    Lo que este invariante NO distingue, y conviene no vender de más: un
    script que sí delega podría ejecutar pytest *además* en su camino
    certificante y seguir cumpliendo. Para verlo haría falta un parser de
    flujo de bash, que es un instrumento mucho mayor que el problema que
    se está cerrando.
    """
    problemas: list[Problema] = []
    for ruta in sorted(informe.scripts):
        contenido = informe.scripts[ruta]
        if not ejecuta_pytest(contenido) or filtra_por_ficheros(contenido):
            continue
        if delega_en_canonica(contenido) or ruta in informe.fragmentos:
            continue
        problemas.append(
            Problema(
                CODIGO_RECETA_SUYA,
                f"{ruta} ejecuta pytest sobre el repo entero y no esta conectado "
                f"a {informe.receta_canonica}: ni lo invoca la receta canonica "
                f"ni delega en ella. Su veredicto se mide con otro instrumento, "
                f"y el suyo es el que puede dar verde un paquete que no "
                f"cumple los suelos que el propio AGENTS.md declara",
            )
        )
    return tuple(problemas)


def evaluar_contratos_de_la_receta(informe: InformeRunners) -> tuple[Problema, ...]:
    """C5. La receta canónica ejecuta todos los contratos exigibles.

    MEDIDO en WI-102. Se borró el bloque entero de la etapa
    `coverage-floors` de `.pipeline.kts` y no lo notó ni el guard de paridad
    (exit 0), ni sus 37 tests, ni la propia receta al ejecutarse
    (`Pipeline finished with SUCCESS`, con cero menciones de la etapa y
    cero de su `VEREDICTO`). La receta seguía siendo la fuente de verdad
    y ya no contenía la mitad de lo que la fuente de verdad declara.

    La forma es **sin lista**, y esa es la decisión que importa. Una lista
    de contratos obligatorios dentro del guard es la misma trampa que
    `DIRECTORIOS_NO_RECETA` en WI-99: obliga a mantener enumerado lo que
    el guard debería comprobar solo, y el mantenimiento es el trabajo que
    se quiere automatizar. Aquí el conjunto sale del repo
    (`scripts/check_*.py`), así que un checker nuevo entra en el contrato
    sin tocar nada, y borrar una etapa se detecta porque el checker que
    invocaba deja de estar invocado.

    Cubre también el caso inverso, que hasta WI-102 era invisible:
    **escribir un checker y no enchufarlo en la receta**. Es un guard que
    no guarda nada, con la misma forma exacta que un guard real.

    Lo que NO cubre, y se declara en vez de disimularse: el descubrimiento
    es por la convención `check_*.py`. Un contrato escrito en un fichero
    con otro nombre queda fuera del invariante, igual que un script de
    shell que no se llama `*.sh` quedaba fuera de C3 antes de WI-100. Es
    el mismo compromiso: la convención es del repo, y el guard vigila lo
    que la convención declara, no lo que el guard quisiera que hubiera.
    """
    if informe.hubo_error:
        return ()
    huerfanos = tuple(c for c in informe.checkers if c not in informe.checkers_invocados)
    if not huerfanos:
        return ()
    return (
        Problema(
            CODIGO_CONTRATO_HUERFANO,
            f"estos contratos exigibles existen en scripts/ pero {informe.receta_canonica} "
            f"no los invoca en ninguna orden: {', '.join(huerfanos)}. Una receta que "
            "ejecuta menos se ejecuta igual de bien: borrarle una etapa no la rompe, "
            "simplemente deja de comprobar lo que su nombre dice comprobar.",
        ),
    )


def evaluar(informe: InformeRunners) -> tuple[Problema, ...]:
    """C1..C5. Si la medición falló, no dice nada más."""
    if informe.hubo_error:
        return (Problema(CODIGO_RUNNER_INEXISTENTE, f"no se pudo medir: {informe.error}"),)
    return (
        *evaluar_recetas(informe),
        *evaluar_portabilidad(informe),
        *evaluar_etapas(informe),
        *evaluar_una_receta(informe),
        *evaluar_contratos_de_la_receta(informe),
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

    MEDIDO en WI-100: hasta aquí se excluía `scripts/hooks/` por constante.
    La exclusión desaparece —no porque el hook se conforme, sino porque la
    propiedad se afinó hasta que el hook no necesita una. Un hook que
    delega (pre-push) cumple por la vía normal; uno que filtra por ficheros
    (pre-commit) cumple por la suya. Y `scripts/hooks/` entra en el
    contrato, que es donde tenía que estar desde el principio.
    """
    base = raiz / "scripts"
    if not base.is_dir():
        return {}
    scripts: dict[str, str] = {}
    for fichero in sorted(base.rglob("*")):
        if not fichero.is_file() or "__pycache__" in fichero.parts:
            continue
        try:
            contenido = fichero.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if es_script_shell(contenido, fichero.suffix):
            scripts[fichero.relative_to(raiz).as_posix()] = contenido
    return scripts


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
            checkers=checkers_de(raiz),
            checkers_invocados=checkers_invocados_por(texto),
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
        # El mensaje dice LO MISMO que el guard mide. WI-101 closed el hueco
        # de que un instrumento anunciara un exit code que no significaba
        # nada, y la version corta de ese mismo defecto es un "OK" que no
        # menciona el quinto contrato: el lector se queda creyendo que hay
        # cuatro, y vuelve a no saber que el quinto se puede borrar.
        return (
            "OK: todo runner remoto invoca la receta canónica, "
            "la receta canónica se puede ejecutar fuera de esta máquina, "
            "ninguna otra receta ejecuta pytest por su cuenta, "
            "y la receta ejecuta todos los contratos exigibles de scripts/."
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
