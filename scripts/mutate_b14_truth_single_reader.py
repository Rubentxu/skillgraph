#!/usr/bin/env python3
"""B14 — el harness de la lectura unica del estado.

Que tiene que demostrar
-----------------------
Que los guards de B14 vigilan lo que dicen vigilar, y en particular que el
guard de la CLAVE DUPLICADA no se conforma con ver `coherente: false`.

Porque ese es el fallo que se produjo al escribir este bloque. La primera
version del test afirmaba `coherente is not True` y pasaba en verde con el
tool VULNERABLE: en ese momento el estado ya era incoherente por otra causa
—el recuento de tests—, y `coherente: false` no dice de que. Un guard que
pasa por una causa ajena al objeto que vigila es un guard que no vigila. La
sonda M2 es la que se asegura de que eso no vuelva: deshace la lectura unica
y el guard tiene que caer, no dar un falso verde.

Que son las sondas
------------------
Cada sonda deshace UNA cosa, y exige que caigan los tests **diagnosticos** de
esa cosa. La causa de una sonda es su conjunto de tests diagnosticos, no todo
lo que se puso rojo: cuatro sondas que heredan el fallo de la quinta se
contarian como cuatro y el numero seria falso.

El guard anti-destruccion, heredado de B9 y corregido en B11
------------------------------------------------------------
`git checkout --` restaura **del indice**. Sin commit debajo, «restaurar» y
«borrar» son la misma operacion. Por eso el veredicto final exige las DOS
cosas: que la suite pase y que `git status` de los mutables este limpio.
Comprobar la suite NO es comprobar que el arbol volvio.

El harness se comprueba a si mismo
----------------------------------
Antes de mutar, colecta la suite y exige dos cosas: que cada nombre de cada
`esperados` EXISTA, y que cada ancla `antes` sea UNICA. Sin eso, una sonda
con un nombre mal escrito se contaria como cazada con menos causa —M5 de B13
fue exactamente eso— y una sonda con un ancla repetida deshaceria el texto
equivocado sin que se notara —M4 de B13 tambien—.
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
MUTABLES = (RAIZ / "scripts" / "project_truth.py",)

SUITES = ("tests/test_b14_truth_single_reader.py",)


@dataclass(frozen=True, slots=True)
class Sonda:
    """Una deformacion del codigo, y quien TIENE que caer."""

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
        timeout=1800,
    )
    caidos = {
        linea.split("::", 1)[1].split(" ")[0]
        for linea in proc.stdout.splitlines()
        if linea.startswith("FAILED ")
    }
    return proc.returncode, caidos


def _colectados(objetivos: tuple[str, ...]) -> set[str]:
    """Los ids de test que EXISTEN de verdad en las suites del harness."""
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
        nombre="M1_vuelve_un_reader_por_regex_del_estado",
        fichero="scripts/project_truth.py",
        # Se sustituye el CUERPO de `tests_declarados` por la version con
        # regex, que es como estaba antes de B14. Definir la constante sin
        # usarla no seria sonda: desactivaria el modulo sin cambiar lo que el
        # codigo hace, y el guard mide si queda alguien LEYENDO por regex.
        #
        # MEDIDO: la primera version de esta sonda mutaba `release_declarada`
        # a `_TAG_STATE.search(...)`, y `_TAG_STATE` es una constante que B14
        # BORRO. El modulo reventaba con NameError, caian los DIEZ tests que
        # ejecutan el verificador, y ninguno era el diagnostico declarado: el
        # harness lo clasifico como INVALIDA, que es exactamente lo que
        # distingue a una sonda que mide de una que rompe. Una sonda que rompe
        # el modulo no prueba el guard que dice vigilar — la pasaria igual
        # cualquier reader por regex, y también un `import` roto —.
        #
        # Por eso la sonda reinsta un reader FUNCIONAL: mismo dato, misma
        # comprobacion de tipo sobre el texto capturado, patron propio. Lo
        # unico que cambia es que vuelve a haber dos maneras de leer el estado.
        antes=(
            '    tests = _seccion("tests")\n'
            '    if tests is None or "total" not in tests:\n'
            '        raise VerdadNoLegible("STATE.yaml.tests no declara `total`")\n'
            '    total = tests["total"]'
        ),
        despues=(
            '    _TOTAL = re.compile(r"^\\s*total:\\s*(\\S+)", re.MULTILINE)\n'
            '    m = _TOTAL.search(_lee("STATE.yaml"))\n'
            "    if m is None:\n"
            '        raise VerdadNoLegible("STATE.yaml.tests no declara `total`")\n'
            "    total = int(m.group(1))"
        ),
        esperados=frozenset(
            {"TestElEstadoSeLeeDeUnaSolaManera::test_no_queda_ningun_regex_sobre_state_yaml"}
        ),
    ),
    Sonda(
        nombre="M2_yaml_tolera_las_claves_duplicadas_en_silencio",
        fichero="scripts/project_truth.py",
        # El ancla es la linea EXACTA que escribio ruff format. Comprobado
        # despues del ultimo `ruff format`, no antes: el error 32 de WI-113.
        antes=(
            "_SinClavesDuplicadas.add_constructor("
            "yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construye)"
        ),
        despues="# Sonda M2: sin este constructor, YAML se queda con la ultima clave en silencio.",
        esperados=frozenset(
            {
                "TestUnaClaveDuplicadaNoPasaPorAlto::test_una_clave_repetida_hace_el_estado_ilegible",
                "TestUnaClaveDuplicadaNoPasaPorAlto::test_el_valor_que_se_lee_no_es_uno_de_los_dos_a_eleccion",
            }
        ),
    ),
    Sonda(
        nombre="M3_el_total_deja_de_comprobar_que_es_un_entero",
        fichero="scripts/project_truth.py",
        antes="    if not isinstance(total, int) or isinstance(total, bool):",
        despues="    if False:",
        esperados=frozenset(
            {"TestLosTiposNoSeAdelantan::test_un_total_que_no_es_entero_se_rechaza"}
        ),
    ),
    Sonda(
        nombre="M4_el_tag_deja_de_comprobar_que_lleva_la_v",
        fichero="scripts/project_truth.py",
        antes='    if not isinstance(etiqueta, str) or not etiqueta.startswith("v"):',
        despues="    if False:",
        esperados=frozenset({"TestLosTiposNoSeAdelantan::test_un_tag_sin_la_v_se_rechaza"}),
    ),
    Sonda(
        nombre="M6_la_colecta_interrumpida_vuelve_a_publicar_un_recuento",
        fichero="scripts/project_truth.py",
        # Quita la mirada al codigo de salida de pytest. El numero que sale en
        # la salida («2867 tests collected, 27 errors») es real —son los tests
        # que llego a ver— pero no es EL recuento, y sin esta comprobacion el
        # verificador lo publicaba con su nombre.
        # El ancla lleva la primera linea del raise para ser UNICA: hay otra
        # comprobacion de `returncode` en `_tag_declarado`, que devuelve `None`
        # y no tiene nada que ver. Un ancla repetida deshaceria el texto
        # equivocado sin que se notara —M4 de B13— y aqui la autocomprobacion
        # del harness lo rechaza antes de tocar nada.
        antes=("    if proc.returncode != 0:\n        parcial = _COLECTADOS.search(proc.stdout)"),
        despues=("    if False:\n        parcial = _COLECTADOS.search(proc.stdout)"),
        esperados=frozenset(
            {
                "TestUnRecuentoQueNoSeTerminoNoSePublica::test_una_colecta_interrumpida_no_publica_un_recuento"
            }
        ),
    ),
    Sonda(
        nombre="M5_el_workitem_deja_de_comprobar_que_no_esta_vacio",
        fichero="scripts/project_truth.py",
        antes="    if not isinstance(workitem, str) or not workitem:",
        despues="    if False:",
        esperados=frozenset({"TestLosTiposNoSeAdelantan::test_un_workitem_vacio_se_rechaza"}),
    ),
)


def _interprete_valido() -> str | None:
    """Por que no, si `PY` no puede importar el paquete. `None` si puede.

    MEDIDO: lanzado con el Python del sistema en vez del del proyecto, este
    harness se negaba a arrancar con «la colecta no devolvio ningun test» — un
    sintoma de una causa que no era la que el harness mide, y sin decir donde
    estava. Falla cerrada, que es lo importante: nunca habria dado un falso
    verde. Pero un instrumento que se niega por una causa que no nombra obliga a
    un viaje de ida y vuelta por el shell para descubrirla, y ese viaje es
    exactamente donde un guard se queda sin correr y otro, sin querer, lo
    declara verde.
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
        f"interprete con el que se lanzo. El ultimo error del interprete fue:\n"
        f"  {proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else '(vacio)'}\n"
        f"Lanzalo con el interprete del proyecto: `uv run python "
        f"scripts/mutate_b14_truth_single_reader.py`."
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

    print(f"B14 · {len(SONDAS)} sondas sobre {len(SUITES)} ficheros de test\n")
    causa_de: dict[str, str] = {}
    compartidas: list[str] = []
    invalidas: list[str] = []

    ids = _colectados(SUITES)
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
        print("Una sonda cuyo esperado no esta escrito bien se contaria como")
        print("cazada con menos causa, y el numero seria falso.")
        for linea in faltan:
            print(f"  {linea}")
        return 2
    print(f"diagnosticos verificados: {sum(len(s.esperados) for s in SONDAS)} nombres existen")

    ambiguas = [
        f"{sonda.nombre}: el ancla aparece {apariciones} veces, y se sustituye la primera"
        for sonda in SONDAS
        for apariciones in [(RAIZ / sonda.fichero).read_text(encoding="utf-8").count(sonda.antes)]
        if apariciones != 1
    ]
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
        # **B36: MEDIDO AL ABRIR EL BLOQUE, ESTO ERA `git checkout --`.**
        # Restaura DEL INDICE, luego con la mutacion sin stagear se lleva el
        # fichero entero. Se restaura ESCRIBIENDO lo que se leyo, que es lo que
        # ya hacen nueve harnesses de este repo.
        ruta.write_text(texto, encoding="utf-8")
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

    return 0 if cazadas == len(SONDAS) and not compartidas and not invalidas and not sucios else 1


if __name__ == "__main__":
    raise SystemExit(main())
