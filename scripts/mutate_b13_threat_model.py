#!/usr/bin/env python3
"""B13 — el harness de mutacion del modelo de amenaza y del aislamiento.

Que tiene que demostrar
-----------------------
Que los guards de B13 vigilan lo que dicen vigilar. Un modelo de amenaza
escrito sin guard es una prosa optimista: nadie lo relee, y cuando el
codigo cambia la prosa se queda diciendo «OK» sobre algo que ya no lo es.
Eso es exactamente lo que paso con la fuga entre tenants.

Que son las sondas
------------------
Cada sonda deshace UNA cosa, y exige que caigan los tests **diagnosticos**
de esa cosa. La causa de una sonda es su conjunto de tests diagnosticos,
no todo lo que se puso rojo: cuatro sondas que heredan el fallo de la
quinta se contarian como cuatro y el numero seria falso.

Las sondas mas importantes aqui son M1 y M2, porque deshacen las DOS
cosas que el documento afirmaba y que no eran verdad:

- M1 reabre la fuga de tenant (quita los parentesis del `OR`).
- M2 saca una superficie de la tabla, que es la unica forma de que la
  vigencia del modelo pueda volverse a medir por un numero.

El guard anti-destruccion, heredado de B9 y corregido en B11
------------------------------------------------------------
`git checkout --` restaura **del indice**. Sin commit debajo, «restaurar»
y «borrar» son la misma operacion: en B9 eso se llevo por delante el
arreglo entero mientras el harness reportaba un numero, y en B11 una
sonda muto un fichero que no estaba en `MUTABLES`, lo dejo sucio, y el
harness reporto «arbol restaurado» porque **la suite seguia verde**.

Por eso el veredicto final exige las DOS cosas: que la suite pase y que
`git status` de los mutables este limpio. Comprobar la suite NO es
comprobar que el arbol volvio.

El harness se comprueba a si mismo antes de mutar
-------------------------------------------------
Dos cosas se comprueban ANTES de mutar nada, y las dos nacieron rotas aqui:

1. M5 se declaro con los dos diagnosticos mal escritos —la clase se llama
   `TestElModeloNoSeContradice` y se escribio `TestElModeloNoSecontradice`— y
   el harness lo|reportaba `[CAZADA]`: `caidos & esperados` no esta vacio
   mientras caiga UNO de los dos, luego un nombre que no existe no produce un
   fallo sino una causa mas corta. Un contador de sondas cazadas no lo nota.
2. M4 usaba `## Superficies` como ancla, y aparece dos veces: como encabezado
   y dentro de una mencion en prosa. `replace(..., 1)` se come la prosa.

Sin esas dos comprobaciones, este fichero seria el mismo defecto que vigila,
un nivel mas abajo.
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
    RAIZ / "src" / "skillgraph" / "platform" / "knowledge_repository.py",
    RAIZ / "docs" / "architecture" / "ADR-0015-threat-model-stride.md",
    RAIZ / "tests" / "test_b13_threat_model.py",
)

SUITES = ("tests/test_b13_threat_model.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo o del documento, y quien TIENE que caer."""

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


def _colectados(objetivos: tuple[str, ...]) -> set[str]:
    """Los ids de test que EXISTEN de verdad en las suites del harness.

    Sin esto, una sonda cuyo `esperados` lleva un nombre mal escrito se
    contaria como cazada con la mitad de la causa: `caidos & esperados` no
    esta vacio mientras caiga UNO de los dos, y el harness imprimiria
    `[CAZADA]` sin mirar el otro. Es el error del harness midiendo al
    harness, y solo se ve mirando lo que hay, no lo que cae.
    """
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
    ids: set[str] = set()
    for linea in proc.stdout.splitlines():
        # pytest imprime `tests/test_b13_threat_model.py::Clase::test`; el
        # objetivo que se le paso lleva la ruta con `tests/` delante.
        if linea.startswith(f"{objetivos[0]}::"):
            ids.add(linea.strip())
    return ids


