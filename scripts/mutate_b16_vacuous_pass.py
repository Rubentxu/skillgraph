#!/usr/bin/env python3
"""B16 · el harness de mutacion de los dos PASS sin nada que comparar.

Por que existe
--------------
B15 dejo escrito que siete de las veinte propiedades del gate de 1.0 se deciden
leyendo el arbol, y que sus PASS no se pueden retirar solos. B16 abre las dos
primeras, y las dos **no eran debiles: eran falsas**. MEDIDO, sobre copias del
arbol con el repo real intacto:

    MEDIDO A · se renombra la constante a _CAPABILITY_VERSION en todo src/
      veredicto : PASS
      evidencia : CAPABILITY_VERSION se declara en un solo sitio: []

    MEDIDO B · core/ importa DomainPack de verdad
      veredicto : PASS
      evidencia : core/ no nombra ningun tipo de recurso: se anaden sin tocarlo

La primera es un PASS cuya evidencia dice una lista vacia: un veredicto sobre
la capacidad de contar del propio instrumento, no sobre el proyecto. La segunda
es la fuga de B13 con el signo cambiado —alli se leian literales en vez de la
consulta ensamblada y se daba verde CON LA FUGA PRESENTE; aqui se leian cadenas
en vez de los imports y se daba verde CON LA DEPENDENCIA PRESENTE—.

Lo que este harness hace es **poner las dos deformaciones en rojo** y exigir que
caigan los tests que dicen vigilarlas. Un guard que no se puede tumbar no es un
guard: es una decoracion que ocupa sitio y da confianza.

Y hace una cosa mas, que no es un extra
---------------------------------------
M5 y M6 **no son de B16**: son un defecto de PRODUCCION que aparecio al medir.
El gate de 1.0 paso a decir `concurrencia real certificada: OPEN` y resulto
que no era ruido del medidor. Cuatro corridas rojas de veinte del
`test_b2_real_concurrency`, y la causa era un `IntegrityError` de la migracion:
ocho procesos abriendo la misma base nueva, los ocho leen `MAX(version) == 0`,
los ocho deciden subir, y el segundo `INSERT` se lleva un UNIQUE sobre la
PRIMARY KEY y **muere antes de escribir un solo evento**. El `timeout` que
arreglo el `PRAGMA journal_mode` en B2 no lo puede arreglar, porque no es un
candado esperando: es un `SELECT` seguido de un `INSERT`, y entre los dos cabe
otro proceso.

Va aqui, y no en un harness aparte, por una razon que conviene decir: si el
harness de B16 solo mirase lo que B16 toco, la proxima vez que el gate se pusiera
en OPEN por un defecto de verdad habria que abrir otro bloque para mirarlo, y
esa es exactamente la razon por la que este tipo de defecto se queda sin mirar.

Autocomprobacion, y por que el harness la exige a si mismo
---------------------------------------------------------
Cuatro sondas de B13, una de B14 y tres de B15 nacieron rotas y las cazo el
propio harness antes de contarlas. Un harness que cuenta como verde una sonda
que no midio es peor que no tener harness, porque **publica un numero**.

Por eso aqui, ANTES de mutar nada, este script se niega a arrancar si:

- un **diagnostico** declarado no existe entre los ids colectados de verdad;
- un **ancla** no aparece exactamente una vez en su fichero;
- una **deformacion** es identica al texto que deberia cambiar.

Y dos cosas mas, que son las que hacen que el numero signifique algo:

- **Cada sonda declara contra que suite corre.** M1-M4 viven en el guard del
  gate; M5 en las migraciones; M6 en el hijo de la concurrencia. Correr las tres
  suites en cada sonda haria que el numero de caidas no dijera nada, porque
  cualquier deformacion tiraria cosas de mas.
- **El recuento final exige el arbol limpio.** Sin eso, un harness que rompe un
  fichero y no lo devuelve deja el repo en un estado que existio de verdad, y el
  siguiente bloque hereda un arbol que nadie commiteo.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

MUTABLES = (
    RAIZ / "scripts" / "measure_b9_gate_1_0.py",
    RAIZ / "src" / "skillgraph" / "platform" / "migrations.py",
    RAIZ / "tests" / "fixtures" / "b2_concurrency_child.py",
)
SUITES_GATE = ("tests/test_b16_vacuous_pass.py",)
SUITES_MIGRACION = ("tests/test_b12_schema_upgrade.py",)
SUITES_CONCURRENCIA = ("tests/test_b2_real_concurrency.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo, y quien TIENE que caer."""

    nombre: str
    fichero: str
    antes: str
    despues: str
    suite: tuple[str, ...]
    esperados: frozenset[str]


