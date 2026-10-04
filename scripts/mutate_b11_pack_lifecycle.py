#!/usr/bin/env python3
"""B11 — el harness de mutacion del ciclo de vida de los packs.

Que tiene que demostrar
-----------------------
No basta con que la suite se ponga verde: tiene que ponerse roja **si
alguien deshace el ciclo**. Un bloque que entrega una funcionalidad nueva
y no comprueba que sus guards la vigilarian ha entregado una funcionalidad
que se deshace sola.

Que son las sondas
------------------
Cada sonda deshace UNA cosa del contrato, y exige que caigan los tests
**diagnosticos** de esa cosa. No basta con que caiga algo: cuatro sondas
que heredan el fallo de la quinta se contarian como cuatro, y el numero
seria un numero falso. Por eso cada sonda declara sus `esperados` y una
causa compartida entre dos sondas se cuenta como AVISO, no como exito.

MEDIDO, y el motivo esta medido, en el harness heredado de B9: contar como
«causa» el conjunto COMPLETO de tests en rojo hace que dos sondas
legitimamente distintas se pisen en las centinelas de «esta todo verde» y el
harness avise de causa compartida donde no la hay. Aqui la causa es el
conjunto de tests DIAGNOSTICOS.

El guard anti-destruccion, copiado de B9
-----------------------------------------
`git checkout --` restaura **del indice**. Sin commit debajo, «restaurar» y
«borrar» son la misma operacion, y en B9 eso se llevo por delante el
arreglo entero mientras el harness reportaba un numero como si nada. Aqui
el harness se NIEGA a empezar si hay trabajo sin commitear en lo que va a
restaurar.
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
    RAIZ / "src" / "skillgraph" / "packaging" / "registry.py",
    RAIZ / "src" / "skillgraph" / "platform" / "installed_packs_repository.py",
    RAIZ / "src" / "skillgraph" / "cli" / "commands" / "pack.py",
    RAIZ / "tests" / "test_b11_pack_lifecycle.py",
)

SUITES = ("tests/test_b11_pack_lifecycle.py",)


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
    """Los mutables con cambios SIN commitear, que se perderian al restaurar.

    Copiado de B9, donde su AUSENCIA DESTRUYO TRABAJO y el harness lo
    reporto como un numero. «Restaurar» y «borrar» son la misma operacion
    si no hay nada commiteado debajo, y la unica manera de que no sean la
    misma es commitear antes.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
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

    **ESTE GUARD EXISTE PORQUE SU AUSENCIA DEJO PASAR UN ARBOL ROTO,
    MEDIDO en la primera ejecucion de este harness.** Una de las seis
    sondas mutaba `installed_packs_repository.py`, que no estaba en
    `MUTABLES`: el harness la ejecuto, la restauro (nada que restaurar) y
    sigio. Al final(reporto «arbol restaurado y ejecutando como estaba»)
    porque la suite seguia VERDE.

    Y aqui esta lo importante: la suite podia estar verde con el archivo
    mutado, porque la mutacion era invisible para los tests. Eso es
    exactamente el fallo de B9 repetido con otro disfraz —«restaurado» y
    «borrado» son la misma operacion si no hay nada commiteado debajo—,
    y la leccion de ahi era que comprobar la suite no basta. Hace falta
    comprobar ADEMAS que el arbol volvio, y eso es lo que hace este.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(linea for linea in proc.stdout.splitlines() if linea.strip())


def _restaura() -> None:
    subprocess.run(
        ["git", "checkout", "--", *[str(p.relative_to(RAIZ)) for p in MUTABLES]],
        cwd=RAIZ,
        check=True,
    )
    _limpia_cache()


