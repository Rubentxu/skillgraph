"""B19 · el harness de mutacion de «NO es reproducible» / «no he podido medirlo».

QUE HACE ESTE HARNESS, Y POR QUE SUS TRES SONDAS TIENEN QUE CAER CADA UNA A LA
SUA, CON SOLO SU DIAGNOSTICO.

El defecto de B19 es un VERBO, no un numero: el predicado decia «la distribucion
NO es reproducible» cuando lo que habia ocurrido era que la entrada habia
cambiado entre las dos mediciones. Un verbo no se mira, se comprueba
deformando lo que decide y viendo si la frase cambia.

Las tres sondas deforman la MITAD DE ARRIBA de la cadena —la decision— y no la
construccion, porque la construccion es lo que ya se sabe que funciona: MEDIDO,
8 de 8 con bytes iguales. Deformar la construccion seria medir otra vez lo que
ya se midio.

  M1  `_huella_de_entrada` deja de mirar el CONTENIDO de lo modificado.
      Un `git status` a solas —que solo ve NOMBRES— pasaria el arbol quieto y
      dejaria pasar el caso que importa. Debe caer el diagnostico de la huella.

  M2  `_decide_por_bytes` vuelve a acusar sin mirar si la entrada era la misma.
      Es el defecto EXACTO de B19, puesto de vuelta. Debe caer el diagnostico
      del verbo.

  M3  `_decide_por_bytes` devuelve PASS con la evidencia de «NO es
      reproducible». Es el contrasalto del contrasalto, en la forma mas dura: sin
      el, un arreglo que hubiera hecho callar al predicado habria hecho pasar
      el bloque entero borrando el defecto Y la capacidad de detectarlo.

**EL REQUISITO QUE B18 ANADIO Y QUE ESTE HARNESS HEREDA.** Antes de contar una
sonda, se exige que la deformacion PARSEE (`ast.parse`). Una deformacion que
rompe la sintaxis hace caer la suite POR NO IMPORTAR, no por detectar: parece
la sonda mas fuerte y no ha medido nada. MEDIDO en B18, donde la primera version
de M1 devolvia un `elif` a una sola linea y dejaba cuatrosentencias colgando
de un `if` que ya no existia, y los seis tests caian como ERROR de colecta.
"""

from __future__ import annotations

import ast
import pathlib
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"
SUITES = ("tests/test_b19_entrada_no_veredicto.py",)


class Sonda:
    def __init__(self, nombre: str, antes: str, despues: str, esperados: frozenset[str]) -> None:
        self.nombre = nombre
        self.antes = antes
        self.despues = despues
        self.esperados = esperados


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_la_huella_deja_de_mirar_el_contenido_de_lo_modificado",
        antes='    crudo = "\\0".join((proc_head.stdout, proc_estado.stdout, proc_diff.stdout))',
        # Se quita `proc_diff` y se deja SOLO el estado, que ve nombres y no
        # contenido: dos ficheros con el mismo nombre y distinto contenido darian
        # la misma huella, y el predicado volveria a acusar sin poder distinguir.
        despues='    crudo = "\\0".join((proc_head.stdout, proc_estado.stdout))',
        esperados=frozenset(
            {
                "tests/test_b19_entrada_no_veredicto.py::"
                "test_la_huella_cambia_si_cambia_el_contenido_de_un_fichero_ya_versionado",
            }
        ),
    ),
    Sonda(
        nombre="M2_el_veredicto_vuelve_a_acusar_sin_mirar_la_entrada",
        antes="    if huella_antes != huella_despues:",
        # El defecto de B19 puesto de vuelta: se borra la condicion que separa
        # «cambio la entrada» de «no es reproducible». El cuerpo se conserva, y
        # queda muerto — que es como se ven estos defectos: el codigo correcto
        # al lado, sin la condicion que lo hacia verdad.
        despues="    if False:",
        esperados=frozenset(
            {
                "TestElVeredictoDistingueLasDosCausas::test_con_la_entrada_cambiada_no_acusa_al_proyecto"
            }
        ),
    ),
    Sonda(
        nombre="M3_el_veredicto_se_desincroniza_de_su_evidencia",
        antes=(
            "    return (\n"
            '        "OPEN",\n'
            '        f"la distribucion NO es reproducible: mismo contenido y distinta fecha dan "\n'
        ),
        # El contrasalto del contrasalto, y en la forma MAS DURA: el veredicto
        # pasa a PASS mientras su evidencia sigue diciendo «NO es reproducible».
        # Un veredicto desincronizado de su propia evidencia es PEOR que uno que
        # se equivoca, porque el que lo lee se lleva las dos cosas y no sabe cual
        # creer. Y si el arreglo de B19 hubiera hecho callar al predicado —que es
        # el arreglo mas facil de hacer y el que deforma el verbo sin tocar nada
        # mas— esto pasaria en verde.
        despues=(
            "    return (\n"
            '        "PASS",\n'
            '        f"la distribucion NO es reproducible: mismo contenido y distinta fecha dan "\n'
        ),
        esperados=frozenset(
            {
                "tests/test_b19_entrada_no_veredicto.py::"
                "test_con_la_entrada_misma_una_no_reproducibilidad_real_sigue_diciendolo"
            }
        ),
    ),
)


def sin_trabajo_sin_commitar() -> tuple[str, ...]:
    salida = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(
        linea for linea in salida.stdout.splitlines() if linea and not linea.startswith("?? ")
    )