def _sin_trabajo_sin_commitar() -> tuple[str, ...]:
    """Los mutables con cambios SIN commitear, que se perderian al restaurar.

    «Restaurar» y «borrar» son la misma operacion sin commit debajo: si el
    fichero esta sucio y el harness hace `git checkout --`, el trabajo se va y el
    harness sigue diciendo que el arbol esta limpio.
    """
    proc = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            *[str(p.relative_to(RAIZ)) for p in MUTABLES],
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(linea for linea in proc.stdout.splitlines() if linea.strip())


def _limpia_cache() -> None:
    for cache in RAIZ.rglob("__pycache__"):
        if ".venv" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)


def _pytest(objetivos: tuple[str, ...]) -> tuple[int, set[str]]:
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *objetivos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    caidos = {
        linea.split("::", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED ")
    }
    return proc.returncode, caidos


def _colectados(objetivos: tuple[str, ...]) -> set[str]:
    """Los ids de test que EXISTEN de verdad en la suite del harness."""
    proc = subprocess.run(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "--collect-only",
            "-p",
            "no:cacheprovider",
            *objetivos,
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    return {
        linea.strip() for linea in proc.stdout.splitlines() if linea.startswith(f"{objetivos[0]}::")
    }


def _interprete_valido() -> str | None:
    """Por que no, si `PY` no puede importar el paquete. `None` si puede.

    MEDIDO: lanzado con el Python del sistema, el harness de B14 se negaba con
    «la colecta no devolvio ningun test» —el sintoma de una causa que no era la
    que el harness mide, y sin decir donde estaba—. Y en B16 el mismo
    desajuste produjo un `ModuleNotFoundError` que se leia como un defecto del
    producto cuando era del interprete que lanzo la sonda. Falla cerrada, que
    es lo importante; pero obliga a un viaje por el shell para descubrirlo, y
    ese viaje es donde un guard se queda sin correr.
    """
    proc = subprocess.run(
        [PY, "-c", "import skillgraph"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if proc.returncode == 0:
        return None
    return (
        f"{PY} no puede importar `skillgraph`, y este harness corre sus sondas con el\n"
        f"interprete con el que se lanzo. Lanzalo con el del proyecto: `uv run python "
        f"{Path(__file__).relative_to(RAIZ)}`."
    )


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_el_vacio_vuelve_a_ser_un_pass",
        fichero="scripts/measure_b9_gate_1_0.py",
        # MEDIDO A, en su forma extrema: el predicado vuelve a su logica de
        # origen, «si hay mas de uno, OPEN; si no, PASS». Con cero declarantes
        # sale verde, y la evidencia dice «se declara en un solo sitio: []».
        antes='    if not declarantes:\n        return (\n            "OPEN",',
        despues='    if not declarantes:\n        return (\n            "PASS",',
        suite=SUITES_GATE,
        esperados=frozenset(
            {"TestUnPassSinNadaQueCompararNoEsUnPass::test_cero_declaraciones_es_open_y_lo_dice"}
        ),
    ),
    Sonda(
        nombre="M2_la_comprobacion_de_where_se_quita",
        fichero="scripts/measure_b9_gate_1_0.py",
        # La propiedad dice «EL PUERTO, y solo el», y la mitad de «y solo el»
        # no estaba medida: bastaba con que no hubiera dos declarantes. Una
        # constante que todos importan desde un fichero que no es el puerto
        # sigue siendo una segunda fuente de verdad, con una palabra menos.
        antes="    if declarantes[0] != PUERTO_DE_CAPABILITIES:",
        despues="    if False and declarantes[0] != PUERTO_DE_CAPABILITIES:",
        suite=SUITES_GATE,
        esperados=frozenset(
            {
                "TestUnPassSinNadaQueCompararNoEsUnPass::"
                "test_una_declaracion_fuera_del_puerto_es_open"
            }
        ),
    ),
    Sonda(
        nombre="M3_el_nucleo_vuelve_a_no_ver_los_imports",
        fichero="scripts/measure_b9_gate_1_0.py",
        # MEDIDO B, en su forma extrema: el predicado vuelve a mirar SOLO
        # cadenas. Un `from ... import DomainPack` es un `Name` del AST, no una
        # cadena, luego la dependencia de verdad no se ve. Es la fuga de B13
        # con el signo cambiado.
        antes="            if isinstance(nodo, ast.ImportFrom) and nodo.module:",
        despues="            if False and isinstance(nodo, ast.ImportFrom) and nodo.module:",
        suite=SUITES_GATE,
        esperados=frozenset(
            {
                "TestUnaFronteraQueNoSeMideNoEsUnaFrontera::"
                "test_un_import_de_verdad_es_open_y_nombra_el_modulo"
            }
        ),
    ),
    Sonda(
        nombre="M4_la_forma_mas_indirecta_vuelve_a_pasar",
        fichero="scripts/measure_b9_gate_1_0.py",
        # No se importa el tipo: se importa el modulo y se llega al tipo por
        # atributo. Es la forma que se escribe cuando ya se sabe que el nucleo
        # no deberia saber del recurso, y es la que un predicado que solo mira
        # `ImportFrom` deja pasar.
        antes="            elif isinstance(nodo, ast.Attribute) and _ES_TIPO_DE_RECURSO(nodo.attr):",
        despues="            elif False and isinstance(nodo, ast.Attribute) and _ES_TIPO_DE_RECURSO(nodo.attr):",
        suite=SUITES_GATE,
        esperados=frozenset(
            {"TestUnaFronteraQueNoSeMideNoEsUnaFrontera::test_un_atributo_tambien_es_open"}
        ),
    ),
    Sonda(
        nombre="M5_la_migracion_vuelve_a_tener_la_ventana_de_la_carrera",
        fichero="src/skillgraph/platform/migrations.py",
        # El defecto de PRODUCCION que aparecio al medir. MEDIDO: 4 corridas
        # rojas de 20, y 1 hijo muerto de 30 con
        # `sqlite3.IntegrityError: UNIQUE constraint failed: schema_version.version`.
        # Los dos `DELETE` caen antes que los dos `INSERT` y el segundo choca.
        # El guard de forma lo caza sin necesitar la carrera, que es lo unico
        # que se puede exigir de forma determinista (esta medido y escrito en
        # el docstring de la clase de tests).
        antes='    cur.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (objetivo,))',
        despues=(
            '    cur.execute("DELETE FROM schema_version")\n'
            '    cur.execute("INSERT INTO schema_version(version) VALUES (?)", (objetivo,))'
        ),
        suite=SUITES_MIGRACION,
        esperados=frozenset(
            {
                "TestDosProcesosQueSubenLaMismaVersionNoSeMateN::"
                "test_la_escritura_de_la_version_es_un_insert_or_ignore"
            }
        ),
    ),
    Sonda(
        nombre="M6_el_hijo_vuelve_a_no_encontrar_su_codigo",
        fichero="tests/fixtures/b2_concurrency_child.py",
        # `RAIZ` se calculo con `.parent.parent` cuando el fichero vivia en
        # `.pipelinek/`, y no se toco al moverlo a `tests/fixtures/`: ahi
        # `.parent.parent` es `tests/`, luego metia `tests/src` en el path, que
        # no existe. El hijo solo podia importar `skillgraph` porque el paquete
        # esta instalado en el interprete que lo lanza —una red de seguridad
        # accidental— y con este `assert` el fallo pasa a decir «el path no
        # apunta a la raiz» en vez de «no encuentro el modulo».
        antes="RAIZ = Path(__file__).resolve().parents[2]",
        despues="RAIZ = Path(__file__).resolve().parent.parent",
        suite=SUITES_CONCURRENCIA,
        esperados=frozenset(
            {"TestLosHijosSeSolapanDeVerdad::test_los_hijos_tienen_solape_en_el_tiempo"}
        ),
    ),
)


def main() -> int:
    problema = _interprete_valido()
    if problema is not None:
        print("NO SE EJECUTA: el interprete no es el del proyecto.")
        print(problema)
        return 2

    sucio = _sin_trabajo_sin_commitar()
    if sucio:
        print("NO SE EJECUTA: hay cambios sin commitear en los mutables.")
        print("«Restaurar» y «borrar» son la misma operacion sin commit debajo.")
        for linea in sucio:
            print(f"  {linea}")
        return 2

    suites = tuple(dict.fromkeys(s for sonda in SONDAS for s in sonda.suite))
    print(
        f"B16 · {len(SONDAS)} sondas sobre {len(SUITES_GATE) + len(SUITES_MIGRACION) + len(SUITES_CONCURRENCIA)} ficheros de test\n"
    )

    ids: set[str] = set()
    for suite in suites:
        ids |= _colectados(suite)
    if not ids:
        print("NO SE EJECUTA: la colecta no devolvio ningun test.")
        return 2
    faltan = [
        f"{sonda.nombre}: no existe el diagnostico {esperado}"
        for sonda in SONDAS
        for esperado in sorted(sonda.esperados)
        if not any(i.endswith(esperado) for i in ids)
    ]
    if faltan:
        print("NO SE EJECUTA: hay diagnosticos que no existen.")
        print("Una sonda cuyo esperado no esta escrito bien se contaria como cazada con")
        print("menos causa, y el numero seria falso.")
        for linea in faltan:
            print(f"  {linea}")
        return 2
    print(f"diagnosticos verificados: {sum(len(s.esperados) for s in SONDAS)} nombres existen")

    invalidas: list[str] = []
    for sonda in SONDAS:
        texto = (RAIZ / sonda.fichero).read_text(encoding="utf-8")
        apariciones = texto.count(sonda.antes)
        if apariciones != 1:
            invalidas.append(
                f"{sonda.nombre}: el ancla aparece {apariciones} veces, y se sustituiria la primera"
            )
        if sonda.antes == sonda.despues:
            invalidas.append(f"{sonda.nombre}: la deformacion es identica al texto que cambia")
    if invalidas:
        print("NO SE EJECUTA: hay sondas invalidas.")
        for linea in invalidas:
            print(f"  {linea}")
        return 2
    print(f"anclas verificadas: {len(SONDAS)} textos unicos\n")

    for suite in suites:
        rc, caidos = _pytest(suite)
        if rc != 0 or caidos:
            print(f"VERDE DE PARTIDA FALSA: {suite[0]} ya esta rojo sin mutar nada.")
            print(f"  rc={rc}  caidos={sorted(caidos)}")
            return 2
        print(f"linea base: {suite[0]} verde sin mutar")

    causa_de: dict[str, str] = {}
    compartidas: list[str] = []
    invalidas = []
    for sonda in SONDAS:
        _limpia_cache()
        ruta = RAIZ / sonda.fichero
        texto = ruta.read_text(encoding="utf-8")
        try:
            ruta.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
            rc, caidos = _pytest(sonda.suite)
        finally:
            ruta.write_text(texto, encoding="utf-8")
        if not sonda.esperados <= caidos:
            invalidas.append(
                f"{sonda.nombre}: cayo {sorted(caidos)}, pero no sus diagnosticos "
                f"{sorted(sonda.esperados)}"
            )
            print(f"  [SIN CAZAR] {sonda.nombre}")
            continue
        if len(caidos) == len(sonda.esperados):
            print(f"  [CAZADA]    {sonda.nombre}  (solo sus diagnosticos)")
        else:
            print(f"  [CAZADA]    {sonda.nombre}  (+{sorted(caidos - sonda.esperados)})")
            compartidas.append(sonda.nombre)
        causa_de[sonda.nombre] = ", ".join(sorted(sonda.esperados))

    if invalidas:
        print(f"\n{len(invalidas)} sonda(s) sin cazar:")
        for linea in invalidas:
            print(f"  {linea}")
        return 1
    print(f"\n{len(SONDAS)}/{len(SONDAS)} sondas cazadas, {len(causa_de)} causas")

    sucios = _sin_trabajo_sin_commitar()
    if sucios:
        print("\nVEREDICTO NO VALIDO: el harness dejo el arbol sucio.")
        for linea in sucios:
            print(f"  {linea}")
        return 1
    if compartidas:
        print(f"sondas que tiraron mas de lo suyo: {compartidas}")
    print("arbol limpio: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