def _sucios() -> tuple[str, ...]:
    """Los mutables que NO volvieron a su estado de `HEAD` al terminar."""
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
        nombre="M1_la_fuga_de_tenant_vuelve_a_estar_abierta",
        fichero="src/skillgraph/platform/knowledge_repository.py",
        antes="            sql += \" AND (api_version || '/' || kind = ? OR kind = ?)\"",
        despues="            sql += \" AND api_version || '/' || kind = ? OR kind = ?\"",
        esperados=frozenset(
            {
                "TestLaFugaCrossTenant::test_t2_no_ve_los_recursos_de_t1_al_filtrar_por_kind",
                "TestLosSqlNoTienenUnOrSinAgrupar::test_ninguna_lectura_ejecuta_un_where_con_or_suelto",
            }
        ),
    ),
    Sonda(
        nombre="M2_una_superficie_del_arbol_deja_de_estar_declarada",
        fichero="docs/architecture/ADR-0015-threat-model-stride.md",
        antes=(
            "| `packaging` | **Contenido de fuera del proyecto**: manifiesto, "
            "requisitos, compatibilidad | `tests/test_b11_pack_lifecycle.py` |\n"
        ),
        despues="",
        esperados=frozenset(
            {
                "TestElModeloEnumeraTodaSuperficieDelArbol::test_todo_paquete_del_arbol_tiene_fila_en_el_adr",
            }
        ),
    ),
    Sonda(
        nombre="M3_la_vigencia_vuelve_a_mediirse_con_un_numero",
        fichero="docs/architecture/ADR-0015-threat-model-stride.md",
        antes="ha cerrado las etapas 0..7 y los bloques B0..B12.",
        despues=(
            "ha cerrado las etapas 0..7 y los bloques B0..B12 con 830 tests verdes y 17 releases."
        ),
        esperados=frozenset(
            {
                "TestElModeloEnumeraTodaSuperficieDelArbol::test_el_adr_no_declara_un_numero_de_tests_como_su_vigencia",
            }
        ),
    ),
    Sonda(
        nombre="M4_la_tabla_de_superficies_desaparece",
        fichero="docs/architecture/ADR-0015-threat-model-stride.md",
        # El ancla lleva los saltos de linea porque `## Superficies` aparece
        # DOS veces: como encabezado y dentro de una mencion en prosa, con
        # acentos graves. `replace(..., 1)` se comeria la prosa, que no es lo
        # que esta sonda quiere deshacer.
        antes="\n## Superficies\n",
        despues="\n## Superficies retiradas\n",
        esperados=frozenset(
            {
                "TestElModeloEnumeraTodaSuperficieDelArbol::test_el_analisis_tiene_una_seccion_de_superficies",
            }
        ),
    ),
    Sonda(
        nombre="M5_la_contradiccion_del_adapter_vuelve",
        fichero="docs/architecture/ADR-0015-threat-model-stride.md",
        antes="- **Fuera del alcance**: T5 backups, T6 observabilidad.",
        despues=(
            "- **Fuera del alcance**: Adapter real HTTP/LLM (E1, sin implementar),\n"
            "  T5 backups, T6 observabilidad."
        ),
        esperados=frozenset(
            {
                "TestElModeloNoSeContradice::test_el_adapter_no_puede_estar_fuera_de_alcance_y_cerrado",
                "TestElModeloNoSeContradice::test_la_seccion_de_alcance_no_excluye_lo_que_esta_implementado",
            }
        ),
    ),
    Sonda(
        nombre="M6_el_adr_vuelve_a_decir_que_no_toca_codigo",
        fichero="docs/architecture/ADR-0015-threat-model-stride.md",
        antes=(
            "- **B13 SI introdujo cambios de codigo**, y esta linea de consecuencias\n"
            "  cambio al revisarlo. Antes afirmaba que el ADR se limita a documentar el\n"
        ),
        despues=(
            "- No introduce cambios de codigo: el ADR documenta el estado real sin\n"
            "  modificar comportamiento. Esta linea cambio al revisarlo. Antes afirmaba\n"
            "  que el ADR se limita a documentar el\n"
        ),
        esperados=frozenset(
            {
                "TestElModeloNoSeContradice::test_el_adr_no_puede_decir_que_no_toca_codigo_mientras_lo_toca",
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

    print(f"B13 · {len(SONDAS)} sondas sobre {len(SUITES)} ficheros de test\n")
    causa_de: dict[str, str] = {}
    compartidas: list[str] = []
    invalidas: list[str] = []

    # Antes de mutar nada: cada nombre que una sonda EXIGE tiene que existir.
    # Un `esperados` con un nombre que no existe se cruzaria con `caidos` y
    # daria una causa mas corta, no un fallo del harness.
    ids = _colectados(SUITES)
    if not ids:
        print("NO SE EJECUTA: la colecta no devolvio ningun test.")
        return 2
    faltan: list[str] = []
    for sonda in SONDAS:
        for esperado in sorted(sonda.esperados):
            if not any(i.endswith(esperado) for i in ids):
                faltan.append(f"{sonda.nombre}: no existe el diagnostico {esperado}")
    if faltan:
        print("NO SE EJECUTA: hay diagnosticos que no existen.")
        print("Una sonda cuyo esperado no esta escrito bien se contaria como")
        print("cazada con menos causa, y el numero seria falso.")
        for linea in faltan:
            print(f"  {linea}")
        return 2
    print(f"diagnosticos verificados: {sum(len(s.esperados) for s in SONDAS)} nombres existen\n")

    # Y cada ancla tiene que ser UNICA. `replace(..., 1)` se come la primera
    # aparicion: una sonda cuyo texto aparece dos veces deshace lo que no
    # quiere, y no falla por una razon que el harness pueda contar.
    ambiguas: list[str] = []
    for sonda in SONDAS:
        apariciones = (RAIZ / sonda.fichero).read_text(encoding="utf-8").count(sonda.antes)
        if apariciones != 1:
            ambiguas.append(
                f"{sonda.nombre}: el ancla aparece {apariciones} veces en {sonda.fichero}, "
                f"y se sustituye la primera"
            )
    if ambiguas:
        print("NO SE EJECUTA: hay anclas ambiguas.")
        for linea in ambiguas:
            print(f"  {linea}")
        return 2
    print(f"anclas verificadas: {len(SONDAS)} textos unicos\n")

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
                f"{sonda.nombre}: cayo {sorted(caidos)} pero ninguno de sus "
                f"diagnosticos {sorted(sonda.esperados)}"
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