def _colectados() -> set[str]:
    """Los nodeids que pytest REALLY colecta, no los que este fichero dice.

    Sin esto, «3 nombres existen» seria una comparacion de una lista escrita a
    mano contra si misma.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header", *SUITES],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    return {linea.strip() for linea in proc.stdout.splitlines() if "::" in linea}


def pytest_de(una_sonda: str) -> tuple[int, set[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *SUITES],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    # MEDIDO, Y FALLO PROPIO DEL HARNES: la primera version hacia
    # `linea.split(" ")[0]` sobre las lineas `FAILED ...`, y por eso todo
    # aso caia en el nombre `FAILED` y el harness decia «cayo con otros
    # diagnosticos» sobre tres sondas que SI habian caido. El separador de
    # pytest es «FAILED <fichero>::<clase>::<testo>», luego el nombre es el
    # segundo campo y no el primero. Un harness que no sabe leer su propia
    # salida no puede contar lo que ha medido, y da 0 de 3 con la sensacion de
    # que el guard no funciona.
    caidas = set()
    for linea in proc.stdout.splitlines():
        for prefijo in ("FAILED ", "ERROR "):
            if linea.startswith(prefijo):
                caidas.add(linea[len(prefijo) :].split(" ")[0])
                break
    return proc.returncode, caidas


def main() -> int:
    if shutil.which("uv") is None:
        print("el arnes necesita `uv` en el PATH para correr pytest con el proyecto")
        return 2
    if sin_trabajo_sin_commitar():
        print("HAY TRABAJO SIN COMMITAR; el arnes no deformaria sobre un arbol que ya esta roto:")
        for linea in sin_trabajo_sin_commitar():
            print(f"   {linea}")
        return 2

    originales = {s.nombre: s.antes for s in SONDAS}
    for s in SONDAS:
        if GATE.read_text(encoding="utf-8").count(s.antes) != 1:
            print(
                f"ANCLA DE {s.nombre} aparece {GATE.read_text(encoding='utf-8').count(s.antes)} veces"
            )
            print("   Si no es exactamente 1, la deformacion ya no es la que dice ser y el")
            print("   arnes estaria contando otra cosa.")
            return 2

    print(f"B19 · {len(SONDAS)} sondas sobre {len(SUITES)} fichero de test\n")

    rc_base, caidas_base = pytest_de("sin deformar")
    print(f"  base (sin deformar): rc={rc_base}, {len(caidas_base)} caidas")
    if rc_base != 0:
        print("  la suite de B19 NO esta verde antes de deformar nada.")
        for c in caidas_base:
            print(f"     {c}")
        return 1

    causa_de: dict[str, str] = {}
    indefinidas: list[str] = []
    try:
        for sonda in SONDAS:
            texto = GATE.read_text(encoding="utf-8")
            GATE.write_text(texto.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
            # EL REQUISITO DE B18, heredado: la deformacion tiene que PARSEAR.
            try:
                ast.parse(GATE.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                indefinidas.append(sonda.nombre)
                print(f"  {sonda.nombre}: SIN_SONDA — la deformacion no parsea ({exc.msg})")
                print("     Un guard que cae porque el arbol no parsea no ha medido nada.")
                GATE.write_text(texto, encoding="utf-8")
                continue
            _rc, caidas = pytest_de(sonda.nombre)
            GATE.write_text(texto, encoding="utf-8")
            propias = caidas - caidas_base
            if not propias:
                print(f"  {sonda.nombre}: NO CAYO — el guard no se entero de la deformacion")
                indefinidas.append(sonda.nombre)
                continue
            if not propias <= sonda.esperados:
                print(f"  {sonda.nombre}: CAYO PERO CON OTROS DIAGNOSTICOS")
                print(f"     esperadas: {sorted(sonda.esperados)}")
                print(f"     caidas   : {sorted(propias)}")
                indefinidas.append(sonda.nombre)
                continue
            esperado = next(iter(propias))
            causa_de[esperado] = sonda.nombre
            print(f"  {sonda.nombre}: CAZADA por {esperado}")
    finally:
        texto = GATE.read_text(encoding="utf-8")
        for nombre, ancla in originales.items():
            texto = texto.replace(ancla, originales[nombre], 1)
        GATE.write_text(texto, encoding="utf-8")

    print(f"\n  arnes restaurado: {GATE.read_text(encoding='utf-8').count('if False:') == 0}")
    # EL CONJUNTO SE DERIVA DEL ARBOL, Y NO DE UNA LISTA ESCRITA AQUI. La
    # primera version de este harness comparaba los diagnosticos esperados
    # contra una lista escrita en el propio harness y decia «3 nombres
    # existen», sin haber comprobado nada: si el test se renombraba, el
    # harness seguia diciendo que existian y luego contaba un 0 de 3 con la
    # explicacion equivocada. Es el mismo error de WI-114 y el de B16: una
    # lista de «los sitios que deben reaccionar» es la misma trampa que la
    # lista de sitios que hay que vigilar.
    colectados = _colectados()
    inexistentes = sorted({d for s in SONDAS for d in s.esperados} - colectados)
    if inexistentes:
        print(f"  DIAGNOSTICOS QUE NO EXISTEN: {inexistentes}")
        print("     Si un test se renombro, el harness no puede culpar a la sonda.")
        return 1
    print(
        f"  diagnosticos verificados contra el arbol: "
        f"{len({d for s in SONDAS for d in s.esperados})} de {len(colectados)} tests colectados"
    )
    if indefinidas:
        print(f"  SIN CAZAR: {indefinidas}")
    print(f"  {len(causa_de)}/{len(SONDAS)} sondas cazadas, {len(set(causa_de.values()))} causas\n")
    return 0 if len(causa_de) == len(SONDAS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
