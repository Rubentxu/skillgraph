#!/usr/bin/env python3
"""B12 — el harness de mutacion del libro de migraciones.

Que tiene que demostrar
-----------------------
Que los guards de B12 vigilan el upgrade. Un bloque que anade la
capacidad de subir una base y no comprueba que sus tests la detectarian si
alguien la deshace ha entregado una capacidad que se deshace sola.

Que son las sondas
------------------
Cada sonda deshace UNA cosa del contrato y exige que caigan los tests
**diagnosticos** de esa cosa. No basta con que caiga algo: si cuatro sondas
heredan el fallo de la quinta se contarian como cuatro y el numero seria un
numero falso. La causa de una sonda es su conjunto de tests diagnosticos,
no todo lo que se puso rojo.

La sonda que mas importa es **M2**. Deshace una decision de diseno —«el
libro registra, no gobierna»— y es la unica que puede volver a hacer que una
base con una columna caida NO se repare. Si M2 saliera con la suite verde,
estariamos declarando que la migracion se aplica solo la primera vez, que es
justo el defecto que B12 vino a quitar.

El guard anti-destruccion, heredado de B9 y corregido en B11
------------------------------------------------------------
`git checkout --` restaura **del indice**. Sin commit debajo, «restaurar» y
«borrar» son la misma operacion: en B9 eso se llevo por delante el arreglo
entero mientras el harness reportaba un numero, y en B11 una sonda muto un
fichero que no estaba en `MUTABLES`, lo dejo sucio, y el harness reporto
«arbol restaurado» porque **la suite seguia verde**.

Por eso el veredicto final exige las DOS cosas: que la suite pase y que
`git status` de los mutables este limpio. Comprobar la suite NO es comprobar
que el arbol volvio.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable

#: Ficheros que este harness restaura. De `HEAD`, no de una copia hecha al
#: empezar: una copia puede tener el arbol ya sucio, y entonces el harness
#: «restaura» el defecto y lo cuenta como verde.
MUTABLES = (
    RAIZ / "src" / "skillgraph" / "platform" / "migrations.py",
    RAIZ / "src" / "skillgraph" / "platform" / "schema.py",
    RAIZ / "src" / "skillgraph" / "platform" / "storage.py",
    RAIZ / "tests" / "test_b12_schema_upgrade.py",
)

SUITES = ("tests/test_b12_schema_upgrade.py", "tests/test_wi87_state_vocabulary_single_source.py")


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo y los tests que TIENEN que caer con ella."""

    nombre: str
    fichero: str
    antes: str
    despues: str
    esperados: frozenset[str]


def _limpia_cache() -> None:
    for cache in RAIZ.rglob("__pycache__"):
        if ".venv" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)


def _sin_trabajo_sin_commitar() -> tuple[str, ...]:
    """Los mutables con cambios SIN commitear, que se perderian al restaurar."""
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


