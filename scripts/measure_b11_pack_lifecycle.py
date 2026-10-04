#!/usr/bin/env python3
"""B11 — el ciclo de vida de los packs, medido ANTES de escribir nada.

Por que este script existe
--------------------------
B8 entrego el CONTRATO de paquete: `PackManifest`, `Requires`, los seis
tipos, los tres niveles de aislamiento y `es_compatible` que responde con
motivos. Su propio enunciado decia, textual, que sin contrato versionado
no hay ``upgrade`` y no hay ``install``/``update``/``remove`` «que valga
como algo mas que copiar ficheros».

B10 cerro las dos propiedades del gate que estaban abiertas por falta de
CERTIFICACION. Quedan cuatro, y dos piden CODIGO: `pack/controller
lifecycle` y `upgrade desde releases soportadas`. Esta mide la primera.

El gate de B9 lo dice asi, y es literal:

    `sg pack` expone ['import', 'load'] y no ['install', 'update', 'remove']

Y el enunciado del gate pide el ciclo de vida, no tres nombres de comando.
Un predicado que se dejara en «existen tres subcomandos» volveria a
cerrarse escribiendo tres lineas de parser, que es el mismo atajo que B10
cerro para las superficies. Por eso aqui **cada** predicado se ejecuta: se
monta un proyecto, se corre el ciclo de verdad y se mira el resultado.

Las cinco preguntas
-------------------
Q1  ¿El ciclo de vida existe como comandos de `sg pack`?
Q2  ¿`install` RECHAZA un pack incompatible y dice POR QUE?
Q3  ¿`update` exige version estrictamente mayor y reporta el delta?
Q4  ¿`remove` de un pack que no esta instalado lo dice, sin reventar?
Q5  ¿`list` responde lo que hay instalado, con version y aislamiento?

Veredictos
----------
``PASS``          la propiedad se cumple y se ha comprobado ejecutandola.
``OPEN``          se ha comprobado y NO se cumple.
``NO_MEASURABLE`` no hay forma de decidirla con este entorno, y se dice por que.
``NO_MEDIBLE``    la propiedad esta declarada aqui y este instrumento no
                  tiene predicado. Sale para que un hueco del instrumento se
                  ponga a si mismo en rojo en vez de dejar pasar en verde.

Diseno: puro por encima, efecto por debajo
------------------------------------------
``evaluar()`` es **puro**: recibe el resultado de las ejecuciones y
devuelve veredictos, sin leer disco ni lanzar procesos. Todo lo que
habla con el mundo vive en ``preguntar()``. Eso permite que un test
construya una respuesta falsa y compruebe que el evaluador se pone rojo,
que es la unica manera de saber que sabe ponerse rojo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

RAIZ: Final[Path] = Path(__file__).resolve().parent.parent

Veredicto = Literal["PASS", "OPEN", "NO_MEASURABLE", "NO_MEDIBLE"]

#: Las cinco preguntas del bloque. Cada una tiene su predicado; una que no
#: lo tuviera sale como NO_MEDIBLE, que es el hueco del instrumento hecho
#: visible en vez de dejarse pasar.
PREGUNTAS: Final[tuple[str, ...]] = (
    "el ciclo de vida existe como comandos de sg pack",
    "install rechaza un pack incompatible y dice por que",
    "update exige version estrictamente mayor y reporta el delta",
    "remove de un pack no instalado lo dice, sin reventar",
    "list responde lo que hay instalado, con version y aislamiento",
)

CICLO_ESPERADO: Final[tuple[str, ...]] = ("install", "update", "remove", "list")

#: La version que `list` deberia ensenar cuando se ejecuta.
#:
#: MEDIDO, y el motivo esta medido: el predicado buscaba el literal `0.1.0`
#: porque la escena empezaba instalando esa, y `list` se ejecutaba DESPUES
#: del `update` a `0.2.0`. O sea que `list` decia la version correcta y el
#: predicado la daba por ausente: el fallo estaba en la sonda, no en el
#: codigo. Es el error 32 de WI-113 con otro disfraz —una sonda que apunta
#: a algo que ya no es— y la leccion es la de siempre: una expectativa
#: escrita a mano en vez de derivada del estado que uno acaba de construir
#: acaba mintiendo en la direccion de alarmar de mas.
VERSION_TRAS_UPDATE: Final[str] = "0.2.0"


@dataclass(frozen=True, slots=True)
class Respuesta:
    """Lo que devolvio UNA ejecucion real. Inmutable."""

    rc: int
    stdout: str
    stderr: str

    @property
    def combinado(self) -> str:
        return f"{self.stdout}\n{self.stderr}"


@dataclass(frozen=True, slots=True)
class Informe:
    """Lo medido ejecutando. Lo evalua `evaluar()`, que es puro."""

    subcomandos: tuple[str, ...]
    install_incompatible: Respuesta
    update_menor: Respuesta
    update_mayor: Respuesta
    remove_inexistente: Respuesta
    list_con_un_pack: Respuesta
    version_esperada_en_list: str
    list_vacio: Respuesta
    install_valido: Respuesta
    error: str = ""


# =====================================================================
# CAPA PURA — de aqui abajo no se lee disco ni se lanza nada.
# =====================================================================


def _exito(respuesta: Respuesta) -> bool:
    return respuesta.rc == 0


def _menciona(respuesta: Respuesta, *agujas: str) -> bool:
    """El mensaje dice ALGO de lo que se le pide que diga.

    No basta con el exit code: un error que sale sin explicar WHICH
    clause failed deja al operador adivinando, y un guard que solo mira el
    codigo de salida no se dao cuenta de la diferencia.
    """
    minusculas = respuesta.combinado.lower()
    return any(aguja.lower() in minusculas for aguja in agujas)


def q1_existe_el_ciclo(informe: Informe) -> tuple[Veredicto, str]:
    """El gate pide install/update/remove. `list` viene con ellos.

    Se mide contra el PARSER, no contra una lista escrita aqui: un
    predicado que comprueba tres nombres fijos dice «cumple» el dia que
    alguien escriba los tres en el parser sin que exista el ciclo entero.
    """
    faltan = [c for c in CICLO_ESPERADO if c not in informe.subcomandos]
    if informe.error:
        return "NO_MEASURABLE", f"no se pudo leer el parser: {informe.error}"
    if faltan:
        return "OPEN", (
            f"`sg pack` expone {list(informe.subcomandos)} y no {faltan}: el ciclo de "
            "vida que el gate declara no existe todavia como comando"
        )
    return "PASS", f"`sg pack` expone el ciclo completo: {sorted(informe.subcomandos)}"


def q2_install_rechaza_incompatible(informe: Informe) -> tuple[Veredicto, str]:
    """Un pack incompatible se rechaza, y el rechazo dice POR QUE.

    B8 entrego `es_compatible` devolviendo MOTIVOS y no un bool, con el
    argumento de que «no encaja» no le dice al operador cual de las dos
    clausulas fallo. Aqui se comprueba que ese motivo llega hasta el
    usuario: es la costura entre el contrato y la linea de comandos.
    """
    r = informe.install_incompatible
    if _exito(r):
        return "OPEN", (
            "install acepto un pack que declara `requires.skillgraph` fuera de rango y "
            f"salio con rc=0: {r.combinado.strip()[:200]}"
        )
    if not _menciona(r, "skillgraph", "requiere", "requiere", "compatib"):
        return "OPEN", (
            "install rechazo el pack pero el mensaje NO dice por que: el operador se "
            f"queda con el exit code y nada mas. Salida: {r.combinado.strip()[:200]}"
        )
    return "PASS", f"install rechazo el pack nombrando la clausula (rc={r.rc})"


def q3_update_exige_version_mayor(informe: Informe) -> tuple[Veredicto, str]:
    """`update` no es `install` con otro nombre: exige que la version suba.

    Las dos mitades. (a) Una version MENOR o igual tiene que rechazarse: si
    `update` acepta una version menor, es una operacion que degrada el
    entorno sin avisar, que es peor que no tenerla. (b) Una version MAYOR
    tiene que aceptarse y decir cual era y cual es: un update que no dice
    el delta deja al operador sin poder confirmar lo que ha-installed.
    """
    menor = informe.update_menor
    if _exito(menor):
        return "OPEN", (
            "update acepto una version MENOR (o igual) que la instalada: es una "
            "operacion que degrada el entorno sin avisar, que es peor que no tener update"
        )
    mayor = informe.update_mayor
    if not _exito(mayor):
        return (
            "OPEN",
            f"update de una version MAYOR fallo: rc={mayor.rc}; {mayor.combinado.strip()[:200]}",
        )
    if not _menciona(mayor, "0.1.0", "0.2.0"):
        return "OPEN", (
            "update funciono pero no dice el DELTA de version: el operador no puede "
            f"confirmar que subio. Salida: {mayor.combinado.strip()[:200]}"
        )
    return "PASS", (
        f"update rechaza la version que no sube (rc={menor.rc}) y con la que sube "
        "dice el delta de version"
    )


def q4_remove_no_inventado(informe: Informe) -> tuple[Veredicto, str]:
    """Quitar lo que no esta instalado se dice, no se revienta.

    Es la mitad de la propiedad que mas se olvida: casi todos los gestores
    de paquetes revientan con una excepcion o un traceback cuando se les
    pide quitar algo que no esta. Aqui la respuesta tiene que ser un
    MENSAJE y un exit code de dominio, que es exactamente lo que WI-109
    cerro para el otro lado de la frontera.
    """
    r = informe.remove_inexistente
    combinado = r.combinado
    if "Traceback" in combinado:
        return "OPEN", (
            "remove de un pack no instalado salio como Traceback: sale a traza en vez "
            "de como error de dominio"
        )
    if _exito(r):
        return "OPEN", (
            "remove de un pack que NO esta instalado devolvio rc=0: no se puede "
            "distinguir «lo he quitado» de «no habia nada», y un `remove` que siempre "
            "sale bien no es un remove"
        )
    if not _menciona(r, "no esta instalado", "no está instalado", "no instalado"):
        return "OPEN", (f"remove fallo pero no dijo QUE: {combinado.strip()[:200]}")
    return "PASS", f"remove de un pack no instalado lo dice (rc={r.rc}, sin traceback)"


def q5_list_responde(informe: Informe) -> tuple[Veredicto, str]:
    """`list` responde lo instalado, con version y aislamiento.

    Sin `list` no hay ciclo de vida que se pueda administrar: se puede
    instalar y quitar, pero no preguntar que hay. Y tiene que traer la
    VERSION, porque sin ella `update` no tiene contra que comparar.
    """
    vacio = informe.list_vacio
    if not _exito(vacio):
        return (
            "OPEN",
            f"`pack list` sobre un proyecto sin packs fallo: rc={vacio.rc}; {vacio.combinado.strip()[:200]}",
        )
    con_pack = informe.list_con_un_pack
    if not _exito(con_pack):
        return "OPEN", (
            f"`pack list` con un pack instalado fallo: rc={con_pack.rc}; "
            f"{con_pack.combinado.strip()[:200]}"
        )
    esperada = informe.version_esperada_en_list
    if not _menciona(con_pack, esperada):
        return "OPEN", (
            f"`pack list` responde pero no dice la VERSION {esperada}, que es la que la "
            f"escena instalo: {con_pack.combinado.strip()[:200]}"
        )
    if not _menciona(con_pack, "declarative", "sandbox", "subprocess"):
        return "OPEN", (
            f"`pack list` no dice el AISLAMIENTO: el nivel es el contenido del contrato "
            f"de B8 y sin el no se ve. Salida: {con_pack.combinado.strip()[:200]}"
        )
    return "PASS", "`pack list` responde version y aislamiento de lo instalado"


PREDICADOS: Final[Mapping[str, Callable[[Informe], tuple[Veredicto, str]]]] = {
    "el ciclo de vida existe como comandos de sg pack": q1_existe_el_ciclo,
    "install rechaza un pack incompatible y dice por que": q2_install_rechaza_incompatible,
    "update exige version estrictamente mayor y reporta el delta": q3_update_exige_version_mayor,
    "remove de un pack no instalado lo dice, sin reventar": q4_remove_no_inventado,
    "list responde lo que hay instalado, con version y aislamiento": q5_list_responde,
}


def evaluar(informe: Informe) -> tuple[tuple[str, Veredicto, str], ...]:
    """Ejecuta el predicado de cada pregunta. Puro: no lee nada."""
    salida: list[tuple[str, Veredicto, str]] = []
    for pregunta in PREGUNTAS:
        predicado = PREDICADOS.get(pregunta)
        if predicado is None:
            salida.append(
                (pregunta, "NO_MEDIBLE", "este instrumento no tiene predicado para esta pregunta")
            )
            continue
        veredicto, evidencia = predicado(informe)
        salida.append((pregunta, veredicto, evidencia))
    return tuple(salida)


# =====================================================================
# CAPA DE EFECTO — de aqui abajo se ejecuta la CLI de verdad.
# =====================================================================


def _subcomandos_de_pack() -> tuple[str, ...]:
    """Los subcomandos de `sg pack`, DERIVADOS del parser real.

    MEDIDO, y el motivo esta medido: en B9 dos consultas al parser
    llamaban a una funcion que no existe y el `ImportError` se comia en un
    `return ()`. Lista vacia y «no hay comandos» son indistinguibles, y esa
    confusion es la que hace que un guard de verde en falso. Por eso aqui
    no hay captura silenciosa: si el parser no se puede leer, revienta.
    """
    sys.path.insert(0, str(RAIZ / "src"))
    try:
        from skillgraph.cli.parser import build_parser
    except ImportError as exc:  # pragma: no cover - el paquete no esta importable
        raise RuntimeError(f"no se pudo importar el parser: {exc}") from exc

    parser = build_parser()
    grupos = getattr(getattr(parser, "_subparsers", None), "_group_actions", ())
    if not grupos:
        raise RuntimeError("el parser no declara subparsers")
    for nombre, sub in grupos[0].choices.items():
        if nombre == "pack":
            sub_grupos = getattr(getattr(sub, "_subparsers", None), "_group_actions", ())
            if not sub_grupos:
                raise RuntimeError("`sg pack` no declara subcomandos")
            return tuple(sorted(sub_grupos[0].choices))
    raise RuntimeError("el parser no declara un comando `pack`")


def _ejecutar(argv: Sequence[str], cwd: Path) -> Respuesta:
    proc = subprocess.run(
        [sys.executable, "-m", "skillgraph", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        env={"PYTHONPATH": str(RAIZ / "src"), "PATH": "/usr/bin:/bin", "HOME": str(cwd)},
    )
    return Respuesta(rc=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _escribir_pack(directorio: Path, nombre: str, version: str, requiere: str) -> Path:
    """Un pack instalable de verdad, escrito en el formato de la CLI.

    El manifiesto de B8 viaja en `spec.manifest`, que es donde el pack
    puede llevar cosas sin que el tipo `DomainPack` las rechace.
    """
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / f"{nombre}.md"
    ruta.write_text(
        f"""---
