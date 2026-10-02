#!/usr/bin/env python3
"""WI-97: comprueba que el paquete se construye y lleva lo que declara.

Por que este script existe
--------------------------
``pyproject.toml`` declara cinco contratos de empaquetado y hasta WI-97
ninguno lo comprobaba ninguna herramienta: ni la suite (2567 tests, cero
referencias a ``hatchling``/``uv build``/``entry_points``) ni los stages de
``.pipeline.kts``. La cadena de release ``git -> __version__ -> pyproject ->
wheel`` se detenia antes de su ultimo eslabon, y todo el aparataje de SemVer
(AGENTS.md §12) medía un numero sobre un paquete que nadie habia visto
construido.

Este script construye el wheel y el sdist reales y verifica:

  C1  la version del artefacto es la que declara el codigo;
  C2  cada ``[project.scripts]`` se publica en el artefacto, con su target;
  C3  el wheel lleva todo modulo del paquete (heredando del arbol, sin una
      lista escrita a mano) y su ``py.typed``;
  C4  el sdist lleva exactamente lo que su ``include`` declara, mas los
      ficheros que el backend anade por definicion.

Diseno: puro por encima, efecto por debajo
------------------------------------------
``evaluar(informe)`` y sus cuatro descompuestos son **funciones puras**: no
leen disco, no miran el reloj y devuelven una tupla de problemas. Toda la
parte que habla con el mundo —construir, abrir el zip, instalar— vive en
``construir_y_medir()``.

Esa division no es estetica. Sin ella el unico modo de probar que el
checker detecta un modulo ausente seria construir el paquete con un modulo
de menos, y eso obliga a mutar el arbol de trabajo. Con la parte pura
separada, los tests construyen el contraejemplo con informes sinteticos.

Uso
---
    uv run python scripts/check_package_build.py            # contrato
    uv run python scripts/check_package_build.py --json     # informe
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CODIGO_VERSION_DRIFT: Final = "sg_build_version_drift"
CODIGO_SCRIPT_FALTANTE: Final = "sg_build_script_faltante"
CODIGO_SCRIPT_SOBRANTE: Final = "sg_build_script_sobrante"
CODIGO_TARGET_NO_RESOLUBLE: Final = "sg_build_target_no_resoluble"
CODIGO_MODULO_FALTANTE: Final = "sg_build_modulo_faltante"
CODIGO_MODULO_SOBRANTE: Final = "sg_build_modulo_sobrante"
CODIGO_PY_TYPED_AUSENTE: Final = "sg_build_py_typed_ausente"
CODIGO_SDIST_NO_VERSIONADO: Final = "sg_build_sdist_no_versionado"
CODIGO_SDIST_FALTA: Final = "sg_build_sdist_falta"
CODIGO_SDIST_SIN_DECLARAR: Final = "sg_build_sdist_sin_declarar"
CODIGO_SDIST_ESENCIAL_AUSENTE: Final = "sg_build_sdist_esencial_ausente"

# Ficheros que el backend anade por definicion y que, por tanto, no son
# deriva del `include` declarado: la licencia que declara `project.license`,
# el readme que declara `project.readme` y el `.gitignore` que el propio
# hatchling adjunta al sdist. Exigirlos en la lista seria una promesa que el
# backend no cumple; tolerarlos sin nombrarlos seria dejar el artefacto a su
# merced. Se nombran, que es lo unico que hace falta para que el contrato sea
# exacto. Medido en WI-97 sobre hatchling 1.32.4.
EXTRAS_BACKEND: Final[frozenset[str]] = frozenset({".gitignore", "LICENSE", "PKG-INFO"})

# Rutas que tienen que estar EN el sdist para que este sirva para lo que
# existe. Una lista corta y justificada, no una lista de inventario: el sdist
# de este repo existe para que otra persona reconstruya y PROBAR el paquete
# desde el fuente.
#   * src/skillgraph — sin el no hay paquete.
#   * tests           — sin el el artefacto se instala pero no se verifica.
#   * docs/blueprint  — la suite versionada lee `docs/blueprint/plan/UAT.md`
#     (tests/test_cli_uat.py); sin el, esos UAT pierden cobertura en silencio.
# Medido en WI-97: quitar `tests` del `only-include` reducia el sdist y
# ningun check de git lo notaba, porque una lista reducida no contradice a
# nada: solo deja de entregar.
RUTAS_ESENCIALES_SDIST: Final[frozenset[str]] = frozenset(
    {"src/skillgraph", "tests", "docs/blueprint"}
)


@dataclass(frozen=True, slots=True)
class Problema:
    """Un incumplimiento del contrato. Inmutable: se acumula en tuplas."""

    codigo: str
    mensaje: str


@dataclass(frozen=True, slots=True)
class InformeBuild:
    """Lo medido sobre los artefactos. Inmutable: lo evaluan funciones puras."""

    version_codigo: str
    version_wheel: str
    version_sdist: str
    modulos_en_fuente: frozenset[str]
    modulos_en_wheel: frozenset[str]
    py_typed_en_fuente: bool
    py_typed_en_wheel: bool
    scripts_declarados: tuple[tuple[str, str], ...]
    scripts_publicados: tuple[tuple[str, str], ...]
    targets_no_resolubles: frozenset[str]
    rutas_sdist: frozenset[str]
    rutas_versionadas: frozenset[str]
    rutas_declaradas: frozenset[str]
    hubo_error: bool = False
    error: str = ""


# =====================================================================
# CAPA PURA — de aqui abajo no se lee disco ni se mira el reloj.
# Las funciones toman un InformeBuild y devuelven tuplas de Problema.
# =====================================================================


def evaluar_version(informe: InformeBuild) -> tuple[Problema, ...]:
    """C1. El numero del artefacto sale del codigo, no de una copia aparte.

    Si `__version__` y la metadata del wheel coinciden pero el sdist no, el
    artefacto es inconsistente: son tres eslabones de una misma cadena y la
    cadena vale lo que vale su eslabon mas debil.
    """
    versiones = {
        "codigo": informe.version_codigo,
        "wheel": informe.version_wheel,
        "sdist": informe.version_sdist,
    }
    distintas = {k: v for k, v in versiones.items() if v != informe.version_codigo}
    if not distintas:
        return ()
    detalle = ", ".join(f"{k}={v!r}" for k, v in sorted(distintas.items()))
    return (
        Problema(
            CODIGO_VERSION_DRIFT,
            f"la version del artefacto no coincide con la del codigo: "
            f"codigo={informe.version_codigo!r}, {detalle}",
        ),
    )


def evaluar_scripts(informe: InformeBuild) -> tuple[Problema, ...]:
    """C2. Lo declarado en `[project.scripts]` y lo publicado, conjunto a conjunto.

    Faltante y sobrante son la misma deriva en direcciones opuestas: un
    entry point declarado que no sale impide usar el comando; uno publicado
    que no se declaro es superficie de API que nadie reviso.
    """
    declarados = dict(informe.scripts_declarados)
    publicados = dict(informe.scripts_publicados)

    problemas: list[Problema] = []
    for nombre in sorted(declarados.keys() - publicados.keys()):
        problemas.append(
            Problema(
                CODIGO_SCRIPT_FALTANTE,
                f"script declarado y no publicado en el artefacto: {nombre} = {declarados[nombre]}",
            )
        )
    for nombre in sorted(publicados.keys() - declarados.keys()):
        problemas.append(
            Problema(
                CODIGO_SCRIPT_SOBRANTE,
                f"script publicado en el artefacto y no declarado: {nombre} = {publicados[nombre]}",
            )
        )
    for nombre in sorted(declarados.keys() & publicados.keys()):
        if declarados[nombre] != publicados[nombre]:
            problemas.append(
                Problema(
                    CODIGO_SCRIPT_FALTANTE,
                    f"script publicado con otro target: {nombre} declara "
                    f"{declarados[nombre]!r} y el artefacto trae {publicados[nombre]!r}",
                )
            )
    for target in sorted(informe.targets_no_resolubles):
        problemas.append(
            Problema(
                CODIGO_TARGET_NO_RESOLUBLE,
                f"el target declarado no resuelve a nada invocable: {target!r}. "
                f"El artefacto lo publica igual, y comparar lo declarado con lo "
                f"publicado no lo nota: el segundo se deriva del primero",
            )
        )
    return tuple(problemas)


def evaluar_modulos(informe: InformeBuild) -> tuple[Problema, ...]:
    """C3. El wheel lleva todo el paquete, y el paquete es el arbol de fuentes.

    El invariante se deriva de `modulos_en_fuente` —todo `.py` bajo
    `src/skillgraph/`— en vez de una lista de modulos escrita a mano. Es el
    mismo argumento que los suelos de cobertura por prefijo de WI-94: una
    lista escrita a mano es correcta al escribirla y falsa en cuanto alguien
    anade un modulo.
    """
    problemas: list[Problema] = []
    for ausente in sorted(informe.modulos_en_fuente - informe.modulos_en_wheel):
        problemas.append(
            Problema(
                CODIGO_MODULO_FALTANTE,
                f"modulo del paquete ausente en el wheel: {ausente}",
            )
        )
    for sobrante in sorted(informe.modulos_en_wheel - informe.modulos_en_fuente):
        problemas.append(
            Problema(
                CODIGO_MODULO_SOBRANTE,
                f"modulo en el wheel que no esta en el arbol de fuentes: {sobrante}",
            )
        )
    if informe.py_typed_en_fuente and not informe.py_typed_en_wheel:
        problemas.append(
            Problema(
                CODIGO_PY_TYPED_AUSENTE,
                "el paquete declara py.typed pero el wheel no lo incluye: "
                "los type checkers lo trataran como no tipado",
            )
        )
    return tuple(problemas)


def evaluar_sdist(informe: InformeBuild) -> tuple[Problema, ...]:
    """C4. El sdist depende del commit, no del arbol de trabajo.

    El invariante no es «el sdist lleva lo que dice el `include`»: es
    «el sdist no lleva nada que git no versione». La segunda es mas fuerte y
    la que da contenido.

    Medido en WI-97: el `include` declaraba nueve rutas y el artefacto
    salia con catorce de primer nivel —`bench/` y `docs/` sin declararse— y,
    cambiando un solo patron, tambien con `audits/`. El `include` de
    hatchling es un filtro, no una lista blanca, y lo que no nombra se cuela
    sin avisar. Un artefacto que se cuela ficheros del arbol de trabajo
    hace que dos arboles con el mismo commit produzcan sdists distintos.

    La segunda mitad del contrato es la promesa complementaria, y son dos:
    cada ruta que el `include` declara tiene que estar en el artefacto, y
    cada raiz que el artefacto trae tiene que estar declarada. Declarar lo
    que no llega al sdist es una promesa falsa; no declarar lo que llega es
    la misma mentira por el otro lado.

    Comparar conjuntos y no listas: el orden en que el backend serializa las
    entradas no es parte del contrato.
    """
    reales = informe.rutas_sdist - EXTRAS_BACKEND

    problemas: list[Problema] = []
    for colada in sorted(reales - informe.rutas_versionadas):
        problemas.append(
            Problema(
                CODIGO_SDIST_NO_VERSIONADO,
                f"el sdist incluye {colada!r} y git no la versiona: el artefacto "
                f"depende de lo que haya en el arbol de trabajo, no del commit",
            )
        )
    for declarada in sorted(informe.rutas_declaradas):
        if not _cubre(declarada, reales):
            problemas.append(
                Problema(
                    CODIGO_SDIST_FALTA,
                    f"ruta declarada en `include` y ausente del sdist: {declarada!r}. "
                    f"Declararla es una promesa que el artefacto no cumple",
                )
            )
    for esencial in sorted(RUTAS_ESENCIALES_SDIST):
        if not _cubre(esencial, reales):
            problemas.append(
                Problema(
                    CODIGO_SDIST_ESENCIAL_AUSENTE,
                    f"ruta esencial ausente del sdist: {esencial!r}. El sdist "
                    f"existe para que otro pueda reconstruir y probar el paquete "
                    f"desde el fuente",
                )
            )
    for no_declarada in sorted(_raices_no_declaradas(reales, informe.rutas_declaradas)):
        problemas.append(
            Problema(
                CODIGO_SDIST_SIN_DECLARAR,
                f"raiz en el sdist que el `include` no nombra: {no_declarada!r}. "
                f"El `include` de hatchling es un filtro, no una lista blanca: "
                f"lo que no nombra se cuela sin avisar",
            )
        )
    return tuple(problemas)


def _cubre(raiz: str, rutas: frozenset[str]) -> bool:
    """True si `raiz` aparece en el sdist como fichero o como prefijo de directorio."""
    prefijo = raiz.rstrip("/") + "/"
    return any(r == raiz.rstrip("/") or r.startswith(prefijo) for r in rutas)


def _raices_no_declaradas(reales: frozenset[str], declaradas: frozenset[str]) -> frozenset[str]:
    """Raices de primer nivel del artefacto que ninguna declaracion cubre.

    Comparar raices y no rutas completas: un `include` puede nombrar
    `docs/blueprint` y cubrir con el mismo efecto que nombrar `docs`, y exigir
    la coincidencia exacta de cada ruta haria el contrato fragil ante una
    reescritura equivalente del patron.
    """
    raices = {r.split("/", 1)[0] for r in reales}
    cubiertas = {d.split("/", 1)[0] for d in declaradas}
    return raices - cubiertas


def evaluar(informe: InformeBuild) -> tuple[Problema, ...]:
    """C1..C4. Compone las dimensiones; si el build fallo, no dice nada mas."""
    if informe.hubo_error:
        return (Problema(CODIGO_VERSION_DRIFT, f"el build fallo: {informe.error}"),)
    return (
        *evaluar_version(informe),
        *evaluar_scripts(informe),
        *evaluar_modulos(informe),
        *evaluar_sdist(informe),
    )


def codigos_de(problemas: tuple[Problema, ...]) -> frozenset[str]:
    return frozenset(p.codigo for p in problemas)


# =====================================================================
# CAPA DE EFECTO — de aqui abajo se lee disco y se lanzan procesos.
# =====================================================================


def _version_de_texto(texto: str) -> str:
    """Extrae `Version: x` de una cabecera de metadata. Vacio si no esta.

    Acepta las dos formas que aparecen en el repo: la cabecera estandar
    (`Version: 0.17.0.dev0`) y la asignacion de Python
    (`__version__ = "0.17.0.dev0"`). Una sola forma significaria que el
    checker solo funciona contra uno de los dos artefactos.
    """
    cabecera = re.search(r"^Version:\s*(?P<v>.+)$", texto, re.MULTILINE)
    if cabecera is not None:
        return cabecera.group("v").strip()
    asignacion = re.search(r"""^__version__\s*=\s*["'](?P<v>[^"']+)["']""", texto, re.MULTILINE)
    return asignacion.group("v").strip() if asignacion is not None else ""


def _modulos_de_arbol(raiz: Path) -> frozenset[str]:
    """Todo `.py` bajo `src/`, en forma relativa a `src/`."""
    paquete = raiz / "src"
    return frozenset(
        str(p.relative_to(paquete).as_posix())
        for p in sorted(paquete.rglob("*.py"))
        if "__pycache__" not in p.parts
    )


def _rutas_de_sdist(ruta: Path) -> frozenset[str]:
    """Todas las rutas del sdist, sin el directorio raiz que anade el backend."""
    with tarfile.open(ruta) as tf:
        nombres = tf.getnames()
    sin_raiz = (n.split("/", 1)[1] for n in nombres if "/" in n)
    return frozenset(r.rstrip("/") for r in sin_raiz if r.strip("/"))


def _rutas_versionadas(raiz: Path) -> frozenset[str]:
    """Lo que git versiona. El artefacto no debe depender de nada mas."""
    proc = subprocess.run(
        ["git", "-C", str(raiz), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return frozenset()
    return frozenset(f.strip() for f in proc.stdout.splitlines() if f.strip())


def _include_declarado(raiz: Path) -> frozenset[str]:
    """La raiz de cada ruta declarada en `[tool.hatch.build.targets.sdist]`.

    Se lee del fichero y no de una constante: si la declaracion cambia, el
    contrato cambia con ella, sin que nadie tenga que editar dos sitios.
    """
    texto = (raiz / "pyproject.toml").read_text(encoding="utf-8")
    bloque = _bloque_sdist(texto)
    entradas = re.findall(r'^\s*"([^"]+)"\s*,?\s*$', bloque, re.MULTILINE)
    return frozenset(e.split("/", 1)[0] for e in entradas)


def _bloque_sdist(texto: str) -> str:
    """El cuerpo del bloque sdist: desde su cabecera hasta la siguiente tabla.

    Se corta por linea porque el valor buscado (`only-include`) va dentro del
    bloque y `str.find('only-include')` sobre el fichero entero podria dar con
    una mencion en un comentario. Solo se leen entradas con el formato de
    lista de TOML (`"algo",`), asi que un valor suelto no puede colarse.
    """
    inicio = texto.find("[tool.hatch.build.targets.sdist]")
    if inicio < 0:
        return ""
    resto = texto[inicio:]
    corte = resto.find("\n[", 1)
    return resto if corte < 0 else resto[:corte]


def _scripts_declarados(raiz: Path) -> tuple[tuple[str, str], ...]:
    texto = (raiz / "pyproject.toml").read_text(encoding="utf-8")
    inicio = texto.find("[project.scripts]")
    if inicio < 0:
        return ()
    bloque = texto[inicio:]
    corte = bloque.find("\n[", 1)
    if corte >= 0:
        bloque = bloque[:corte]
    entradas = re.findall(r"^\s*([\w.-]+)\s*=\s*[\"']([\w.]+:[\w.]+)[\"']", bloque, re.MULTILINE)
    return tuple(entradas)


def _scripts_publicados_de_texto(texto: str) -> tuple[tuple[str, str], ...]:
    """Los `console_scripts` que el artefacto publica, en orden.

    Se limita a la seccion `[console_scripts]`: un `entry_points.txt` puede
    declarar grupos mas (entry points para plug-ins) que no son comandos y
    no forman parte del contrato de `[project.scripts]`.
    """
    dentro = False
    entradas: list[tuple[str, str]] = []
    for linea in texto.splitlines():
        if linea.strip().startswith("["):
            dentro = linea.strip() == "[console_scripts]"
            continue
        if dentro:
            encontrado = re.match(r"^\s*([\w.-]+)\s*=\s*([\w.]+:[\w.]+)\s*$", linea)
            if encontrado is not None:
                entradas.append((encontrado.group(1), encontrado.group(2)))
    return tuple(entradas)


def _primera_creacion(patron: str, directorio: Path) -> Path:
    candidatas = sorted(directorio.glob(patron))
    if not candidatas:
        raise FileNotFoundError(f"no se encontro {patron} en {directorio}")
    return candidatas[0]


def _comando_uv() -> list[str] | None:
    """Como lanzar `uv`, o `None` si no esta disponible.

    `sys.executable -m uv` NO vale dentro del venv del proyecto: uv no es un
    modulo importable, vive en el PATH como binario. Medido en WI-97 — el
    intento devolvio `No module named uv` y el checker reportaba un fallo de
    build que en realidad era un fallo de invocacion.
    """
    encontrado = shutil.which("uv")
    return [encontrado] if encontrado else None


def construir_y_medir(raiz: Path, destino: Path) -> InformeBuild:
    """Construye los dos artefactos y devuelve lo medido sobre ellos.

    El build va a un directorio temporal y se ejecuta con `cwd=raiz`: pasar la
    ruta como argumento posicional hace que `uv build` escriba en `<raiz>/dist`
    e ignore `--out-dir`, dejando el repositorio ensuciado.
    """
    comando = _comando_uv()
    if comando is None:
        return _informe_de_error("uv no esta en el PATH: no se puede construir el paquete")

    destino.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [*comando, "build", "--out-dir", str(destino)],
            cwd=str(raiz),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - entorno sin uv
        return _informe_de_error(f"no se pudo lanzar uv: {exc}")

    if proc.returncode != 0:
        return _informe_de_error(
            f"uv build devolvio {proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}"
        )

    try:
        wheel = _primera_creacion("*.whl", destino)
        sdist = _primera_creacion("*.tar.gz", destino)
        with zipfile.ZipFile(wheel) as zf:
            nombres = zf.namelist()
            meta = next(n for n in nombres if n.endswith(".dist-info/METADATA"))
            texto_meta = zf.read(meta).decode("utf-8", errors="replace")
        with tarfile.open(sdist) as tf:
            # El PKG-INFO cuelga del directorio raiz que el backend anade
            # (`skillgraph-<version>/PKG-INFO`). Buscarlo por sufijo y no por
            # nombre exacto: el nombre lleva la version, que es justo lo que
            # se esta midiendo.
            candidatos = [m for m in tf.getnames() if m.endswith("/PKG-INFO")]
            member = tf.extractfile(candidatos[0]) if candidatos else None
            texto_pkg = member.read().decode("utf-8", errors="replace") if member else ""
        return InformeBuild(
            version_codigo=_version_de_texto(
                (raiz / "src" / "skillgraph" / "__init__.py").read_text(encoding="utf-8")
            ),
            version_wheel=_version_de_texto(texto_meta),
            version_sdist=_version_de_texto(texto_pkg),
            modulos_en_fuente=_modulos_de_arbol(raiz),
            modulos_en_wheel=frozenset(
                n for n in nombres if n.endswith(".py") and n.startswith("skillgraph/")
            ),
            py_typed_en_fuente=(raiz / "src" / "skillgraph" / "py.typed").exists(),
            py_typed_en_wheel="skillgraph/py.typed" in nombres,
            scripts_declarados=_scripts_declarados(raiz),
            scripts_publicados=_scripts_publicados_de_texto(texto_entry_points(zf_path=wheel)),
            targets_no_resolubles=frozenset(
                t for _, t in _scripts_declarados(raiz) if not _target_resuelve(t)
            ),
            rutas_sdist=_rutas_de_sdist(sdist),
            rutas_versionadas=_rutas_versionadas(raiz),
            rutas_declaradas=_include_declarado(raiz),
        )
    except (OSError, StopIteration, zipfile.BadZipFile, KeyError, tarfile.TarError) as exc:
        return _informe_de_error(f"no se pudo leer el artefacto: {exc}")


def texto_entry_points(*, zf_path: Path) -> str:
    with zipfile.ZipFile(zf_path) as zf:
        candidatas = [n for n in zf.namelist() if n.endswith(".dist-info/entry_points.txt")]
        return zf.read(candidatas[0]).decode("utf-8") if candidatas else ""


def _target_resuelve(target: str) -> bool:
    """¿El target `modulo:atributo` importa y es invocable?

    Comparar lo declarado con lo publicado no basta: lo publicado SE DERIVA
    de lo declarado, asi que un target equivocado aparece identico en los dos
    lados. Solo importar el modulo distingue «declaro algo que existe» de
    «declaro algo que no existe y el backend lo copia sin mirarlo».
    """
    modulo, _, atributo = target.partition(":")
    if not modulo or not atributo:
        return False
    try:
        import importlib

        return callable(getattr(importlib.import_module(modulo), atributo))
    except (ImportError, AttributeError, ValueError, TypeError):
        return False


def _informe_de_error(mensaje: str) -> InformeBuild:
    """Informe vacio con el error marcado: `evaluar` no dira nada mas.

    Un artefacto que no se pudo construir no se puede medir. Fabricar un
    informe con ceros seria peor que fallar: pareceria un paquete sin
    modulos ni scripts, que es un diagnostico distinto del real.
    """
    return InformeBuild(
        version_codigo="",
        version_wheel="",
        version_sdist="",
        modulos_en_fuente=frozenset(),
        modulos_en_wheel=frozenset(),
        py_typed_en_fuente=False,
        py_typed_en_wheel=False,
        scripts_declarados=(),
        scripts_publicados=(),
        targets_no_resolubles=frozenset(),
        rutas_sdist=frozenset(),
        rutas_versionadas=frozenset(),
        rutas_declaradas=frozenset(),
        hubo_error=True,
        error=mensaje,
    )


def formatear(problemas: tuple[Problema, ...]) -> str:
    if not problemas:
        return "OK: el paquete construye y cumple su contrato declarado."
    lineas = [f"FALLO: {len(problemas)} incumplimiento(s) del contrato de empaquetado"]
    lineas.extend(f"  [{p.codigo}] {p.mensaje}" for p in problemas)
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Comprueba que el paquete construye y lleva lo que declara."
    )
    parser.add_argument("--json", action="store_true", help="volcar el informe como JSON")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    import tempfile

    with tempfile.TemporaryDirectory(prefix="sg-build-") as temporal:
        informe = construir_y_medir(args.repo.resolve(), Path(temporal) / "dist")

    problemas = evaluar(informe)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not problemas,
                    "problemas": [{"codigo": p.codigo, "mensaje": p.mensaje} for p in problemas],
                    "informe": {
                        "version_codigo": informe.version_codigo,
                        "version_wheel": informe.version_wheel,
                        "version_sdist": informe.version_sdist,
                        "modulos_fuente": len(informe.modulos_en_fuente),
                        "modulos_wheel": len(informe.modulos_en_wheel),
                        "rutas_declaradas": sorted(informe.rutas_declaradas),
                        "rutas_sdist": len(informe.rutas_sdist),
                        "rutas_no_versionadas": sorted(
                            (informe.rutas_sdist - EXTRAS_BACKEND) - informe.rutas_versionadas
                        ),
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
