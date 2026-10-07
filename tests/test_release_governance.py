"""Tests de release governance (WI-01).

Contrato: el valor de ``skillgraph.__version__`` en HEAD debe
coincidir con la etiqueta git anotada más reciente (sin sufijo
``.devN``), o bien terminar en ``.devN`` si HEAD está en un commit
posterior a esa etiqueta.

Este test es el admission gate de release. Cualquier drift entre
``__version__`` y la etiqueta se considera release governance drift
y bloquea la release.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import skillgraph

REPO_ROOT = Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
DEV_SUFFIX_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.dev\d+$")


def _git(*args: str) -> str:
    """Ejecuta un comando git y devuelve stdout stripped."""
    result = subprocess.run(
        ("git", *args),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _head_sha() -> str:
    return _git("rev-parse", "HEAD")


def _describe_tags() -> str:
    """``git describe --tags --abbrev=0`` desde HEAD.

    Devuelve string vacío si no hay etiqueta reachable desde HEAD.
    """
    result = subprocess.run(
        ("git", "describe", "--tags", "--abbrev=0"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    # exit 0 si encuentra, 128 si no; nos da igual el exit, sólo el stdout.
    return result.stdout.strip()


def _head_is_at_tag(tag: str) -> bool:
    """¿El HEAD apunta literalmente al commit de la etiqueta?"""
    try:
        tag_sha = _git("rev-list", "-1", tag)
    except subprocess.CalledProcessError:
        return False
    return tag_sha == _head_sha()


def test_version_matches_git_tag() -> None:
    """Regla de release: __version__ debe coincidir con la etiqueta
    anotada más reciente, o terminar en .devN si HEAD es posterior.

    Tres ramas válidas:

    1. **HEAD en una etiqueta** ``v<X>.<Y>.<Z>`` y
       ``__version__ = <X>.<Y>.<Z>`` (release limpia).
    2. **HEAD posterior a una etiqueta reachable** y
       ``__version__`` con sufijo ``.devN`` (trabajo entre releases).
       La base SemVer puede ser la misma que la etiqueta (PATCH sobre
       la misma release) o superior (MINOR planeado).
    3. **Sin etiqueta reachable** y ``__version__`` con sufijo
       ``.devN`` (trabajo pre-release inicial).

    Drift real (rechazado): ``__version__ = X.Y.Z`` puro con HEAD no
    etiquetado, o ``__version__`` con sufijo .devN apuntando a una
    base que contradice una etiqueta anotada en el mismo commit.
    """
    version = skillgraph.__version__
    tag = _describe_tags()

    # Caso 0: no hay etiqueta reachable desde HEAD.
    # __version__ debe terminar en .devN (cualquier base válida).
    if not tag:
        assert DEV_SUFFIX_RE.match(version), (
            f"release governance drift: no hay etiqueta reachable "
            f"desde HEAD ({_head_sha()[:12]}), pero "
            f"__version__ = {version!r} no termina en .devN. "
            f"Use un sufijo .dev0/.devN durante el trabajo."
        )
        return

    # Hay etiqueta reachable. ¿HEAD está exactamente en ese commit?
    if _head_is_at_tag(tag):
        # HEAD == tag. __version__ debe ser el SemVer puro de la
        # etiqueta. Esto es una release limpia.
        m = SEMVER_RE.match(version)
        assert m, (
            f"release governance drift: HEAD está en la etiqueta "
            f"{tag!r} pero __version__ = {version!r} no es un "
            f"SemVer puro (X.Y.Z)."
        )
        expected = tag.lstrip("v")
        assert version == expected, (
            f"release governance drift: HEAD en {tag!r}, "
            f"__version__ = {version!r}, esperaba {expected!r}."
        )
        return

    # HEAD está en un commit posterior a la etiqueta reachable.
    # Caso de trabajo: __version__ debe terminar en .devN.
    # La base X.Y.Z puede ser la misma que la etiqueta (PATCH sobre
    # la misma release, p.ej. 0.14.0 -> 0.14.0.dev0 -> 0.14.0), o
    # superior (p.ej. 0.14.1.dev0 después de una etiqueta 0.14.0).
    m = DEV_SUFFIX_RE.match(version)
    assert m, (
        f"release governance drift: HEAD posterior a la etiqueta "
        f"{tag!r} (HEAD = {_head_sha()[:12]}), pero "
        f"__version__ = {version!r} no termina en .devN."
    )
    # Drift real sería: __version__ con .devN pero HEAD == etiqueta
    # (imposible que un commit etiquetado tenga sufijo dev). Eso ya
    # queda cubierto por el caso HEAD-en-etiqueta arriba, que exige
    # SemVer puro. Si llegamos aquí, ya validamos que __version__
    # tiene .devN; cualquier base X.Y.Z es admisible hasta que se
    # cree la siguiente etiqueta.


def test_current_version_is_documented_in_state() -> None:
    """CURRENT.md y STATE.yaml deben reflejar la versión activa.

    Si la versión cambia sin actualizar la documentación, este test
    falla con un mensaje que apunta al documento que falta.

    **R0.B: ESTE GUARD LEÍA EL CAMPO POR TEXTO, Y NO FUNCIONABA.**

    Era `f'package_version: "{version}"' in state_yaml`, y hay **DOS**
    campos con ese nombre en `STATE.yaml`:

        tests.package_version     (viejo desde B29: 0.39.0.dev0)
        release.package_version   (el que declara la version activa)

    Una coincidencia de texto encuentra la línea que sea, en cualquier
    sección. Con la cabecera mal y `releases[0]` bien, pasaba en verde —
    y MEDIDO: `project_truth` tampoco lo cruzaba, así que nadie se enteraba
    de la clase de fallo que este guard dice cubrir.

    **AHORA LEE EL CAMPO POR SU CAMINO** (`yaml.safe_load` → `release` →
    `package_version`). No es una mejora de estilo: un predicado que busca
    texto no puede decir *dónde* estaba el valor, y aquí hay dos sitios.
    """
    import yaml

    version = skillgraph.__version__
    state = yaml.safe_load((REPO_ROOT / "STATE.yaml").read_text(encoding="utf-8"))
    current_md = (REPO_ROOT / "CURRENT.md").read_text(encoding="utf-8")

    # STATE.yaml: por su seccion, no por coincidencia de texto.
    declarada = state.get("release", {}).get("package_version")
    assert declarada == version, (
        f"STATE.yaml release.package_version dice {declarada!r} y la version "
        f"activa del paquete es {version!r}. Actualice STATE.yaml al bump de "
        "version. (Nota: `tests.package_version` es un campo DISTINTO y viejo; "
        "no confundirlos es justo lo que este guard no podia hacer antes.)"
    )
    # CURRENT.md debe contener la versión declarada en algún sitio.
    assert version in current_md, (
        f"CURRENT.md no contiene la versión {version!r}. Actualice CURRENT.md al bump de versión."
    )