def _pytest(objetivos: tuple[str, ...]) -> tuple[int, set[str]]:
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *objetivos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    caidos = {
        linea.split("::", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED ")
    }
    return proc.returncode, caidos


def _sucios() -> tuple[str, ...]:
    """Los mutables que NO volvieron a su estado de `HEAD` al terminar.

    Existe porque su ausencia dejo pasar un arbol roto, MEDIDO en la
    primera ejecucion del harness de B11: una sonda mutaba un fichero que
    no estaba en `MUTABLES`, lo ejecuto, no lo restauro (no habia nada que
    restaurar) y sigio. El harness reporto «arbol restaurado y ejecutando
    como estaba» porque la suite seguia VERDE.

    Aqui esta lo importante: la suite podia estar verde con el fichero
    mutado, porque la mutacion era invisible para los tests. Comprobar la
    suite no basta; hace falta comprobar ADEMAS que el arbol volvio.
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


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_la_version_vuelve_a_ser_un_literal",
        fichero="src/skillgraph/platform/schema.py",
        antes="SCHEMA_VERSION: int = version_declarada()",
        despues="SCHEMA_VERSION: int = 2",
        esperados=frozenset(
            {
                "TestLaVersionEsDerivada::test_no_es_un_literal_escrito_a_mano",
            }
        ),
    ),
    Sonda(
        nombre="M2_el_libro_vuelve_a_gobernar",
        fichero="src/skillgraph/platform/migrations.py",
        antes="""    for migracion in MIGRACIONES:
        migracion.aplicar(cur)
        if migracion.id in ya:
            continue""",
        despues="""    for migracion in MIGRACIONES:
        if migracion.id in ya:
            continue
        migracion.aplicar(cur)""",
        esperados=frozenset(
            {
                "TestLaColumnaAdHocDejoDeSerUnCasoEspecial::test_una_base_sin_esa_columna_la_recupera",
            }
        ),
    ),
    Sonda(
        nombre="M3_una_base_mas_nueva_se_abre_en_silencio",
        fichero="src/skillgraph/platform/storage.py",
        antes="            migrations.comprueba_que_no_sea_mas_nueva(cur)\n",
        despues="",
        esperados=frozenset(
            {
                "TestUnaBaseMasNuevaNoSeAbre::test_una_base_mas_nueva_falla",
                "TestUnaBaseMasNuevaNoSeAbre::test_el_error_dice_que_versiones_se_vieron",
                "TestUnaBaseMasNuevaNoSeAbre::test_no_sale_como_traceback_de_sqlite",
            }
        ),
    ),
    Sonda(
        nombre="M4_la_base_deja_de_declarar_su_version",
        fichero="src/skillgraph/platform/migrations.py",
        antes=(
            '    cur.execute("DELETE FROM schema_version")\n'
            '    cur.execute("INSERT INTO schema_version(version) VALUES (?)", (objetivo,))'
        ),
        despues="    pass  # sonda M4: la base deja de declarar su version",
        esperados=frozenset(
            {
                "TestSubirUnaBaseVieja::test_una_base_sin_libro_se_abre_y_se_migra",
                "TestSubirUnaBaseVieja::test_la_versio_n_se_puede_preguntar_a_la_base",
            }
        ),
    ),
    Sonda(
        nombre="M5_el_libro_deja_de_anotar",
        fichero="src/skillgraph/platform/migrations.py",
        antes="""        cur.execute(
            "INSERT OR IGNORE INTO schema_migrations(migration_id, applied_at) "
            "VALUES (?, datetime('now'))",
            (migracion.id,),
        )
        nuevas.append(migracion.id)""",
        despues="        nuevas.append(migracion.id)",
        esperados=frozenset(
            {
                "TestElLibroDeMigraciones::test_una_base_nueva_tiene_todas_anotadas",
                "TestSubirUnaBaseVieja::test_una_base_sin_libro_se_abre_y_se_migra",
            }
        ),
    ),
)


def main() -> int:
    sucio = _sin_trabajo_sin_commitar()
    if sucio:
        print("NO SE EJECUTA: hay cambios sin commitear en los mutables.")
        print("«Restaurar» y «borrar» son la misma operacion sin commit debajo.")
        for linea in sucio:
            print(f"  {linea}")
        return 2

    print(f"B12 · {len(SONDAS)} sondas sobre {len(SUITES)} ficheros de test\n")
    causa_de: dict[str, str] = {}
    compartidas: list[str] = []
    invalidas: list[str] = []

    rc, caidos = _pytest(SUITES)
    if rc != 0 or caidos:
        print("VERDE DE PARTIDA FALSA: la suite ya esta roja sin mutar nada.")
        print(f"  rc={rc}  caidos={sorted(caidos)}")
        return 2
    print("linea base: suite verde sin mutar\n")

    for sonda in SONDAS:
        ruta = RAIZ / sonda.fichero
        texto = ruta.read_text(encoding="utf-8")
        if sonda.antes not in texto:
            invalidas.append(f"{sonda.nombre}: el texto «antes» no aparece en {sonda.fichero}")
            print(f"  [SIN SONDA] {sonda.nombre}")
            continue
        ruta.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
        _limpia_cache()
        rc, caidos = _pytest(SUITES)
        subprocess.run(
            ["git", "checkout", "--", sonda.fichero], cwd=RAIZ, check=True, capture_output=True
        )
        _limpia_cache()

        if rc == 0:
            invalidas.append(f"{sonda.nombre}: la suite sigue VERDE (rc=0)")
            print(f"  [NO CAZADA] {sonda.nombre}")
            continue

        diagnosticos = caidos & sonda.esperados
        if not diagnosticos:
            invalidas.append(
                f"{sonda.nombre}: cayo {sorted(caidos)} pero ninguno de sus diagnosticos "
                f"{sorted(sonda.esperados)}"
            )
            print(f"  [OTRA CAUSA] {sonda.nombre}: cayo {sorted(caidos)}")
            continue

        causa = ",".join(sorted(diagnosticos))
        print(f"  [CAZADA] {sonda.nombre}  -> {causa}")
        if causa in causa_de:
            compartidas.append(f"{sonda.nombre} comparte causa con {causa_de[causa]}")
        causa_de[causa] = sonda.nombre

    sucios = _sucios()
    cazadas = len(SONDAS) - len(invalidas)

    print(f"\n{cazadas}/{len(SONDAS)} sondas cazadas, {len(causa_de)} causas distintas")
    if compartidas:
        print("AVISO — causa compartida entre sondas:")
        for linea in compartidas:
            print(f"  {linea}")
    if invalidas:
        print("SONDAS INVALIDAS:")
        for linea in invalidas:
            print(f"  {linea}")
    if sucios:
        print("ARBOL SUCIO (los mutables no volvieron a HEAD):")
        for linea in sucios:
            print(f"  {linea}")

    # El veredicto exige LAS DOS cosas. La suite verde con el arbol sucio es
    # el falso verde de B11, y no se repite aqui.
    return 0 if cazadas == len(SONDAS) and not compartidas and not invalidas and not sucios else 1


if __name__ == "__main__":
    raise SystemExit(main())