def _sondas() -> tuple[Sonda, ...]:
    """Las deformaciones, derivadas del texto REAL de los ficheros.

    MEDIDO en B9, y es el error 32 de WI-113 repetido: una sonda que apunta
    a un texto que ya no existe se cuenta como «no cazo», y eso se lee como
    «el guard aguanta» cuando lo que pasa es que el guard no se toco. Por
    eso cada sonda se verifica contra el fichero ANTES de mutar, y una
    sonda cuyo `antes` no esta ahi se cuenta como fallo del harness.
    """
    return (
        Sonda(
            nombre="M1_instalar_acepta_un_pack_incompatible",
            fichero="src/skillgraph/packaging/registry.py",
            antes='    motivos = motivos_de_incompatibilidad(manifiesto, version_skillgraph=version_skillgraph)\n    if motivos:\n        raise ValidationError(\n            f"el pack {manifiesto.describe()} no se puede instalar: " + "; ".join(motivos)\n        )',
            despues="    motivos = ()  # sonda M1: la compatibilidad deja de comprobarse",
            esperados=frozenset(
                {
                    "TestElNucleoDelCiclo::test_instalar_rechaza_incompatible_con_el_motivo",
                    "TestElCicloSeEjecuta::"
                    "test_install_por_la_cli_rechaza_un_pack_incompatible_diciendo_por_que",
                }
            ),
        ),
        Sonda(
            nombre="M2_update_acepta_una_version_que_no_sube",
            fichero="src/skillgraph/packaging/registry.py",
            antes="    if not _sube(instalada.manifiesto.version, manifiesto.version):",
            despues="    if False:  # sonda M2: update deja de exigir que la version suba",
            esperados=frozenset({"TestElNucleoDelCiclo::test_update_exige_que_la_version_suba"}),
        ),
        Sonda(
            nombre="M3_update_compara_por_texto_y_no_por_numero",
            fichero="src/skillgraph/packaging/registry.py",
            antes="    return b > a",
            despues="    return nueva > actual  # sonda M3: 0.10.0 pasa a ser MENOR que 0.9.0",
            esperados=frozenset(
                {"TestElNucleoDelCiclo::test_update_compara_por_numero_y_no_por_texto"}
            ),
        ),
        Sonda(
            nombre="M4_retirar_borra_la_fila",
            fichero="src/skillgraph/packaging/registry.py",
            antes="        return RegistroDePacks(tuple(retirada if f.pack == pack else f for f in self.filas))",
            despues="        return RegistroDePacks(tuple(f for f in self.filas if f.pack != pack))  # sonda M4: BORRA en vez de marcar",
            esperados=frozenset(
                {
                    "TestRetirarMarcaNoBorra::test_la_fila_sigue_ahi_despues_de_retirar",
                    "TestElRegistroPersisteYAisla::test_retirar_no_borra_la_fila_en_disco",
                }
            ),
        ),
        Sonda(
            nombre="M5_el_aislamiento_por_tenant_y_proyecto",
            fichero="src/skillgraph/platform/installed_packs_repository.py",
            antes='        sql = "SELECT * FROM installed_packs WHERE tenant_id = ? AND project_id = ?"',
            despues='        sql = "SELECT * FROM installed_packs"  # sonda M5: sin WHERE, sin aislamiento',
            esperados=frozenset(
                {
                    "TestElRegistroPersisteYAisla::test_el_registro_no_enseña_packs_de_otro_proyecto",
                    "TestElRegistroPersisteYAisla::test_el_registro_no_enseña_packs_de_otro_tenant",
                }
            ),
        ),
        Sonda(
            nombre="M6_instalar_deja_de_crear_registro",
            fichero="src/skillgraph/packaging/registry.py",
            antes="        return self._con_viva(\n            FilaDePack(\n                pack=manifiesto.name, estado=ESTADO_INSTALADO, manifiesto=manifiesto, uid=uid\n            )\n        )",
            despues="        return self  # sonda M6: instalar no registra nada",
            esperados=frozenset(
                {
                    "TestRetirarMarcaNoBorra::test_el_registro_es_inmutable",
                    "TestElCicloSeEjecuta::test_el_ciclo_completo_corre_de_punta_a_punta",
                }
            ),
        ),
    )


