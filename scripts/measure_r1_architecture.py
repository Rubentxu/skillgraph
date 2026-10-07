#!/usr/bin/env python3
"""R1 — las fronteras arquitectónicas como leyes ejecutables.

QUÉ MIDE, Y POR QUÉ NO ES «UN AUDIT MÁS»
========================================

R1 pide cinco cosas que hoy son **declaraciones**:

    god modules > 800               = 0
    public complexity >= threshold  = 0
    domain → SQL                    = 0
    domain → platform               = 0
    normative refs rotas            = 0

Y el punto del bloque no es medirlas: es que **una propiedad que llegó a
cero no vuelve a convertirse en advertencia**. Un audit que informa y no
bloquea es una descripción, no una ley.

# LAS CINCO PREGUNTAS, Y POR QUÉ ESTAS CINCO

    P1  EL RATCHET DE TAMAÑO EXISTE Y BLOQUEA
    P2  LA COMPLEJIDAD PÚBLICA ESTA CERRADA
    P3  EL DOMINIO NO HABLA SQL
    P4  EL DOMINIO NO IMPORTA PLATFORM
    P5  LAS REFERENCIAS NORMATIVAS EXISTEN

**P1 Y P2 SON LAS QUE DICEN SI R1 ESTÁ HECHO.** El objetivo pide que una
propiedad que llegó a cero **no vuelva a convertirse en advertencia**. Eso
no se cumple con un script que informa: se cumple con un gate que sale
distinto de cero. Se mide preguntando por el **código de salida** del
auditor, no por lo que imprime.

**P3 Y P4 TIENEN UNA TRAMPA QUE YA LA PAGUÉ UNA VEZ.** Un `grep` de
`sqlite3` en `src/skillgraph/knowledge/` marca `knowledge_controller.py`
—que importa `sqlite3` para traducir `IntegrityError`— y también marcaría
`errors.py`, `engine.py` y `runcontroller.py`, donde la palabra aparece
**solo dentro de docstrings**. Tres de cuatro serían falsos positivos, y
un guard que señala la mitad de las cosas correctas entrena a ignorar el
guard. Aquí se cuenta **código**, no prosa: se descartan docstrings y
comentarios por AST.

**P5 ES LA QUE MÁS FÁCIL ES DAR POR BUENA.** `05-SPEC`, `06-SPEC`,
`ADR-0028`, `ADR-0030` se citan en el repo; lo que hay que comprobar es
que **existen y están versionadas**. Una cita a un documento inexistente
no es una cita: es una afirmación que no se puede contrastar.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

#: Los paquetes que son DOMINIO. `platform/` es el adapter: que él hable
#: SQL es su trabajo, y por eso no se cuenta.
DOMINIO = ("knowledge", "core", "runtime", "handoff", "agent", "workflow", "dsl")

#: Umbral del ratchet, el mismo que escribe el objetivo.
MAX_LOC = 800


def _modulos_de(dominio: str) -> list[Path]:
    base = SRC / dominio
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


# ---------------------------------------------------------------------------
# Lo que cuenta como «hablar SQL» y lo que NO cuenta
# ---------------------------------------------------------------------------


def _nombres_sql_en_ejecucion(ruta: Path) -> set[str]:
    """Nombres que el MÓDULO USA, no los que menciona.

    Se recorre el AST y se miran los nodos de código real. Un `docstring`
    es un `Expr` cuyo valor es una constante: se salta. Un comentario no
    aparece en el AST: se salta por construcción. Y un `import sqlite3`
    en la cabecera **sí cuenta**, porque es código.

    La razón de hacerlo así y no con `grep` está en el docstring del
    módulo: `errors.py`, `engine.py` y `runcontroller.py` nombran
    `sqlite3` en prosa, y un guard que las señala está midiendo prosa.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    hallados: set[str] = set()

    for nodo in ast.walk(arbol):
        # `import sqlite3` / `from sqlite3 import X`
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.split(".")[0] == "sqlite3":
                    hallados.add(f"import sqlite3 (linea {nodo.lineno})")
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] == "sqlite3":
                hallados.add(f"from sqlite3 import ... (linea {nodo.lineno})")
        # `except sqlite3.IntegrityError` / `sqlite3.IntegrityError(...)`
        elif isinstance(nodo, ast.Attribute):
            raiz = nodo
            while isinstance(raiz, ast.Attribute):
                raiz = raiz.value
            if isinstance(raiz, ast.Name) and raiz.id == "sqlite3":
                hallados.add(f"sqlite3.{nodo.attr} (linea {nodo.lineno})")
        # `cursor.execute(...)`, `conn.executescript(...)`, `.executemany`
        elif isinstance(nodo, ast.Call):
            func = nodo.func
            if isinstance(func, ast.Attribute) and func.attr in {
                "execute",
                "executemany",
                "executescript",
            }:
                hallados.add(f".{func.attr}() (linea {nodo.lineno})")

    return hallados


