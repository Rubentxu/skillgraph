#!/usr/bin/env python3
"""B10 — las superficies publicas, DECLARADAS y VIGILADAS.

Por que este script existe
--------------------------
B9 midio las veinte propiedades del gate de 1.0 una a una. Dos salieron
``OPEN`` por la misma razon y solo por esa: **falta de certificacion, no de
codigo**.

``resource/controller API estable``
    ``skillgraph.core.__init__`` no declaraba ``__all__``. Un paquete sin
    superficie declarada no tiene nada que pueda decir que es estable.

``CLI estable``
    no existia ``docs/cli-surface.json``. Once comandos de primer nivel
    podem cambiar sin que nada lo note.

La trampa de cerrar las dos escribiendo el fichero
--------------------------------------------------
Las dos propiedades se cierran en **veinte segundos** tocando un fichero: se
escribe un ``__all__`` y se hace ``touch docs/cli-surface.json``. Los dos
veredictos pasan a ``PASS`` y el gate de 1.0 no se acerca ni un milimetro,
porque lo que miden no era «existe un fichero» sino «existe una superficie
certificada».

Por eso este script no comprueba que el fichero exista: **lo ejecuta**. Y
las dos superficies se **generan desde el arbol** y se comparan con lo
declarado, de modo que un ``touch`` no produce un snapshot valido sino un
JSON que no describe nada, y la comparacion lo dice nombrando comandos.

Donde viven las superficies, y por que no en ``docs/``
-------------------------------------------------------
``docs/*`` esta en ``.gitignore`` salvo tres carve-outs. Un snapshot que no
viaja no es una superficie declarada: es un fichero local que solo existe en
la maquina donde se genero — exactamente el defecto que B8 midio con el hijo
de concurrencia. Por eso viven en ``SURFACES/`` en la raiz, versionadas, y
por eso el guard incluye una comprobacion de que estan en ``git ls-files``.

Diseno: puro por encima, efecto por debajo
------------------------------------------
``evaluar_*`` son **funciones puras**: reciben un ``Informe`` y devuelven
tuplas de ``Problema``. No leen disco, no importan el paquete, no miran el
reloj. Toda la parte que habla con el mundo vive en ``medir()``.

Eso no es estetica: es lo que permite que un test construya un ``Informe``
falso y compruebe que el evaluador **se pone rojo**, que es la unica manera
de saber que el evaluador sabe ponerse rojo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Como se llaman los dos ficheros de superficie. El directorio se pasa
#: como parametro (`--repo`), no se lee de un global: el instrumento
#: tiene que poder correr contra otro arbol sin que nadie tenga que
#: reconfigurar el modulo.
NOMBRE_CORE: Final[str] = "core-surface.json"
NOMBRE_CLI: Final[str] = "cli-surface.json"

VERSAION_ESPERADA: Final[str] = "sggw_superficie/v1"


@dataclass(frozen=True, slots=True)
class Problema:
    """Un incumplimiento del contrato. Inmutable: se acumula en tuplas."""

    codigo: str
    mensaje: str


@dataclass(frozen=True, slots=True)
class Informe:
    """Lo medido sobre el arbol y las declaraciones. Inmutable."""

    core_declarado_en_paquete: tuple[str, ...]
    core_por_modulo: Mapping[str, tuple[str, ...]]
    core_no_resolubles: tuple[str, ...]
    core_ajenos: tuple[str, ...]
    superficies_declaradas: tuple[str, ...]
    superficies_en_git: tuple[str, ...]
    cli_comandos: tuple[str, ...]
    cli_subcomandos: Mapping[str, tuple[str, ...]]
    runner_all: tuple[str, ...]
    declared_core: tuple[str, ...] | None
    declared_cli_comandos: tuple[str, ...] | None
    declared_cli_subcomandos: Mapping[str, tuple[str, ...]] | None
    declared_runner_all: tuple[str, ...] | None
    declared_version_core: str
    declared_version_cli: str
    hubo_error: bool = False
    error: str = ""


# =====================================================================
# CAPA PURA — de aqui abajo no se lee disco ni se importa el paquete.
# Las funciones toman un Informe y devuelven tuplas de Problema.
# =====================================================================


def evaluar_core_declarado(informe: Informe) -> tuple[Problema, ...]:
    """S1. El paquete declara una superficie, y la declara COMPLETA.

    Dos mitades, y las dos importan. Que exista ``__all__`` es la mitad
    superficial: un ``__all__`` con tres nombres de sesenta tambien «declara
    superficie», y por eso la comparacion es contra la union de los tres
    modulos, no contra un numero.
    """
    problemas: list[Problema] = []
    declarados = set(informe.core_declarado_en_paquete)
    esperados = {n for nombres in informe.core_por_modulo.values() for n in nombres}
    if not declarados:
        return (
            Problema(
                "core_sin_all",
                "core/__init__.py no declara __all__: la superficie publica no esta "
                "declarada, luego no hay nada que pueda decir que es estable",
            ),
        )
    faltan = sorted(esperados - declarados)
    if faltan:
        problemas.append(
            Problema(
                "core_incompleto",
                f"core/__init__.py declara {len(declarados)} simbolos y {len(faltan)} "
                f"de sus modulos no reexporta: {faltan}",
            )
        )
    sobra = sorted(declarados - esperados - {"MODULOS", "SUPERFICIE"})
    if sobra:
        problemas.append(
            Problema(
                "core_ajeno",
                f"core/__init__.py declara simbolos que ningun modulo del nucleo "
                f"declara: {sobra}. Una superficie que publica algo que no existe no "
                "es una superficie, es una promesa",
            )
        )
    if informe.core_no_resolubles:
        problemas.append(
            Problema(
                "core_irresoluble",
                f"core/__init__.py declara simbolos que no se pueden importar: "
                f"{list(informe.core_no_resolubles)}",
            )
        )
    return tuple(problemas)


def evaluar_core_snapshot(informe: Informe, donde: str = "surfaces") -> tuple[Problema, ...]:
    """S2. La superficie del nucleo no se ha movido desde el snapshot.

    Aqui esta el cierre real de la propiedad: el snapshot **se compara con
    el arbol**, no se comprueba que exista. Un ``touch`` deja el fichero ahi
    con la forma correcta y el contenido de la superficie anterior, y eso es
    un cambio de superficie sin declarar.

    ``donde`` es solo el nombre del directorio, para que el mensaje diga donde
    mirarlo. Es un parametro y no una constante de modulo porque esta funcion
    es pura: leer un global seria leer el mundo.
    """
    if informe.hubo_error:
        return (Problema("core_snapshot", f"no se pudo medir: {informe.error}"),)
    if informe.declared_version_core != VERSAION_ESPERADA:
        return (
            Problema(
                "core_snapshot_formato",
                f"la superficie del nucleo declara el formato "
                f"{informe.declared_version_core!r} y este instrumento entiende "
                f"{VERSAION_ESPERADA!r}: un snapshot de otra forma no se puede "
                "comparar, y no comparar no es pasar",
            ),
        )
    if informe.declared_core is None:
        return (
            Problema(
                "core_snapshot_ausente",
                f"no existe {donde}/{NOMBRE_CORE}: la superficie del "
                f"nucleo son {len(informe.core_declarado_en_paquete)} simbolos y no hay "
                "contra que compararla, luego puede cambiar sin que nada lo note",
            ),
        )
    esperados = tuple(
        sorted(n for n in informe.core_declarado_en_paquete if n not in {"MODULOS", "SUPERFICIE"})
    )
    declarados = tuple(sorted(informe.declared_core))
    if declarados == esperados:
        return ()
    anadidos = sorted(set(esperados) - set(declarados))
    perdidos = sorted(set(declarados) - set(esperados))
    detalle = []
    if anadidos:
        detalle.append(f"+{anadidos}")
    if perdidos:
        detalle.append(f"-{perdidos}")
    return (
        Problema(
            "core_superficie_movida",
            f"la superficie del nucleo cambio y el snapshot no lo registra "
            f"({', '.join(detalle)}): {len(declarados)} declarados frente a "
            f"{len(esperados)} reales",
        ),
    )


def evaluar_cli_snapshot(informe: Informe, donde: str = "surfaces") -> tuple[Problema, ...]:
    """S3. La CLI no expone un comando que el snapshot no declara.

    Se derivan las tres capas: los comandos de primer nivel, los subcomandos
    de cada uno y el ``runner.__all__`` que el blueprint (ADR-0018) declara
    como la superficie publica del CLI. Las tres se comparan.

    El motivo de mirar tambien ``runner.__all__``: un comando puede anadirse
    y registrar su handler sin tocar ``__all__``, y entonces la superficie
    que ADR-0018 dice que no cambia ha cambiado. Comparar solo los nombres de
    comando deja pasar justo ese caso.
    """
    if informe.hubo_error:
        return (Problema("cli_snapshot", f"no se pudo medir: {informe.error}"),)
    if informe.declared_version_cli != VERSAION_ESPERADA:
        return (
            Problema(
                "cli_snapshot_formato",
                f"la superficie de la CLI declara el formato "
                f"{informe.declared_version_cli!r} y este instrumento entiende "
                f"{VERSAION_ESPERADA!r}",
            ),
        )
    if informe.declared_cli_comandos is None or informe.declared_cli_subcomandos is None:
        return (
            Problema(
                "cli_snapshot_ausente",
                f"no existe {donde}/{NOMBRE_CLI}: la CLI expone "
                f"{len(informe.cli_comandos)} comandos y no hay contra que compararlos, "
                "luego su superficie puede cambiar sin que nada lo note",
            ),
        )
    problemas: list[Problema] = []
    declarados = set(informe.declared_cli_comandos)
    reales = set(informe.cli_comandos)
    anadidos = sorted(reales - declarados)
    if anadidos:
        problemas.append(
            Problema(
                "cli_comando_nuevo",
                f"la CLI expone comandos que el snapshot no declara: {anadidos}. "
                "Anadir un comando es cambiar la superficie: o se regenera el "
                "snapshot o no es una superficie estable",
            )
        )
    # La comparacion es en las DOS direcciones, y esto se corrigio midiendo.
    # MEDIDO: la primera version solo miraba `reales - declarados`, asi que
    # un snapshot al que se le anadia un comando INVENTADO pasaba en verde:
    # el guard sabia detectar que la CLI tumbuh y no que la declaracion
    # miente. Y esa es justo la mitad que importa, porque el snapshot es lo
    # que dice «esto es lo que hay», no una nota.
    #
    # Un guard que solo sabe dar verde en una direccion no mide: mide el
    # caso que nadie va a tener.
    perdidos = sorted(declarados - reales)
    if perdidos:
        problemas.append(
            Problema(
                "cli_comando_inexistente",
                f"el snapshot declara comandos que la CLI no expone: {perdidos}. "
                "Una declaracion que nombra algo que no existe no es una "
                "declaracion de la superficie: es una de otra cosa",
            )
        )
    for grupo in sorted(reales | declarados):
        sub_reales = set(informe.cli_subcomandos.get(grupo, ()))
        sub_declarados = set((informe.declared_cli_subcomandos or {}).get(grupo, ()))
        if sub_reales != sub_declarados:
            problemas.append(
                Problema(
                    "cli_subcomando_movido",
                    f"`sg {grupo}` expone {sorted(sub_reales)} y el snapshot declara "
                    f"{sorted(sub_declarados)}",
                )
            )
    if informe.declared_runner_all is not None:
        reales_all = set(informe.runner_all)
        declarados_all = set(informe.declared_runner_all)
        if reales_all != declarados_all:
            problemas.append(
                Problema(
                    "cli_runner_all_movido",
                    f"runner.__all__ cambio: {sorted(reales_all ^ declarados_all)} "
                    f"({len(informe.runner_all)} simbolos reales frente a "
                    f"{len(informe.declared_runner_all)} declarados). ADR-0018 declara "
                    "esta superficie como estable",
                )
            )
    return tuple(problemas)


def evaluar_superficies_versionadas(informe: Informe) -> tuple[Problema, ...]:
    """S4. Una superficie que no viaja no declara nada.

    Es el defecto que B8 midio con el hijo de concurrencia: el modulo de
    tests versionado, el hijo en ``.pipelinek/`` ignorado por git. En un
    clon limpio estos dos JSON no existen, y entonces el guard no ve que
    la superficie se ha movido: no ve nada. Aqui se mira, por cada
    superficie, si el fichero esta en `git ls-files`.

    La comparacion es por **fichero**, no por directorio: un `.gitkeep` en
    `surfaces/` no declara la superficie, y un directorio entero excluido
    haria que un solo carve-out sacase el resto fuera sin que nada lo note.
    B8 escribio este criterio y lo midio en las dos direcciones.
    """
    if informe.hubo_error:
        return (Problema("superficies_versionadas", f"no se pudo medir: {informe.error}"),)
    esperados = informe.superficies_declaradas
    versionadas = set(informe.superficies_en_git)
    faltan = [r for r in esperados if r not in versionadas]
    if not faltan:
        return ()
    return (
        Problema(
            "superficie_no_versionada",
            f"estos ficheros de superficie no estan en `git ls-files`: {sorted(faltan)}. "
            "Una superficie que no viaja declara lo que declare la maquina que la "
            "genero, no lo que declara el repositorio, y en un clon limpio el guard "
            "no tendria nada contra que comparar",
        ),
    )


def evaluar(informe: Informe) -> tuple[Problema, ...]:
    """Los cuatro contratos, en orden. Puro: no lee nada."""
    return (
        *evaluar_core_declarado(informe),
        *evaluar_core_snapshot(informe),
        *evaluar_cli_snapshot(informe),
        *evaluar_superficies_versionadas(informe),
    )


def codigos_de(problemas: tuple[Problema, ...]) -> frozenset[str]:
    return frozenset(p.codigo for p in problemas)


# =====================================================================
# CAPA DE EFECTO — de aqui abajo se lee disco y se importa el paquete.
# =====================================================================


def _version_publica(modulo: Any) -> tuple[str, ...]:
    """El ``__all__`` de un modulo, como tupla. Sin capturarlo: si no existe, no hay superficie."""
    declarados = getattr(modulo, "__all__", None)
    if declarados is None:
        return ()
    return tuple(declarados)


def _modulos_del_nucleo() -> tuple[tuple[str, Any], ...]:
    import skillgraph.core as nucleo

    declarados = getattr(nucleo, "MODULOS", ())
    if not declarados:
        raise RuntimeError("skillgraph.core no declara MODULOS: no se sabe que auditar")
    return tuple((nombre, getattr(nucleo, nombre)) for nombre in declarados)


def _comandos_de_la_cli() -> tuple[dict[str, list[str]], tuple[str, ...]]:
    """Los comandos y subcomandos del parser de verdad, y el ``runner.__all__``.

    MEDIDO en B9, y el motivo esta medido: la primera version llamaba a
    ``construir_parser()``, que no existe —el nombre real es
    ``build_parser()``—, y el ``ImportError`` se comia en un ``return ()``.
    Dos consultas devolvieron lista vacia y se midpointaron dos veredictos,
    los dos falsos y los dos en la direccion de alarmar de mas.

    Por eso aqui no hay captura silenciosa: si el parser no se puede leer,
    revienta. Una superficie vacia es indistinguible de una superficie de
    cero comandos, y esa confusion es exactamente la que hace que un guard
    de verde en falso.
    """
    from skillgraph.cli import runner
    from skillgraph.cli.parser import build_parser

    parser = build_parser()
    grupos = getattr(getattr(parser, "_subparsers", None), "_group_actions", ())
    if not grupos:
        raise RuntimeError("el parser no declara subparsers")
    hijos: dict[str, list[str]] = {}
    for nombre, sub in grupos[0].choices.items():
        sub_grupos = getattr(getattr(sub, "_subparsers", None), "_group_actions", ())
        hijos[nombre] = sorted(sub_grupos[0].choices) if sub_grupos else []
    return hijos, _version_publica(runner)


def _leer_declaracion(ruta: Path) -> tuple[Any, str]:
    """Lee un snapshot. Devuelve ``(carga, "")`` o ``(None, por que fallo)."""
    if not ruta.is_file():
        return None, f"no existe {ruta.relative_to(ruta.parent.parent)}"
    try:
        return json.loads(ruta.read_text(encoding="utf-8")), ""
    except json.JSONDecodeError as exc:
        return None, f"{ruta.name} no es JSON legible: {exc}"


def _versionadas(raiz: Path, rutas: tuple[Path, ...]) -> tuple[str, ...]:
    proc = subprocess.run(
        ["git", "ls-files", "--", *[str(r.relative_to(raiz)) for r in rutas]],
        cwd=raiz,
        capture_output=True,
        text=True,
        check=True,
    )
    versionados = set(proc.stdout.split())
    return tuple(
        sorted(str(r.relative_to(raiz)) for r in rutas if str(r.relative_to(raiz)) in versionados)
    )


def medir(raiz: Path, directorio: Path) -> Informe:
    """Mide el arbol. Es la unica parte que habla con el mundo."""
    import skillgraph.core as nucleo

    try:
        por_modulo = {nombre: _version_publica(modulo) for nombre, modulo in _modulos_del_nucleo()}
        declarados = _version_publica(nucleo)
        irresolubles = tuple(n for n in declarados if not hasattr(nucleo, n))
        hijos, runner_all = _comandos_de_la_cli()
    except Exception as exc:
        return Informe(
            (),
            {},
            (),
            (),
            (),
            (),
            {},
            (),
            None,
            None,
            None,
            None,
            "",
            "",
            True,
            str(exc),
        )

    esperados = {n for nombres in por_modulo.values() for n in nombres}
    ajenos = tuple(sorted(set(declarados) - esperados - {"MODULOS", "SUPERFICIE"}))

    carga_core, _ = _leer_declaracion(directorio / NOMBRE_CORE)
    carga_cli, _ = _leer_declaracion(directorio / NOMBRE_CLI)

    return Informe(
        core_declarado_en_paquete=declarados,
        core_por_modulo=por_modulo,
        core_no_resolubles=irresolubles,
        core_ajenos=ajenos,
        superficies_declaradas=(
            f"surfaces/{NOMBRE_CORE}",
            f"surfaces/{NOMBRE_CLI}",
        ),
        superficies_en_git=_versionadas(raiz, (directorio / NOMBRE_CORE, directorio / NOMBRE_CLI)),
        cli_comandos=tuple(sorted(hijos)),
        cli_subcomandos={k: tuple(v) for k, v in sorted(hijos.items())},
        runner_all=runner_all,
        declared_core=tuple(carga_core["superficie"])
        if isinstance(carga_core, dict) and "superficie" in carga_core
        else None,
        declared_cli_comandos=tuple(carga_cli["comandos"])
        if isinstance(carga_cli, dict) and "comandos" in carga_cli
        else None,
        declared_cli_subcomandos=(
            {k: tuple(v) for k, v in carga_cli["subcomandos"].items()}
            if isinstance(carga_cli, dict) and "subcomandos" in carga_cli
            else None
        ),
        declared_runner_all=tuple(carga_cli["runner_all"])
        if isinstance(carga_cli, dict) and "runner_all" in carga_cli
        else None,
        declared_version_core=(carga_core or {}).get("version", "")
        if isinstance(carga_core, dict)
        else "",
        declared_version_cli=(carga_cli or {}).get("version", "")
        if isinstance(carga_cli, dict)
        else "",
    )


def construir_declaraciones(informe: Informe) -> dict[str, dict[str, Any]]:
    """Las dos declaraciones, generadas desde el arbol. Puro: solo escribe memoria."""
    if informe.hubo_error:
        raise RuntimeError(
            f"no se puede declarar una superficie que no se pudo medir: {informe.error}"
        )
    return {
        NOMBRE_CORE: {
            "version": VERSAION_ESPERADA,
            "superficie": sorted(
                n for n in informe.core_declarado_en_paquete if n not in {"MODULOS", "SUPERFICIE"}
            ),
        },
        NOMBRE_CLI: {
            "version": VERSAION_ESPERADA,
            "comandos": sorted(informe.cli_comandos),
            "subcomandos": {k: sorted(v) for k, v in sorted(informe.cli_subcomandos.items())},
            "runner_all": sorted(informe.runner_all),
        },
    }


def escribir_declaraciones(directorio: Path, informe: Informe) -> tuple[Path, ...]:
    """Escribe los snapshots. La unica funcion de este fichero que muta disco."""
    directorio.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    for nombre, carga in construir_declaraciones(informe).items():
        destino = directorio / nombre
        destino.write_text(
            json.dumps(carga, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        escritos.append(destino)
    return tuple(escritos)


def formatear(problemas: tuple[Problema, ...]) -> str:
    if not problemas:
        return (
            "OK: las superficies del nucleo y de la CLI estan declaradas, "
            "versionadas y coinciden con el arbol."
        )
    lineas = [f"FALLO: {len(problemas)} incumplimiento(s) del contrato de superficies"]
    lineas.extend(f"  [{p.codigo}] {p.mensaje}" for p in problemas)
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Comprueba que las superficies publicas estan declaradas y no se han movido."
    )
    parser.add_argument("--json", action="store_true", help="volcar el informe como JSON")
    parser.add_argument(
        "--actualizar",
        action="store_true",
        help="regenerar los snapshots desde el arbol y salir",
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    raiz = args.repo.resolve()
    directorio = raiz / "surfaces"

    informe = medir(raiz, directorio)

    if args.actualizar:
        if informe.hubo_error:
            print(f"FALLO: no se pudo medir la superficie: {informe.error}")
            return 1
        for ruta in escribir_declaraciones(directorio, informe):
            print(f"escrito {ruta.relative_to(raiz)}")
        return 0

    problemas = evaluar(informe)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not problemas,
                    "problemas": [{"codigo": p.codigo, "mensaje": p.mensaje} for p in problemas],
                    "medido": {
                        "simbolos_core": len(informe.core_declarado_en_paquete),
                        "comandos_cli": len(informe.cli_comandos),
                        "simbolos_runner": len(informe.runner_all),
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
