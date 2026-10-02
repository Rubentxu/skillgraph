"""WI-82 — la suite no debe ensuciar `git status` al re-verificar evidencia UAT.

Defecto medido (2026-10-02, ciclo SDDK `wi-82-evidence-write-idempotence`):
`tests/test_h4_expansion_cli.py` emite `tests/uat-evidence/UAT-08.json` y
`UAT-09.json` en cada ejecucion. Ambos ficheros estan versionados, y el
UNICO campo que cambia entre ejecuciones es `revision`, que se rellena con
`git rev-parse HEAD`. Resultado: `pytest tests/test_h4_expansion_cli.py`
deja el arbol de git sucio, aunque la evidencia sea semanticamente
identica.

Por que `revision` no es una entrada honesta del estado: **ningun test
comprueba que `revision` == HEAD**. Es un sello informativo ("el commit bajo
el que se produjo este contenido"). Peor aun,
`tests/test_uat_audit.py:143` afirma justo lo contrario de lo que hace el
producto: `assert survived["revision"] == "must-survive"` — la evidencia
persistida debe SOBREVIVIR a una re-emision sin cambio semantico.

Y `revision` no puede converger por construccion: un fichero versionado
nunca puede contener el SHA del commit que lo versiona. Quedaria siempre un
commit por detras. Ese desfase no es informacion; es ruido.

Invariante que fija esta red:

    Re-verificar con contenido semanticamente identico NO reescribe el
    fichero. Re-verificar con contenido distinto SI lo reescribe.

La segunda mitad importa tanto como la primera: un helper "idempotente" que
se tragara cambios reales seria peor que el defecto que corrige.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests._evidence_lock import save_with_lock

EVIDENCE_DIR = Path(__file__).parent / "uat-evidence"

# SHA que se usa para simular "la evidencia en disco se produjo bajo otro
# commit". No es un HEAD real: si lo fuera, el test seria una tautologia.
_OTHER_REV = "0" * 40


def _payload(uat_id: str, revision: str, **overrides: object) -> dict[str, object]:
    """Payload con la misma forma que emiten los helpers de UAT-08/09."""
    base: dict[str, object] = {
        "uat_id": uat_id,
        "revision": revision,
        "timestamp": "2026-09-23T11:00:00Z",
        "scenario": "s",
        "expected": "e",
        "observed": "o",
        "steps": [],
        "artifacts": [],
        "status": "PASS",
        "notes": "n",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Nivel unitario: el contrato de `save_with_lock`
# ---------------------------------------------------------------------------


def test_identical_payload_modulo_revision_does_not_rewrite(tmp_path: Path) -> None:
    """Re-emitir el mismo contenido con otro `revision` deja el fichero intacto.

    Este es el defecto exacto: la evidencia en disco dice `revision=X`, la
    nueva ejecucion produce `revision=Y`, y todo lo demas es identico.
    """
    out = save_with_lock(
        tmp_path, "UAT-08", _payload("UAT-08", "a" * 40), volatile_keys=("revision",)
    )
    before = out.read_bytes()

    save_with_lock(tmp_path, "UAT-08", _payload("UAT-08", "b" * 40), volatile_keys=("revision",))

    assert out.read_bytes() == before, (
        "save_with_lock reescribio la evidencia pese a ser identica "
        "salvo `revision` (esto es lo que ensucia `git status`)"
    )
    assert json.loads(out.read_text(encoding="utf-8"))["revision"] == "a" * 40


def test_changed_payload_is_still_written(tmp_path: Path) -> None:
    """Un cambio real de contenido SI se escribe aunque se declare `revision` volátil.

    Guarda contra el helper "idempotente" que se traga la evidencia nueva.
    """
    out = save_with_lock(
        tmp_path, "UAT-08", _payload("UAT-08", "a" * 40), volatile_keys=("revision",)
    )
    save_with_lock(
        tmp_path, "UAT-08", _payload("UAT-08", "b" * 40, status="FAIL"), volatile_keys=("revision",)
    )

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "FAIL"
    assert json.loads(out.read_text(encoding="utf-8"))["revision"] == "b" * 40


def test_no_rewrite_preserves_mtime(tmp_path: Path) -> None:
    """No reescribir significa no reescribir: la mtime no se toca.

    Comparar contenido no distingue "no escribió" de "escribió lo mismo".
    La mtime sí. Sin esto, un helper que reescribiera idéntico pasaría
    el test anterior.
    """
    out = save_with_lock(
        tmp_path, "UAT-08", _payload("UAT-08", "a" * 40), volatile_keys=("revision",)
    )
    mtime_before = out.stat().st_mtime_ns

    save_with_lock(tmp_path, "UAT-08", _payload("UAT-08", "b" * 40), volatile_keys=("revision",))

    assert out.stat().st_mtime_ns == mtime_before, (
        "el fichero se reescribio (mtime cambio) pese a ser identico salvo `revision`"
    )


def test_default_still_rewrites(tmp_path: Path) -> None:
    """Sin `volatile_keys`, el comportamiento es el de siempre: siempre escribe.

    `uat_audit.py::_save_evidence` usa `history_keep=True` y SI quiere que
    cada ejecucion quede registrada. El opt-in no debe alterarlo.
    """
    out = save_with_lock(tmp_path, "UAT-01", _payload("UAT-01", "a" * 40))
    save_with_lock(tmp_path, "UAT-01", _payload("UAT-01", "a" * 40))
    assert json.loads(out.read_text(encoding="utf-8"))["revision"] == "a" * 40

    save_with_lock(tmp_path, "UAT-01", _payload("UAT-01", "b" * 40))
    assert json.loads(out.read_text(encoding="utf-8"))["revision"] == "b" * 40


def test_volatile_keys_absent_from_existing_file(tmp_path: Path) -> None:
    """Fichero previo sin la clave volátil: se compara contra `{}` y se escribe."""
    out = tmp_path / "UAT-08.json"
    out.write_text(json.dumps({"uat_id": "UAT-08"}), encoding="utf-8")

    save_with_lock(tmp_path, "UAT-08", _payload("UAT-08", "b" * 40), volatile_keys=("revision",))

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "PASS"


def test_volatile_keys_absent_from_new_payload(tmp_path: Path) -> None:
    """Payload nuevo sin la clave volátil contra fichero que sí la tiene."""
    out = save_with_lock(tmp_path, "UAT-08", _payload("UAT-08", "a" * 40))

    save_with_lock(
        tmp_path, "UAT-08", {"uat_id": "UAT-08", "status": "PASS"}, volatile_keys=("revision",)
    )

    assert "revision" not in json.loads(out.read_text(encoding="utf-8")), (
        "una clave volátil ausente en el payload no debe introducirse en el fichero"
    )


def test_unreadable_existing_file_does_not_lose_evidence(tmp_path: Path) -> None:
    """Si el fichero previo no se puede leer, se escribe (fail-open, no fail-silent)."""
    out = tmp_path / "UAT-08.json"
    out.write_text("{esto no es json", encoding="utf-8")

    save_with_lock(tmp_path, "UAT-08", _payload("UAT-08", "b" * 40), volatile_keys=("revision",))

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "PASS"


# ---------------------------------------------------------------------------
# Nivel end-to-end: los emisores reales de UAT-08/09
# ---------------------------------------------------------------------------


def _git_status_of_evidence() -> str:
    """`git status --porcelain` limitado a tests/uat-evidence/."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", "tests/uat-evidence/"],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).parent.parent,
    )
    return out.stdout