def _importa_platform(ruta: Path) -> set[str]:
    """Imports REALES hacia `skillgraph.platform`, por AST.

    **`platform.ports` COMPLETO es el puerto, y es la excepción
    declarada.** El objetivo llama `ports/RevisionRegistry`, y lo que hay
    detrás de `platform/ports/` son `Protocol` y DTOs, no implementación:
    `StoredClaim`, `AgentAdapter`, `RepositoryPort`. Contarlos sería marcar
    la inyección de dependencias como una fuga, que es medir lo contrario
    de lo que dice el nombre.

    Lo que se cuenta es el resto de `platform`: `storage`, `schema`,
    `migrations`. Si el dominio importa la implementación, la frontera es
    de adorno.

    **Y LOS IMPORTS DE `if TYPE_CHECKING` NO CUENTAN.** `observation.py`
    importa `Storage` ahi, y en runtime ese import no existe: no abre una
    conexion ni puede meter la implementacion dentro del dominio. Contarlo
    haria que el guard pidiera borrar el bloque de tipos, que es lo
    correcto — y borrarlo haria que el type-checker dejara de saber que hay
    un `Storage` ahi. Es el mismo criterio que aplica
    `check_architecture_ratchet.py`, y estan juntos a proposito: un guard y
    su contrasalto que no compartan el criterio miden dos cosas distintas.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    solo_tipos: set[int] = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.If):
            continue
        prueba = nodo.test
        nombre = prueba.id if isinstance(prueba, ast.Name) else getattr(prueba, "attr", "")
        if nombre != "TYPE_CHECKING":
            continue
        for hijo in ast.walk(nodo):
            solo_tipos.add(getattr(hijo, "lineno", -1))

    hallados: set[str] = set()
    for nodo in ast.walk(arbol):
        if getattr(nodo, "lineno", -1) in solo_tipos:
            continue
        if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").startswith(
            "skillgraph.platform"
        ):
            if nodo.module == "skillgraph.platform.ports" or (nodo.module or "").startswith(
                "skillgraph.platform.ports."
            ):
                continue
            hallados.add(f"{nodo.module} (linea {nodo.lineno})")
        elif isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.startswith("skillgraph.platform") and not alias.name.startswith(
                    "skillgraph.platform.ports"
                ):
                    hallados.add(f"{alias.name} (linea {nodo.lineno})")
    return hallados


# ---------------------------------------------------------------------------
# Las cinco preguntas
# ---------------------------------------------------------------------------


def p1_el_ratchet_existe_y_bloquea() -> tuple[bool, str]:
    """¿Hay un ratchet de tamaño que **haga fallar** la construcción?

    Y la parte que hace que R1 sea R1: **no basta con que el script
    exista**. Se ejecuta y se mira su **código de salida**. Un auditor que
    imprime «2 módulos grandes» y sale 0 es una descripción del futuro,
    no una ley sobre el presente.
    """
    script = RAIZ / "scripts" / "check_architecture_ratchet.py"
    if not script.exists():
        return False, (
            "NO EXISTE scripts/check_architecture_ratchet.py. Sin un gate que "
            "salga distinto de cero, «god modules > 800 = 0» es un deseo."
        )
    proc = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, cwd=str(RAIZ)
    )

    # **ESTO NO ES «EL ARBOL CUMPLE O NO CUMPLE».** Un gate que devuelve
    # `rc=0` sobre un árbol limpio no demuestra que bloquee: un script que
    # devuelve siempre `rc=0` da lo mismo. La diferencia hay que medirla
    # DÁNDOLE UN CASO QUE DEBE DAR ROJO, y eso es lo unico que separa una
    # ley de una descripcion.
    #
    # La primera version de esta pregunta hacia exactamente eso mal:
    # `if rc != 0: return False` decia «el ratchet bloquea» al ver un rojo,
    # que es al reves — un gate que SI bloquea da rojo cuando hay deuda.
    if proc.returncode != 0:
        return False, (
            f"el ratchet da ROJO sobre el arbol actual (rc={proc.returncode}): "
            "todavia hay incumplimientos, luego R1 no ha cerrado"
        )

    bloquea, detalle = _el_ratchet_da_rojo()
    if bloquea:
        return True, (
            "el ratchet sale 0 sobre el arbol que cumple Y da rojo ante un "
            "modulo de 900 lineas: es una ley, no una descripcion. " + detalle
        )
    return False, (
        "el ratchet sale 0 sobre el arbol que cumple, pero **no se pone rojo** "
        "ante un modulo sobre el umbral: no bloquea. " + detalle
    )


def _el_ratchet_da_rojo() -> tuple[bool, str]:
    """¿El ratchet detecta un módulo sobre el umbral? Medido con un árbol real.

    Se construye en `tempfile` copiando `src/` y añadiendo un módulo de 900
    líneas. **POR QUÉ UN ÁRBOL DE VERDAD:** el gate lee el repo, y para
    probar que lee hay que darle algo. Un test que solo mirara el `return`
    probaría que el script se ejecuta, no que mide.
    """
    import shutil
    import tempfile

    script = RAIZ / "scripts" / "check_architecture_ratchet.py"
    with tempfile.TemporaryDirectory(prefix="r1_ratchet_") as tmp:
        raiz = Path(tmp) / "repo"
        (raiz / "src" / "skillgraph" / "grande").mkdir(parents=True)
        shutil.copytree(SRC / "knowledge", raiz / "src" / "skillgraph" / "knowledge")
        grande = raiz / "src" / "skillgraph" / "grande" / "god.py"
        grande.write_text(
            "\n".join(f"def f{i}(x: int) -> int:\n    return x + {i}" for i in range(450)),
            encoding="utf-8",
        )
        if len(grande.read_text(encoding="utf-8").splitlines()) <= MAX_LOC:
            return False, "el contraejemplo NO supera el umbral: el test miente"
        proc = subprocess.run(
            [sys.executable, str(script), "--raiz", str(raiz)],
            capture_output=True,
            text=True,
        )
        salida = proc.stdout + proc.stderr
        nombro = "god.py" in salida
        if proc.returncode != 0 and nombro:
            return True, f"rc={proc.returncode} y nombro el fichero."
        if proc.returncode == 0:
            return False, "rc=0 ante un god module: el gate no mide."
        return (
            False,
            f"rc={proc.returncode} pero NO nombro el fichero: quien lo ve no sabe qué abrir.",
        )


def p2_la_complejidad_publica_esta_cerrada() -> tuple[bool, str]:
    """¿Alguna función PÚBLICA con complejidad ciclomática >= 20?

    La medición es por AST, y el umbral es el que ya usa el repo en el
    gate de hotspots (`cc>=20` sobre funciones públicas).
    """
    hotspots: list[str] = []
    for dominio in DOMINIO:
        for ruta in _modulos_de(dominio):
            try:
                arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
            except SyntaxError:
                continue
            for nodo in ast.walk(arbol):
                if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if nodo.name.startswith("_"):
                    continue
                cc = _complejidad(nodo)
                if cc >= 20:
                    hotspots.append(f"{ruta.relative_to(RAIZ)}:{nodo.name} (cc={cc})")
    return not hotspots, (
        "ninguna funcion publica con cc>=20"
        if not hotspots
        else "hotspots publicos: " + "; ".join(sorted(hotspots))
    )


def _complejidad(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Complejidad ciclomática de McCabe, sin dependencias externas."""
    cc = 1
    for hijo in ast.walk(nodo):
        if isinstance(hijo, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            cc += 1
        elif isinstance(hijo, ast.BoolOp):
            cc += len(hijo.values) - 1
        elif isinstance(hijo, ast.IfExp):
            cc += 1
        elif isinstance(hijo, ast.comprehension):
            cc += 1 + len(hijo.ifs)
        elif isinstance(hijo, ast.Assert):
            cc += 1
        elif isinstance(hijo, ast.Match):
            cc += len([c for c in hijo.cases if c.guard is not None]) + 1
    return cc


def p3_el_dominio_no_habla_sql() -> tuple[bool, str]:
    """Cero uso de SQL en el dominio, contado por AST.

    **Y ESTA ES LA QUE TIENE LA TRAMPA DE LOS DOCSTRINGS.** Un `grep` de
    `sqlite3` en `knowledge/`, `core/` y `runtime/` marca cuatro
    ficheros, y **tres de los cuatro solo lo nombran en prosa**:
    `errors.py` habla de la traducción, `engine.py` y `runcontroller.py`
    explican por qué ya no reciben una conexión. Un guard que los señale
    está midiendo la documentación.

    Lo que se cuenta: `import sqlite3`, `sqlite3.<algo>` y
    `.execute()/.executemany()/.executescript()` en código.
    """
    fugas: list[str] = []
    for dominio in DOMINIO:
        for ruta in _modulos_de(dominio):
            for uso in sorted(_nombres_sql_en_ejecucion(ruta)):
                fugas.append(f"{ruta.relative_to(RAIZ)}: {uso}")
    return not fugas, (
        "el dominio no usa SQL en codigo (los docstrings NO cuentan)"
        if not fugas
        else "fugas de SQL al dominio: " + "; ".join(fugas)
    )


def p4_el_dominio_no_importa_platform() -> tuple[bool, str]:
    """Cero imports del dominio hacia `platform`, salvo el puerto.

    `skillgraph.platform.ports` es el **puerto** y está permitido — es lo
    que el objetivo llama `ports/RevisionRegistry`. Lo que se cuenta es el
    resto: si el dominio importa la implementación, la frontera es de
    adorno.
    """
    fugas: list[str] = []
    for dominio in DOMINIO:
        for ruta in _modulos_de(dominio):
            for uso in sorted(_importa_platform(ruta)):
                fugas.append(f"{ruta.relative_to(RAIZ)}: {uso}")
    return not fugas, (
        "el dominio no importa la implementacion de platform (ports si)"
        if not fugas
        else "dependencias dominio -> platform: " + "; ".join(fugas)
    )


def _existe_la_autoridad(nombre: str) -> bool:
    """¿Existe en el árbol un documento que sea ESTA autoridad?

    Se busca por el **nombre citado**, no por prefijo laxo: `ADR-0028` esta
    resuelto si hay un fichero que empiece por `ADR-0028`, y `06-SPEC` si hay
    uno que empiece por `06-SPEC`. Un prefijo más corto (`0`) daría un
    positivo falso, que es peor que un negativo: un guard que da por buena
    una referencia rota es exactamente el defecto que este bloque cierra.

    **`external/` CUENTA, y es donde vive la mayoría.** El bundle está ahí
    **fuera de git por decisión del repo** (lo dice `.gitignore`), no
    porque valga poco: `external/blueprint-v1/` es el **source of truth**
    de `AGENTS.md` §0. Exigir que esté versionado sería exigir que se
    deshaga una decisión de gobernanza, y en este repo la autoridad
    normativa es precisamente lo que no viaja con el código.

    **Y UN DIRECTORIO ES UNA AUTORIDAD TANTO COMO UN FICHERO.**
    `blueprint-v1` es el caso: son 12 documentos dentro de una carpeta, y
    la cita es al conjunto. Buscar solo ficheros marca la referencia
    normativa **más importante del repo** como rota, que es peor que no
    buscarla: entrena a leer la salida del guard sin creerla.
    """
    raices = (
        RAIZ,
        RAIZ / "external",
        RAIZ / "docs",
        RAIZ / "decisions",
        RAIZ / "specs",
    )
    for directorio in raices:
        if not directorio.is_dir():
            continue
        for p in directorio.rglob("*"):
            # Un fichero suelto, o un directorio con contenido: ambos son
            # una autoridad. Un directorio VACIO no lo es.
            if p.is_file() and p.name.startswith(nombre):
                return True
            if p.is_dir() and p.name.startswith(nombre) and any(p.iterdir()):
                return True
    return False


def p5_las_referencias_normativas_existen() -> tuple[bool, str]:
    """Toda referencia normativa citada EXISTE en el árbol.

    Se citan specs (`NN-SPEC-*`), ADRs y blueprints. Una cita a un documento
    que no está en el repo no es una cita: es una afirmación que nadie puede
    contrastar.

    **Y «existe» significa un fichero cuyo nombre empieza por lo citado.** La
    versión importa menos que la existencia aquí: un documento sin versionar es
    una nota, y una cita a una nota es una cita a algo que se puede mover sin
    dejar rastro. Lo que se mide primero es que la autoridad esté.
    """
    import re as _re

    cita = _re.compile(r"\b((?:\d{2}-SPEC-[A-Z0-9-]+)|(?:ADR-\d{4})|(?:blueprint-v1))")
    citadas: set[str] = set()
    for patron in ("*.md", "*.py", "*.yaml", "*.kts"):
        for ruta in RAIZ.glob(patron):
            if ".git" in ruta.parts:
                continue
            try:
                texto = ruta.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            citadas.update(cita.findall(texto))

    # La autoridad normativa vive en el arbol del repo: `external/` esta
    # FUERA de git por decision del repo (el bundle `docs/` no se versiona),
    # luego «versionada» se comprueba contra el arbol, no contra un indice.
    rotas = sorted(n for n in citadas if not _existe_la_autoridad(n))
    return not rotas, (
        f"{len(citadas)} referencias normativas citadas, todas existen"
        if not rotas
        else f"referencias rotas ({len(rotas)}/{len(citadas)}): {rotas}"
    )


PREGUNTAS = (
    p1_el_ratchet_existe_y_bloquea,
    p2_la_complejidad_publica_esta_cerrada,
    p3_el_dominio_no_habla_sql,
    p4_el_dominio_no_importa_platform,
    p5_las_referencias_normativas_existen,
)


def main() -> int:
    print("R1 — las fronteras arquitectonicas como leyes ejecutables")
    print("  (el punto del bloque no es medirlas: es que una propiedad")
    print("   que llego a cero NO vuelva a convertirse en advertencia)\n")

    abiertas = 0
    for fn in PREGUNTAS:
        cerrada, medido = fn()
        etiqueta = "CERRADA" if cerrada else "ABIERTA"
        print(f"  {fn.__name__[:2].upper()}  {etiqueta}  {fn.__doc__.splitlines()[0]}")
        print(f"      medido: {medido}")
        if not cerrada:
            abiertas += 1

    print(f"\nRESULTADO: {abiertas}/{len(PREGUNTAS)} preguntas ABIERTAS")
    if abiertas:
        print("R1 esta ABIERTO: las fronteras son declaraciones, no leyes.")
        return 1
    print("R1 esta cerrado: cada propiedad llega a cero Y el gate bloquea.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
