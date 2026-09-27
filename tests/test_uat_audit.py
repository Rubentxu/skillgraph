"""Tests pytest para los UATs que viven solo en tests/uat_audit.py.

Cierra el gap honesto documentado en specs/uat-coverage-gap.md:
estos UATs ya tienen implementacion verificada (status=PASS al
ejecutar uat_audit.py), pero NO corren automaticamente en CI
porque uat_audit.py es un script y scripts/ci.sh solo ejecuta
pytest.

Este modulo NO reimplementa la logica de los UATs: simplemente
invoca las funciones uat_NN() de tests/uat_audit.py y aserta
el campo status del Evidence devuelto.

Patron reutilizado: el helper _run_cli de tests/uat_audit.py se
usa tal cual (sin modificar), garantizando que pytest ejecuta
exactamente el mismo codigo que el script de audit manual.

Cobertura que AÑADE este modulo:
- UAT-05: handoff con ContextRecipe.
- UAT-10: invalidacion de conocimiento (H3 slice 4).
- UAT-11: asimilacion de skill (H5).
- UAT-15: fuente maliciosa (Adapter outcome JSON gobierna).
- UAT-16: estado historico (handoff_json persiste).

UATs ya cubiertos en pytest (NO duplicar):
- UAT-01..04, 06..07 en test_cli_uat.py y test_cli_run_uat.py.
- UAT-08, UAT-09 en test_h4_expansion_cli.py.
- UAT-14 en test_skill_importer.py (test_script_never_executes_during_import).

UATs esperados BLOCKED (cubiertos en test_uat_blocked.py):
- UAT-12 (H6 multipropósito), UAT-13 (H7 promoción).

Cada test aqui es un wrapper trivial; el valor NO es logica nueva
sino CI-coverage: si alguien modifica src/skillgraph/*.py sin
actualizar uat_audit.py, estos tests fallan en CI, no esperan
ejecucion manual.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# tests/ no es un paquete Python; importamos el script via sys.path.
_TESTS_DIR = Path(__file__).parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import uat_audit  # type: ignore[import-not-found]  # noqa: E402

# Mapping (uat_id, uat_fn, expected_status).
# expected_status="PASS" para los 5 gaps reales.
_GAP_UATS: list[tuple[str, str, str]] = [
    ("UAT-05", "uat_05", "PASS"),
    ("UAT-10", "uat_10", "PASS"),
    ("UAT-11", "uat_11", "PASS"),
    ("UAT-15", "uat_15", "PASS"),
    ("UAT-16", "uat_16", "PASS"),
]


@pytest.mark.parametrize("uat_id,fn_name,expected", _GAP_UATS)
def test_uat_wrapper_runs_and_passes(uat_id: str, fn_name: str, expected: str) -> None:
    """Wrapper pytest para un UAT que solo vive en uat_audit.py.

    Invoca la funcion uat_NN() y aserta su Evidence.status. NO
    reimplementa la logica. Si uat_audit.py cambia y un UAT deja
    de pasar, este test falla en CI automaticamente.
    """
    fn = getattr(uat_audit, fn_name)
    evidence = fn()
    assert evidence.uat_id == uat_id, (
        f"{fn_name}() retorno uat_id={evidence.uat_id!r}, esperado {uat_id!r}"
    )
    assert evidence.status == expected, (
        f"{uat_id} status={evidence.status!r}, esperado {expected!r}.\n"
        f"observed: {evidence.observed}\nnotes: {evidence.notes}"
    )


# ---------------------------------------------------------------------------
# Tests del CLI de uat_audit (proteccion contra escritura destructiva)
# ---------------------------------------------------------------------------


def test_main_default_is_readonly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin args, main() debe leer evidencia y NO escribir nada nuevo."""
    import uat_audit

    # Redirigir EVIDENCE_DIR a un tmp para verificar que NO crea archivos.
    fake_evidence = tmp_path / "evidence"
    fake_evidence.mkdir()
    # Copiar un file valido preexistente para que el read-only lo reporte.
    (fake_evidence / "UAT-05.json").write_text(
        '{"uat_id": "UAT-05", "status": "PASS", "revision": "abc1234"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main([])

    # Exit 0 y NO se escribio nada nuevo en el tmp.
    assert rc == 0
    created = [p.name for p in fake_evidence.iterdir() if p.name != "UAT-05.json"]
    assert created == [], f"main() creo archivos en modo lectura: {created}"


def test_main_write_unknown_uat_returns_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--write sobre un UAT desconocido retorna rc=2."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    fake_evidence.mkdir()
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main(["--write", "UAT-99"])

    assert rc == 2


def test_main_write_stub_without_yes_returns_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--write sobre un UAT stub (UAT-08/09/12/13) SIN --yes retorna rc=3 y NO escribe."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    fake_evidence.mkdir()
    # Pre-poblar con evidencia PASS que NO debe ser pisada.
    (fake_evidence / "UAT-08.json").write_text(
        '{"uat_id": "UAT-08", "status": "PASS", "revision": "must-survive"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main(["--write", "UAT-08"])

    assert rc == 3
    # Evidencia preexistente intacta.
    survived = json.loads((fake_evidence / "UAT-08.json").read_text(encoding="utf-8"))
    assert survived["revision"] == "must-survive", (
        f"--write UAT-08 sin --yes piso la evidencia: {survived}"
    )


def test_main_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run ejecuta los UATs pero NO escribe evidencia."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    fake_evidence.mkdir()
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main(["--dry-run", "UAT-05"])

    assert rc == 0
    # No se creo UAT-05.json (UAT-05 no es stub; --dry-run nunca escribe).
    assert not (fake_evidence / "UAT-05.json").exists()


def test_main_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """--help imprime uso y sale con rc=0 (argparse usa SystemExit)."""
    import uat_audit

    with pytest.raises(SystemExit) as exc_info:
        uat_audit.main(["--help"])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "Auditoria UAT de SkillGraph" in out
    assert "--write" in out


# ---------------------------------------------------------------------------
# QW-H: UAT-08/09 deben usar la evidencia E2E, no un stub BLOCKED.
# ---------------------------------------------------------------------------


class TestUat08Uat09DelegatesToE2E:
    """Comportamiento nuevo (QW-H):

    - Si el test E2E ``test_h4_expansion_cli.py`` escribio evidencia
      PASS, ``uat_08/09()`` la devuelve tal cual.
    - Si no, devuelve BLOCKED con referencia al test que la debe generar.
    """

    def test_uat_08_returns_existing_pass_evidence_when_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Si UAT-08.json existe con status PASS, uat_08 lo devuelve."""
        import uat_audit as _ua  # noqa: E402

        fake_dir = tmp_path / "tests" / "uat-evidence"
        fake_dir.mkdir(parents=True)
        fake_dir.joinpath("UAT-08.json").write_text(
            _ua.json.dumps(
                {
                    "uat_id": "UAT-08",
                    "revision": "deadbeef" * 5,
                    "timestamp": "2026-09-23T11:00:00Z",
                    "scenario": "scenario X",
                    "expected": "expected X",
                    "observed": "observed X",
                    "steps": [],
                    "artifacts": [],
                    "status": "PASS",
                    "notes": "fake evidencia",
                }
            ),
            encoding="utf-8",
        )

        # uat_08 -> uats_blocked_gap -> _git_rev (subprocess git rev-parse).
        monkeypatch.setattr(_ua, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(_ua, "_git_rev", lambda: "deadbeef" * 5)
        monkeypatch.setattr(_ua, "_now", lambda: "2026-09-27T08:00:00Z")

        ev = _ua.uat_08()
        assert ev.observed == "observed X"
        assert ev.uat_id == "UAT-08"

    def test_uat_09_returns_existing_pass_evidence_when_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import uat_audit as _ua  # noqa: E402

        fake_dir = tmp_path / "tests" / "uat-evidence"
        fake_dir.mkdir(parents=True)
        fake_dir.joinpath("UAT-09.json").write_text(
            _ua.json.dumps(
                {
                    "uat_id": "UAT-09",
                    "revision": "deadbeef" * 5,
                    "timestamp": "2026-09-23T11:00:00Z",
                    "scenario": "scenario Y",
                    "expected": "expected Y",
                    "observed": "observed Y",
                    "steps": [],
                    "artifacts": [],
                    "status": "PASS",
                    "notes": "fake evidencia",
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(_ua, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(_ua, "_git_rev", lambda: "deadbeef" * 5)
        monkeypatch.setattr(_ua, "_now", lambda: "2026-09-27T08:00:00Z")

        ev = _ua.uat_09()
        assert ev.status == "PASS"
        assert ev.observed == "observed Y"

    def test_uat_08_returns_blocked_when_no_evidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Sin evidencia en disco, devuelve BLOCKED con nota honesta."""
        import uat_audit as _ua  # noqa: E402

        fake_dir = tmp_path / "tests" / "uat-evidence"
        fake_dir.mkdir(parents=True)
        # No UAT-08.json.

        monkeypatch.setattr(_ua, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(_ua, "_git_rev", lambda: "deadbeef" * 5)
        monkeypatch.setattr(_ua, "_now", lambda: "2026-09-27T08:00:00Z")

        ev = _ua.uat_08()
        assert ev.status == "BLOCKED"
        assert "test_h4_expansion_cli.py" in ev.notes

    def test_uat_09_returns_blocked_when_no_evidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import uat_audit as _ua  # noqa: E402

        fake_dir = tmp_path / "tests" / "uat-evidence"
        fake_dir.mkdir(parents=True)

        monkeypatch.setattr(_ua, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(_ua, "_git_rev", lambda: "deadbeef" * 5)
        monkeypatch.setattr(_ua, "_now", lambda: "2026-09-27T08:00:00Z")

        ev = _ua.uat_09()
        assert ev.status == "BLOCKED"
        assert "test_h4_expansion_cli.py" in ev.notes

    def test_uat_08_returns_blocked_when_evidence_is_not_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Si el JSON existe pero NO es PASS (p.ej. cadena vieja), vuelve a BLOCKED."""
        import uat_audit as _ua  # noqa: E402

        fake_dir = tmp_path / "tests" / "uat-evidence"
        fake_dir.mkdir(parents=True)
        fake_dir.joinpath("UAT-08.json").write_text(
            _ua.json.dumps(
                {
                    "uat_id": "UAT-08",
                    "revision": "x",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "scenario": "s",
                    "expected": "e",
                    "observed": "stale (PASS pre-QW-H)",
                    "steps": [],
                    "artifacts": [],
                    "status": "BLOCKED",
                    "notes": "viejo",
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(_ua, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(_ua, "_git_rev", lambda: "deadbeef" * 5)
        monkeypatch.setattr(_ua, "_now", lambda: "2026-09-27T08:00:00Z")

        ev = _ua.uat_08()
        # Como ya es BLOCKED, no la aceptamos: regeneramos notas honestas.
        assert ev.status == "BLOCKED"
        assert "test_h4_expansion_cli.py" in ev.notes
