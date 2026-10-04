"""B20 · el harness de mutacion de la contradiccion del gate.

QUE MIDE, Y POR QUE SUS SONDAS TIENEN QUE CAER CADA UNA A LA SUA.

El defecto de B20 no es un numero, es una RELACION: el gate se contradecia a si
mismo sobre el mismo hecho. Un numero se comprueba mirandolo; una relacion se
comprueba rompiendo una de sus dos puntas y viendo si la otra se entera.

  M1  `_tipos_de_recurso` vuelve al SUFIJO. Es el defecto de B20 puesto de
      vuelta entero: con el patron, `PackManifest` deja de contar y el
      predicado vuelve a dar PASS con un import de verdad en `core/`. Debe caer
      el diagnostico del conjunto.

  M2  `_docstrings_de` vuelve a mirar SOLO `body[0]`. Es el segundo defecto del
      clasificador, y es el que mas caro sale: con el, la documentacion de los
      `NewType` de `core/` se cuenta como dependencia y el veredicto da OPEN
      sobre un arbol SANO. Debe caer el diagnostico de la documentacion.

  M3  la comparacion de contradiccion se invierte: `core sin dependencias` en
      OPEN deja de obligar a `ontology extensible`. Es la CONTRAALTO del
      contrasalto: sin el, el guard que vigila que el gate no se contradiga
      pasaria en verde si alguien invirtiera la implication, que es
      precisamente el defecto que el bloque cierra.

**EL REQUISITO QUE B18 ANADIO Y QUE ESTE HARNESS HEREDA.** Antes de contar una
sonda se exige que la deformacion PARSEE. Una deformacion que rompe la sintaxis
hace caer la suite POR NO IMPORTAR, no por detectar, y pareceria la sonda mas
fuerte de las tres. MEDIDO en B18, donde la primera version de M1 dejo cuatro
sentencias colgando de un `if` que ya no existia.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"
SUITE0 = RAIZ / "tests" / "test_b20_ontologia_contradictoria.py"
SUITES = ("tests/test_b20_ontologia_contradictoria.py",)


class Sonda:
    """Una deformacion, y el FICHERO donde vive.

    MEDIDO, y este atributo no estaba en la primera version: M3 deformaba la
    comparacion de contradiccion, que vive en el TEST, y el harness la buscaba
    en el GATE — donde no aparece ni una vez. La sonda no llego al sitio que
    decia medir y el harness lo dijo solo, con «ancla aparece 0 veces», que es
    exactamente para lo que esta comprobacion esta: un 0 tiene que ser un
    AVISO con nombre, no una excepcion.

    Y que M3 deforme el propio guard del bloque es correcto y no es una
    trampa: el arnes tiene que poder comprobar que su contrasalto no se puede
    invertir. Un contrasalto que nadie puede romper de verdad no es un
    contrasalto, es una decoracion.
    """

    def __init__(
        self,
        nombre: str,
        fichero: pathlib.Path,
        antes: str,
        despues: str,
        esperados: frozenset[str],
    ) -> None:
        self.nombre = nombre
        self.fichero = fichero
        self.antes = antes
        self.despues = despues
        self.esperados = esperados


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_el_conjunto_de_recursos_vuelve_a_ser_un_sufijo",
        fichero=GATE,
        antes="    for paquete in PAQUETES_DE_RECURSO:",
        # El defecto de B20 entero: un patron por forma en vez de un conjunto
        # derivado. Con el, `PackManifest` deja de contar y el predicado vuelve
        # a mentir sobre el tipo central del proyecto.
        despues="    for paquete in ('inventado',):  # deformacion: conjunto vacio de proposito",
        esperados=frozenset(
            {
                "tests/test_b20_ontologia_contradictoria.py::"
                "test_el_conjunto_de_recursos_lo_declaran_los_paquetes_no_un_sufijo"
            }
        ),
    ),
    Sonda(
        nombre="M2_el_clasificador_de_docstrings_vuelve_a_mirar_solo_el_primero",
        fichero=GATE,
        antes="        for sentencia in cuerpo:",
        # El segundo defecto del clasificador, y el que mas caro sale: la
        # documentacion de los `NewType` de core/ se contaria como dependencia
        # y el veredicto daria OPEN sobre un arbol sano.
        despues="        for sentencia in cuerpo[:1]:  # deformacion: solo el primero",
        esperados=frozenset(
            {
                "tests/test_b20_ontologia_contradictoria.py::test_un_docstring_que_nombra_un_recurso_no_abre_el_veredicto"
            }
        ),
    ),
    Sonda(
        nombre="M3_la_implicacion_se_invierte",
        fichero=SUITE0,
        antes='        if c == "OPEN" and o != "OPEN":',
        # La CONTRAALTO del contrasalto. Sin esta deformacion, el guard que
        # vigila que el gate no se contradiga pasaria en verde con la
        # implicacion al reves —que es el defecto que el bloque cierra—.
        despues='        if o == "OPEN" and c != "OPEN":  # deformacion: implication al reves',
        esperados=frozenset(
            {
                "tests/test_b20_ontologia_contradictoria.py::"
                "test_un_tipo_de_recurso_que_las_dos_ven_no_puede_ser_un_solo_pass"
            }
        ),
    ),
)


def sin_trabajo_sin_commitar() -> tuple[str, ...]:
    salida = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(
        linea for linea in salida.stdout.splitlines() if linea and not linea.startswith("?? ")
    )


def colectados() -> set[str]:
    """Los nodeids REALES, no los que este fichero dice.

    MEDIDO, y es el segundo fallo de este patron en dos bloques: la primera
    version de B19 comparaba sus diagnosticos contra una lista escrita en el
    propio harness y decia «3 nombres existen» sin comprobar nada.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header", *SUITES],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    return {linea.strip() for linea in proc.stdout.splitlines() if "::" in linea}