def _emit_08(tmp_path: Path, apply: subprocess.CompletedProcess[str]) -> None:
    """Invoca el emisor real de UAT-08 con el minimo de fixtures."""
    from tests.test_h4_expansion_cli import _emit_uat_08_evidence

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"nodes": [{"name": "n1"}]}), encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    proposal.write_text("{}", encoding="utf-8")
    _emit_uat_08_evidence(tmp_path, tmp_path, apply, plan_file, proposal)


def _emit_09(tmp_path: Path, apply: subprocess.CompletedProcess[str]) -> None:
    """Invoca el emisor real de UAT-09 con el minimo de fixtures."""
    from tests.test_h4_expansion_cli import _emit_uat_09_evidence

    rejection = tmp_path / "rejection.json"
    rejection.write_text(
        json.dumps(
            {
                "proposal_id": "prop-1",
                "reason": "I3",
                "violated_invariants": ["I3"],
                "policy_violations": [],
            }
        ),
        encoding="utf-8",
    )
    proposal = tmp_path / "proposal.json"
    proposal.write_text("{}", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"nodes": [{"name": "n1"}]}), encoding="utf-8")
    _emit_uat_09_evidence(
        tmp_path,
        tmp_path,
        apply,
        plan_file=plan_file,
        proposal=proposal,
        rejection_files=[rejection],
    )


def _completed(
    rc: int = 0, stdout: str = "ok", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["sg"], returncode=rc, stdout=stdout, stderr=stderr)


