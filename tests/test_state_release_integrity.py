"""WI-74: `STATE.yaml` no puede volver a mentir sobre las releases.

`STATE.yaml` es el punto de recuperacion durable del proyecto: su
encabezado dice "apunta a la verdad observable". Medido el 2026-10-02, su
seccion de releases contenia cuatro SHA que NO EXISTEN en el repo, dos
que apuntan al commit equivocado, tres entradas con prosa en el campo
`sha`, dos releases sin registrar y un `release.tag` dos versiones
atras. Y no habia ninguna red que lo detectara: la auditoria de deuda
arquitectonica si la tiene (`test_audit_debt_accuracy.py`), el estado no.

Estos tests atan el estado a `git tag` con **igualdad exacta**, sin
margenes ni tolerancias, que es lo unico que sirve: si manana se publica
una release y no se registra aqui, falla solo.

El test `test_unresolvable_old_shas_are_recorded_as_such` es el que
impide "limpiar" el pasado en silencio. Cuatro entradas tienen un
valor que ya no resuelve porque el historial se movio; borrar esa
constancia dejaria el documento igual de limpio y de falso.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "STATE.yaml"
SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
HEX_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _git(*args: str) -> str:
    result = subprocess.run(
        ("git", *args),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _state() -> dict[str, Any]:
    return yaml.safe_load(STATE_PATH.read_text(encoding="utf-8"))


def _git_tags() -> list[str]:
    """Etiquetas SemVer de git, ordenadas por version (no alfabeticamente)."""
    tags = [t for t in _git("tag").splitlines() if SEMVER_RE.match(t)]
    return sorted(tags, key=lambda t: tuple(int(p) for p in SEMVER_RE.match(t).group(1, 2, 3)))


def _git_sha(tag: str) -> str:
    return _git("rev-list", "-n", "1", tag)


def _entries() -> list[dict[str, Any]]:
    releases = _state().get("release", {}).get("releases") or []
    return [e for e in releases if isinstance(e, dict)]


def _listed_tags() -> list[str]:
    return [str(e.get("tag", "")) for e in _entries() if e.get("tag")]


def _entry_for(tag: str) -> dict[str, Any]:
    for entry in _entries():
        if str(entry.get("tag", "")) == tag:
            return entry
    raise AssertionError(f"{tag} no esta listado en STATE.yaml")


# ---------------------------------------------------------------------------
# REQ-4: exhaustividad y exactitud del inventario
# ---------------------------------------------------------------------------


def test_release_tag_is_the_latest_semver_tag() -> None:
    """`release.tag` es la etiqueta mas reciente, no una de hace dos versiones."""
    declared = _state().get("release", {}).get("tag")
    latest = _git_tags()[-1]

    assert declared == latest, (
        f"STATE.yaml release.tag dice {declared!r} pero la ultima etiqueta en git "
        f"es {latest!r}. Un punto de recuperacion que no sabe donde estamos no "
        "es un punto de recuperacion"
    )


def test_every_semver_tag_is_listed_exactly_once() -> None:
    """REQ-4: ni una etiqueta de git falta, ni se lista dos veces."""
    git_tags = _git_tags()
    listed = _listed_tags()

    missing = [t for t in git_tags if t not in listed]
    duplicates = sorted({t for t in listed if listed.count(t) > 1})

    assert not missing, f"etiquetas de git sin registrar en STATE.yaml: {missing}"
    assert not duplicates, f"etiquetas listadas mas de una vez: {duplicates}"


def test_no_invented_tags() -> None:
    """REQ-4: STATE.yaml no lista releases que git no tiene."""
    git_tags = set(_git_tags())

    invented = sorted(t for t in _listed_tags() if t not in git_tags)

    assert not invented, (
        f"STATE.yaml lista releases que no existen en git: {invented}. O el "
        "documento miente, o hay una etiqueta local que no se publico"
    )


# ---------------------------------------------------------------------------
# REQ-1: los SHA tienen que existir y ser los correctos
# ---------------------------------------------------------------------------


def test_every_listed_sha_resolves_to_a_real_commit() -> None:
    """REQ-1: el hallazgo grave. Un SHA que no resuelve no es informacion.

    Cuatro entradas (v0.14.1..v0.14.4) declaraban SHA que no existen en
    el repo: `git cat-file -e` falla. Restaurar desde ahi lleva a commits
    inexistentes.
    """
    unresolvable: list[str] = []
    for entry in _entries():
        tag = str(entry.get("tag", ""))
        sha = str(entry.get("sha", ""))
        if not sha:
            continue
        if not HEX_SHA_RE.match(sha):
            continue  # REQ-3 lo cubre aparte
        proc = subprocess.run(
            ("git", "cat-file", "-e", f"{sha}^{{commit}}"),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            unresolvable.append(f"{tag}={sha}")

    assert not unresolvable, (
        "STATE.yaml declara SHA que no existen en el repo: "
        f"{unresolvable}. Se sustituyen por el real, pero la constancia de que "
        "el anterior no resolvia debe permanecer (ver "
        "test_unresolvable_old_shas_are_recorded_as_such)"
    )


def test_every_listed_sha_matches_its_tag() -> None:
    """REQ-1: el SHA es el del tag, no el del commit de documentacion.

    Dos entradas apuntaban al commit que documentaba el release
    (p. ej. "docs(release): v0.14.8 release-receipt") en vez de al
    commit etiquetado. El campo no decia lo que su nombre prometia.
    """
    divergent: list[str] = []
    for entry in _entries():
        tag = str(entry.get("tag", ""))
        sha = str(entry.get("sha", ""))
        if not tag or not HEX_SHA_RE.match(sha):
            continue
        real = _git_sha(tag)
        if not real.startswith(sha) and not sha.startswith(real[: len(sha)]):
            divergent.append(f"{tag}: dice {sha[:12]}, git dice {real[:12]}")

    assert not divergent, f"SHA que no coinciden con su etiqueta: {divergent}"


# ---------------------------------------------------------------------------
# REQ-3: el campo `sha` no es un sitio para prosa
# ---------------------------------------------------------------------------


def test_sha_field_never_holds_prose() -> None:
    """REQ-3: `sha` contiene un SHA o nada, nunca una descripcion.

    Tres entradas usaban el campo para texto ("WI-11 release bundle").
    Eso hace que cualquier validacion automatica que lo compare con git
    falle de forma incomprensible en vez de detectar un dato erroneo.
    """
    prosa: list[str] = []
    for entry in _entries():
        tag = str(entry.get("tag", ""))
        sha = str(entry.get("sha", ""))
        if sha and not HEX_SHA_RE.match(sha):
            prosa.append(f"{tag}: {sha!r}")

    assert not prosa, (
        f"el campo `sha` contiene prosa en {len(prosa)} entrada(s): {prosa}. "
        "La descripcion va en su propio campo"
    )


# ---------------------------------------------------------------------------
# REQ-2: el pasado no se pierde ni se disimula
# ---------------------------------------------------------------------------


def test_unresolvable_old_shas_are_recorded_as_such() -> None:
    """REQ-2: donde el valor antiguo no resolvia, consta que no resolvia.

    Este test impide la forma mas silenciosa de "arreglar" el estado:
    sustituir los SHA rotos por los correctos y borrar el rastro. El
    documento quedaria mas limpio y tambien mas falso, porque perderia
    la informacion de que el historial se movio bajo esos releases.
    """
    recorded = {str(e.get("tag", "")): e for e in _entries() if e.get("superseded_sha")}

    # Los cuatro que no resolvian, medidos el 2026-10-02.
    expected = {"v0.14.1", "v0.14.2", "v0.14.3", "v0.14.4"}

    missing = sorted(expected - set(recorded))
    assert not missing, (
        f"estas entradas declaraban un SHA que no resolvia y no lo dejan "
        f"constar en `superseded_sha`: {missing}. Si el valor se sustituyo, "
        "el motivo tiene que quedar escrito"
    )

    for tag in sorted(expected):
        note = str(recorded[tag]["superseded_sha"])
        assert recorded[tag].get("sha") != note, (
            f"{tag}: `sha` y `superseded_sha` son el mismo valor; el anterior "
            "debe quedar aparte, no ocupar el campo principal"
        )


# ---------------------------------------------------------------------------
# El documento sigue siendo legible y parseable
# ---------------------------------------------------------------------------


def test_state_yaml_stays_parseable_and_documents_itself() -> None:
    """La red no puede pasar porque STATE.yaml dejo de cargarse."""
    state = _state()
    assert isinstance(state, dict)
    assert "release" in state, "STATE.yaml perdio la seccion release"
    assert _entries(), "release.releases quedo vacio"