def pytest_de() -> tuple[int, set[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *SUITES],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    caidas: set[str] = set()
    for linea in proc.stdout.splitlines():
        for prefijo in ("FAILED ", "ERROR "):
            if linea.startswith(prefijo):
                caidas.add(linea[len(prefijo) :].split(" ")[0])
                break
    return proc.returncode, caidas


def main() -> int:
    if sin_trabajo_sin_commitar():
        print("HAY TRABAJO SIN COMMITAR; el arnes no deformaria sobre un arbol ya roto:")
        for linea in sin_trabajo_sin_commitar():
            print(f"   {linea}")
        return 2

    ficheros = sorted({s.fichero for s in SONDAS})
    textos = {f: f.read_text(encoding="utf-8") for f in ficheros}
    for sonda in SONDAS:
        n = textos[sonda.fichero].count(sonda.antes)
        if n != 1:
            print(
                f"ANCLA DE {sonda.nombre} aparece {n} veces en "
                f"{sonda.fichero.relative_to(RAIZ)}; tiene que ser exactamente 1. "
                f"Si es 0, la deformacion no llega al sitio que dice medir y la sonda "
                f"se contaria como la mas fuerte de las tres sin haber medido nada."
            )
            return 2

    print(f"B20 · {len(SONDAS)} sondas sobre {len(SUITES)} fichero de test\n")

    rc_base, caidas_base = pytest_de()
    print(f"  base (sin deformar): rc={rc_base}, {len(caidas_base)} caidas")
    if rc_base != 0:
        print("  la suite de B20 NO esta verde antes de deformar nada.")
        return 1

    causa_de: dict[str, str] = {}
    indefinidas: list[str] = []
    try:
        for sonda in SONDAS:
            original = textos[sonda.fichero]
            sonda.fichero.write_text(
                original.replace(sonda.antes, sonda.despues, 1), encoding="utf-8"
            )
            try:
                ast.parse(sonda.fichero.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                indefinidas.append(sonda.nombre)
                print(f"  {sonda.nombre}: SIN_SONDA — no parsea ({exc.msg})")
                sonda.fichero.write_text(original, encoding="utf-8")
                continue
            _rc, caidas = pytest_de()
            sonda.fichero.write_text(original, encoding="utf-8")
            propias = caidas - caidas_base
            if not propias:
                indefinidas.append(sonda.nombre)
                print(f"  {sonda.nombre}: NO CAYO — el guard no se entero")
                continue
            if not propias <= sonda.esperados:
                indefinidas.append(sonda.nombre)
                print(f"  {sonda.nombre}: CAYO CON OTROS DIAGNOSTICOS")
                print(f"     esperadas: {sorted(sonda.esperados)}")
                print(f"     caidas   : {sorted(propias)}")
                continue
            esperado = next(iter(propias))
            causa_de[esperado] = sonda.nombre
            print(f"  {sonda.nombre}: CAZADA por {esperado}")
    finally:
        for fichero, texto in textos.items():
            fichero.write_text(texto, encoding="utf-8")

    print(
        f"\n  arnes restaurado: el gate vuelve a parsear: {bool(ast.parse(GATE.read_text(encoding='utf-8')))}"
    )
    esperados = {d for s in SONDAS for d in s.esperados}
    inexistentes = sorted(esperados - colectados())
    if inexistentes:
        print(f"  DIAGNOSTICOS QUE NO EXISTEN: {inexistentes}")
        return 1
    print(f"  diagnosticos verificados contra el arbol: {len(esperados)}")
    if indefinidas:
        print(f"  SIN CAZAR: {indefinidas}")
    print(f"  {len(causa_de)}/{len(SONDAS)} sondas cazadas, {len(set(causa_de.values()))} causas\n")
    return 0 if len(causa_de) == len(SONDAS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