def main() -> int:
    print("Harness de mutacion B11 — el ciclo de vida de los packs")
    print("=" * 78)

    pendientes = _sin_trabajo_sin_commitar()
    if pendientes:
        print("ABORTO: hay cambios SIN COMMITAR en ficheros que este harness restaura.")
        print("        `git checkout --` restaura del indice, luego restaurarlos")
        print("        BORRARIA el trabajo en vez de volver atras. Commitea antes.")
        for linea in pendientes:
            print(f"        {linea}")
        return 2

    _limpia_cache()
    rc, _ = _pytest(SUITES)
    if rc != 0:
        print(f"ABORTO: la suite NO esta verde antes de mutar (rc={rc}).")
        return 2
    print("Base verificada: suite verde sin tocar nada.\n")

    sondas = _sondas()
    causas: set[frozenset[str]] = set()
    sin_sonda: list[str] = []
    cazadas = 0

    for sonda in sondas:
        ruta = RAIZ / sonda.fichero
        original = ruta.read_text(encoding="utf-8")
        if sonda.antes not in original:
            sin_sonda.append(sonda.nombre)
            print(f"[SIN SONDA] {sonda.nombre}: el texto anterior no esta en {sonda.fichero}")
            print("             El harness esta mirando algo que ya no existe.")
            continue

        ruta.write_text(original.replace(sonda.antes, sonda.despues, 1), encoding="utf-8")
        _limpia_cache()
        rc, caidos = _pytest(SUITES)
        _restaura()

        if rc == 0 or not (sonda.esperados & caidos):
            print(f"[NO CAZADA] {sonda.nombre}: rc={rc}, cayeron {sorted(caidos)}")
            continue
        if not sonda.esperados <= caidos:
            print(f"[PARCIAL]   {sonda.nombre}: cayeron {sorted(caidos)}")
            print(f"             se esperaban {sorted(sonda.esperados)}")
            continue

        cazadas += 1
        causas.add(frozenset(sonda.esperados))
        print(f"[CAZADA]    {sonda.nombre}: {len(caidos)} tests en rojo")

    print()
    print(f"sondas cazadas: {cazadas}/{len(sondas)}")
    print(f"causas DISTINTAS: {len(causas)} (una por sonda = {cazadas} esperadas)")
    if sin_sonda:
        print(f"sin sonda: {sin_sonda}")
    # El aviso SOLO tiene sentido cuando todas se cazaron y aun asi las
    # causas se pisan. Con menos sondeadas que sondas, avisar de «causa
    # compartida» es mixingar dos cosas distintas: lo que hay ahi son
    # sondas sin cazar, y eso ya se ha dicho una linea mas arriba.
    if sondas and cazadas == len(sondas) and len(causas) != len(sondas):
        print(
            "AVISO: dos sondas comparten el MISMO conjunto de tests diagnosticos. Una de "
            "las dos no esta midiendo lo que dice medir: o su guarda no muerde, o cae por "
            "otra causa."
        )

    # El ultimo veredicto tiene que ser el del codigo original. Sin esto, el
    # harness termina mudo y su ultimo estado conocido es una deformacion.
    _limpia_cache()
    rc, caidos = _pytest(SUITES)
    print()
    if rc != 0 or caidos:
        print(f"ABORTO: tras restaurar, la suite sigue en rojo (rc={rc}, {sorted(caidos)}).")
        return 2

    # La suite verde NO basta. Este harness fallo MEDIDO por dar verde
    # con un archivo mutado en el arbol, y por eso el ultimo veredicto
    # mira las dos cosas: que la suite pase y que el arbol haya vuelto.
    sucios = _sucios()
    if sucios:
        print("ABORTO: el ARBOL NO VOLVIO, aunque la suite este verde.")
        print("        Una sonda muta algo que no esta en MUTABLES, o el")
        print("        `git checkout --` no la toco. Esto NO es 'restaurado':")
        print("        es un fichero roto que la suite no sabe mirar.")
        for linea in sucios:
            print(f"        {linea}")
        return 2

    print(f"Arbol restaurado Y EJECUTANDO como estaba: {SUITES[0]} verde, y `git status` limpio.")
    return 0 if cazadas == len(sondas) and not sin_sonda else 1


if __name__ == "__main__":
    sys.exit(main())