def _completed_different() -> subprocess.CompletedProcess[str]:
    """Un resultado genuinamente distinto en los TRES campos que ambos emisores usan.

    UAT-09 usa `apply.returncode`; UAT-08 usa `apply.stderr`. Hay que mover
    los tres (rc, stdout, stderr) para que cualquiera de los dos emisores
    produzca de verdad otro payload. Mover solo el rc dejaba a UAT-08 con
    un payload identico y el test pasaba sin comprobar nada.
    """
    return _completed(rc=7, stdout="stdout-distinto", stderr="stderr-distinto")


@pytest.mark.parametrize("emitter", [_emit_08, _emit_09])
def test_emitter_does_not_dirty_tracked_evidence(
    emitter: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El emisor real, con un HEAD distinto, no puede reescribir el fichero versionado.

    El escenario real es: una ejecucion posterior del suite, sobre un
    checkout mas avanzado, produce el MISMO contenido con otro
    `git rev-parse HEAD`. El fichero debe quedar como estaba.

    Por que el test siembra antes de comparar: el payload real del emisor
    depende de datos que solo existen en la corrida de produccion (los
    nombres de fichero del scratch de pytest, el `nodes_after` real). Con
    fixtures sinteticos el payload difiere de verdad y se escribe — lo
    cual seria el comportamiento CORRECTO. Para poder distinguir "cambio
    real" de "solo cambia el sello", el test deja en disco exactamente el
    payload que el propio emisor produce, con `revision` distinto.
    """
    import tests.test_h4_expansion_cli as h4

    target = EVIDENCE_DIR / ("UAT-08.json" if emitter is _emit_08 else "UAT-09.json")
    original = target.read_bytes()
    try:
        # Fase 1: descobrir el payload que produce este emisor.
        monkeypatch.setattr(h4, "_git_rev_head", lambda: "1" * 40)
        emitter(tmp_path, _completed())  # type: ignore[operator]
        produced = json.loads(target.read_text(encoding="utf-8"))

        # Fase 2: dejar en disco ese mismo payload, pero archivado bajo
        # otro commit — que es como siempre aparece tras un push.
        seeded = dict(produced)
        seeded["revision"] = _OTHER_REV
        target.write_text(json.dumps(seeded, indent=2, ensure_ascii=False), encoding="utf-8")
        seeded_bytes = target.read_bytes()

        # Fase 3: el emisor corre con un HEAD distinto al sembrado.
        monkeypatch.setattr(h4, "_git_rev_head", lambda: "2" * 40)
        emitter(tmp_path, _completed())  # type: ignore[operator]

        assert target.read_bytes() == seeded_bytes, (
            f"{target.name} fue reescrito pese a que solo cambia `revision` "
            f"(sello informativo, no verificado contra HEAD)"
        )
    finally:
        target.write_bytes(original)


@pytest.mark.parametrize("emitter", [_emit_08, _emit_09])
def test_emitter_writes_when_content_actually_changes(
    emitter: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Si el emisor produce contenido genuinamente distinto, escribe.

    Contraparte del test anterior: la idempotencia no puede tragarse una
    re-verificacion que si cambio de veras.
    """
    import tests.test_h4_expansion_cli as h4

    target = EVIDENCE_DIR / ("UAT-08.json" if emitter is _emit_08 else "UAT-09.json")
    original = target.read_bytes()
    try:
        monkeypatch.setattr(h4, "_git_rev_head", lambda: "1" * 40)
        emitter(tmp_path, _completed())  # type: ignore[operator]
        first = target.read_bytes()

        monkeypatch.setattr(h4, "_git_rev_head", lambda: "1" * 40)
        emitter(tmp_path, _completed_different())  # type: ignore[operator]

        assert target.read_bytes() != first, (
            f"{target.name} cambio de verdad (resultado del CLI distinto) "
            f"y NO se escribio: la idempotencia se tragaria evidencia real"
        )
    finally:
        target.write_bytes(original)


def test_suite_run_leaves_tree_clean() -> None:
    """Contrato de bloque: la evidencia versionada no está sucia al entrar.

    Si un test anterior del propio suite la dejo sucia, este falla y lo
    delata en lugar de propagar el ruido al commit siguiente.
    """
    dirty = _git_status_of_evidence().strip()
    assert not dirty, (
        f"tests/uat-evidence/ esta sucio antes de correr; el tree se ensucia "
        f"en cada ejecucion del suite:\n{dirty}"
    )