apiVersion: skillgraph.dev/v1alpha1
kind: DomainPack
metadata:
  namespace: packs
  name: {nombre}
spec:
  version: {version}
  manifest:
    name: {nombre}
    version: {version}
    kind: DomainPack
    isolation: declarative
    requires:
      skillgraph: "{requiere}"
---
# {nombre}
""",
        encoding="utf-8",
    )
    return ruta


def _proyecto(directorio: Path) -> str:
    """Crea un proyecto de verdad y devuelve su nombre."""
    r = _ejecutar(["project", "create", "b11"], directorio)
    if r.rc != 0:
        raise RuntimeError(f"no se pudo crear el proyecto: {r.combinado}")
    return "b11"


def preguntar() -> Informe:
    """Mide ejecutando la CLI. Es la unica parte que habla con el mundo."""
    try:
        subcomandos = _subcomandos_de_pack()
    except Exception as exc:
        vacio = Respuesta(2, "", "no medido")
        return Informe((), vacio, vacio, vacio, vacio, vacio, vacio, vacio, "", str(exc))

    faltantes = [c for c in CICLO_ESPERADO if c not in subcomandos]
    if faltantes:
        # Las preguntas que dependen de un comando que no existe se
        # contestan con la EJECUCION que daria el runner al invocarlo, no
        # con un veredicto inventado: asi el informe dice «este comando no
        # esta» en vez de «este comando esta roto», que son cosas distintas.
        inexistente = Respuesta(
            2, "", f"el comando no existe todavia: `sg pack` no expone {faltantes}"
        )
        return Informe(
            subcomandos,
            inexistente,
            inexistente,
            inexistente,
            inexistente,
            inexistente,
            inexistente,
            inexistente,
        )

    with tempfile.TemporaryDirectory(prefix="sg-b11-") as temporal:
        raiz = Path(temporal)
        _proyecto(raiz)
        bueno = _escribir_pack(raiz / "packs", "acme", "0.1.0", ">=0.1.0")
        malo = _escribir_pack(raiz / "packs", "villano", "0.1.0", ">=99.0.0")

        install_valido = _ejecutar(["pack", "install", "b11", str(bueno)], raiz)
        install_malo = _ejecutar(["pack", "install", "b11", str(malo)], raiz)
        nuevo = _escribir_pack(raiz / "packs2", "acme", "0.2.0", ">=0.1.0")
        update_mayor = _ejecutar(["pack", "update", "b11", str(nuevo)], raiz)
        viejo = _escribir_pack(raiz / "packs3", "acme", "0.0.9", ">=0.1.0")
        update_menor = _ejecutar(["pack", "update", "b11", str(viejo)], raiz)
        remove_inexistente = _ejecutar(["pack", "remove", "b11", "nada-esta-instalado"], raiz)
        list_con = _ejecutar(["pack", "list", "b11"], raiz)

        with tempfile.TemporaryDirectory(prefix="sg-b11-vacio-") as vacio_dir:
            vacio_raiz = Path(vacio_dir)
            _proyecto(vacio_raiz)
            list_vacio = _ejecutar(["pack", "list", "b11"], vacio_raiz)

        return Informe(
            subcomandos=subcomandos,
            install_incompatible=install_malo,
            update_menor=update_menor,
            update_mayor=update_mayor,
            remove_inexistente=remove_inexistente,
            list_con_un_pack=list_con,
            version_esperada_en_list=VERSION_TRAS_UPDATE,
            list_vacio=list_vacio,
            install_valido=install_valido,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mide el ciclo de vida de los packs, propiedad por propiedad."
    )
    parser.add_argument("--json", action="store_true", help="volcar el informe como JSON")
    args = parser.parse_args(argv)

    informe = preguntar()
    resultados = evaluar(informe)
    resumen: dict[str, int] = {}
    for _, veredicto, _ in resultados:
        resumen[veredicto] = resumen.get(veredicto, 0) + 1
    abierto = [p for p, v, _ in resultados if v == "OPEN"]
    payload = {
        "instrumento": "scripts/measure_b11_pack_lifecycle.py",
        "preguntas": [{"pregunta": p, "veredicto": v, "evidencia": e} for p, v, e in resultados],
        "resumen": resumen,
        "abiertas": abierto,
        "listo": not abierto,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for pregunta, veredicto, evidencia in resultados:
            print(f"[{veredicto:>14}] {pregunta}")
            print(f"                {evidencia}")
        print()
        print(" · ".join(f"{k}: {v}" for k, v in sorted(resumen.items())))
    # rc 1 = medido y no se cumple; rc 2 = no se pudo medir. La distincion
    # importa porque «no cumple» y «nadie lo ha medido» piden acciones
    # distintas, y con un solo rc no se puede distinguirlas.
    if informe.error or "NO_MEASURABLE" in resumen:
        return 2
    return 0 if not abierto else 1


if __name__ == "__main__":
    raise SystemExit(main())
