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
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# tests/ no es un paquete Python; importamos el script via sys.path.
_TESTS_DIR = Path(__file__).parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import uat_audit  # type: ignore[import-not-found]  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Mapping

_REPO = Path(__file__).resolve().parent.parent
_UAT_IDS: tuple[str, ...] = tuple(uid for uid, _ in uat_audit._UAT_FUNCTIONS)

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
    # Evidencia COMPLETA y en PASS para todas las UATs.
    #
    # Antes esta fixture ponia solo UAT-05.json y afirmaba rc == 0 con las
    # otras 15 en MISSING. Ese rc == 0 era el bug que WI-101 corrige: la
    # asercion codificaba el comportamiento erroneo como si fuera el
    # correcto. La fixture ahora es una auditoria bien formada, asi que la
    # asercion sigue significando lo que decia.
    _volcar_evidencia(fake_evidence, {uid: "PASS" for uid in _UAT_IDS})
    antes = _huella(fake_evidence)
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main([])

    # Exit 0 y NO se escribio nada nuevo en el tmp.
    assert rc == 0
    assert _huella(fake_evidence) == antes, "el modo lectura modifico la evidencia en disco"


def test_main_readonly_falla_si_la_evidencia_dice_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WI-101: evidencia persistida en FAIL debe producir exit code de derrota.

    MEDIDO antes de arreglar: `scripts/audit_bundle.sh` invocaba el modo
    lectura, que hacia `return 0` incondicional. Con UAT-01 inyectada en
    FAIL el bundle imprimia `PASS=15 FAIL=1` y salia con 0, asi que su
    propia guarda (`rc -ne 0`) no podia dispararse nunca y el bundle se
    certificaba a si mismo con un FAIL a la vista.
    """
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    estados = {uid: "PASS" for uid in _UAT_IDS}
    estados["UAT-01"] = "FAIL"
    _volcar_evidencia(fake_evidence, estados)
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main([])

    assert rc != 0, "el modo lectura dio verde con evidencia en FAIL"


def test_main_readonly_falla_si_falta_evidencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin directorio de evidencia el audit no puede certificar nada: rc != 0.

    MEDIDO antes de arreglar: con `tests/uat-evidence/` ausente el modo
    lectura imprimia `PASS=0 FAIL=0 BLOCKED=0` y salia con 0. Un bundle
    sin una sola evidencia era indistinguible de uno con 16 PASS.
    """
    import uat_audit

    fake_evidence = tmp_path / "no_existe"
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main([])

    assert rc != 0, "el modo lectura dio verde sin ninguna evidencia"


def test_main_readonly_falla_si_la_evidencia_es_ilegible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSON corrupto o de otra UAT: el audit no puede dar ese veredicto por bueno."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {uid: "PASS" for uid in _UAT_IDS})
    (fake_evidence / "UAT-03.json").write_text("{esto no es json", encoding="utf-8")
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main([])

    assert rc != 0, "el modo lectura dio verde con evidencia ilegible"


def test_main_readonly_falla_si_el_estado_es_desconocido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un status fuera del dominio (typo, esquema viejo) no es PASS."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    estados = {uid: "PASS" for uid in _UAT_IDS}
    estados["UAT-07"] = "passed"
    _volcar_evidencia(fake_evidence, estados)
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    rc = uat_audit.main([])

    assert rc != 0, "el modo lectura acepto un status fuera de PASS|FAIL|BLOCKED"


def test_resumen_no_se_traga_los_estados_fuera_de_dominio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """El recuento tiene que sumar todas las filas leidas, no solo las conocidas.

    MEDIDO en WI-101: con un `status: "passed"` el resumen imprimia
    `PASS=15 FAIL=0 BLOCKED=0` sobre 16 veredictos leidos. El numero era
    cierto letra a letra y estaba mal: 15+0+0 != 16, y la diferencia no
    aparecia en ninguna parte de la salida.
    """
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    estados = {uid: "PASS" for uid in _UAT_IDS}
    estados["UAT-07"] = "passed"
    _volcar_evidencia(fake_evidence, estados)
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)

    uat_audit.main([])
    salida = capsys.readouterr().out

    assert "FUERA DE DOMINIO=1" in salida, (
        f"el resumen no dio cuenta del veredicto fuera de dominio:\n{salida}"
    )
    assert "UAT-07" in salida


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
# WI-101: helpers de fixture
# ---------------------------------------------------------------------------


def _volcar_evidencia(directorio: Path, estados: Mapping[str, str]) -> None:
    """Escribe un JSON de evidencia por UAT con el estado indicado."""
    directorio.mkdir(parents=True, exist_ok=True)
    for uat_id, estado in estados.items():
        (directorio / f"{uat_id}.json").write_text(
            json.dumps(
                {
                    "uat_id": uat_id,
                    "revision": "a" * 40,
                    "timestamp": "2026-10-02T00:00:00Z",
                    "scenario": "s",
                    "expected": "e",
                    "observed": "o",
                    "steps": [],
                    "artifacts": [],
                    "status": estado,
                    "notes": "fixture de test",
                }
            ),
            encoding="utf-8",
        )


def _huella(directorio: Path) -> dict[str, str]:
    """Mapa nombre -> sha256. Detecta cualquier escritura, incluida una idéntica."""
    import hashlib

    if not directorio.exists():
        return {}
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directorio.iterdir())
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# WI-101: --verify (ejecuta de verdad y confronta con la evidencia persistida)
# ---------------------------------------------------------------------------


def _stub_ejecucion(monkeypatch: pytest.MonkeyPatch, estados: Mapping[str, str]) -> list[str]:
    """Sustituye `_run_one` por una ejecucion controlada. Devuelve el registro."""
    ejecutadas: list[str] = []

    def _fake(uat_id: str, _fn_name: str, *, write: bool) -> tuple[object, None]:
        ejecutadas.append(uat_id)
        ev = uat_audit.Evidence(
            uat_id=uat_id,
            revision="b" * 40,
            timestamp="2026-10-02T00:00:00Z",
            scenario="s",
            expected="e",
            observed="o",
            steps=[],
            artifacts=[],
            status=estados[uat_id],
        )
        return ev, None

    monkeypatch.setattr(uat_audit, "_run_one", _fake)
    return ejecutadas


def test_verify_ejecuta_los_uats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--verify EJECUTA. Es la diferencia con el modo lectura, y hay que medirla."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {"UAT-05": "PASS"})
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    ejecutadas = _stub_ejecucion(monkeypatch, {"UAT-05": "PASS"})

    rc = uat_audit.main(["--verify", "UAT-05"])

    assert ejecutadas == ["UAT-05"], "--verify no ejecuto ninguna UAT"
    assert rc == 0


def test_verify_falla_si_la_ejecucion_contradice_la_evidencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La evidencia dice PASS y la ejecucion dice FAIL: --verify no puede dar verde.

    Este es el hueco de WI-101. La evidencia persistida es un JSON escrito
    en el pasado; nada la contrastaba con el codigo que la produjo, asi
    que podia afirmar PASS para un UAT que hoy falla sin que nadie se
    entere.
    """
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {"UAT-05": "PASS"})
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    _stub_ejecucion(monkeypatch, {"UAT-05": "FAIL"})

    rc = uat_audit.main(["--verify", "UAT-05"])

    assert rc != 0, "--verify dio verde con evidencia PASS contra ejecucion FAIL"


def test_verify_falla_si_la_evidencia_anticipa_un_fallo_que_ya_no_ocurre(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidencia FAIL, ejecucion PASS: solo la divergencia puede ponerlo rojo.

    El caso espejo del anterior, y el que faltaba. Los dos juntos cierran
    la confusion: en el primero el veredicto ya es FAIL, asi que `rc != 0`
    puede venir del veredicto y no de la divergencia. Con la ejecucion en
    PASS el veredicto es 0, y cualquier `rc != 0` viene **solo** de haber
    comparado con la evidencia.

    MEDIDO: este es exactamente el caso del `.pipelinek/wi101_measure.sh`
    sobre el repo real (UAT-01 persistido en FAIL, los 16 UAT ejecutando
    PASS, exit 1) — y no estaba cubierto por ningun test. La mutacion M4
    lo destapo: convertir `_divergencias` en `return ()` dejaba verde el
    test que si existia, porque ese test no podia distinguir las dos
    causas del fallo.
    """
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {"UAT-05": "FAIL"})
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    _stub_ejecucion(monkeypatch, {"UAT-05": "PASS"})

    rc = uat_audit.main(["--verify", "UAT-05"])

    assert rc != 0, (
        "--verify dio verde con la evidencia anticipando un FAIL que ya no ocurre: "
        "el veredicto de la ejecucion es PASS, asi que un rc 0 solo puede venir "
        "de no haber contrastado con la evidencia persistida"
    )


def test_verify_falla_si_la_ejecucion_falla_aunque_concurdan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAIL concordado sigue siendo FAIL: --verify no es un chequeo de coherencia."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {"UAT-05": "FAIL"})
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    _stub_ejecucion(monkeypatch, {"UAT-05": "FAIL"})

    rc = uat_audit.main(["--verify", "UAT-05"])

    assert rc != 0


def test_verify_falla_si_falta_la_evidencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ejecucion PASS pero sin evidencia persistida: no se puede confirmar nada."""
    import uat_audit

    fake_evidence = tmp_path / "no_existe"
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    _stub_ejecucion(monkeypatch, {"UAT-05": "PASS"})

    rc = uat_audit.main(["--verify", "UAT-05"])

    assert rc != 0, "--verify certifico un UAT cuya evidencia no existe"


def test_verify_no_escribe_evidencia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--verify es un modo de certificacion: ejecuta, confronta y NO muta."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {"UAT-05": "PASS"})
    antes = _huella(fake_evidence)
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    _stub_ejecucion(monkeypatch, {"UAT-05": "PASS"})

    rc = uat_audit.main(["--verify", "UAT-05"])

    assert rc == 0
    assert _huella(fake_evidence) == antes, "--verify modifico la evidencia persistida"


def test_verify_acepta_blocked_concordante(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BLOCKED concordante es un veredicto honesto, no una divergencia."""
    import uat_audit

    fake_evidence = tmp_path / "evidence"
    _volcar_evidencia(fake_evidence, {"UAT-12": "BLOCKED"})
    monkeypatch.setattr(uat_audit, "EVIDENCE_DIR", fake_evidence)
    _stub_ejecucion(monkeypatch, {"UAT-12": "BLOCKED"})

    rc = uat_audit.main(["--verify", "UAT-12"])

    assert rc == 0


# ---------------------------------------------------------------------------
# WI-101: el bundle de auditoria tiene que ejecutar, no releer JSON congelado
# ---------------------------------------------------------------------------

#: Flags que hacen que `uat_audit` EJECUTE los UATs. El modo lectura
#: (sin flag) queda fuera a proposito: es el defecto que se corrige.
_FLAGS_QUE_EJECUTAN = frozenset({"--verify", "--write", "--dry-run"})

_INVOCA_UAT: re.Pattern[str] = re.compile(r"tests\.uat_audit")
_FLAG_LARGO: re.Pattern[str] = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")


def _ordenes_uat_del_bundle() -> tuple[str, ...]:
    """Las ordenes lógicas (sin comentarios) que invocan `tests.uat_audit`.

    Se reutiliza `logicas_de` del checker de paridad: el mecanismo que en
    WI-100 saco a los hooks del inventario no se reimplementa aqui. Los
    comentarios se eliminan ANTES de buscar, que es lo que impide que un
    `--verify` comentado cuente como invocacion.
    """
    import sys as _sys

    _raiz = str(_REPO)
    if _raiz not in _sys.path:
        _sys.path.insert(0, _raiz)
    from scripts.check_ci_recipe_parity import logicas_de

    bundle = _REPO / "scripts" / "audit_bundle.sh"
    return tuple(
        orden
        for orden in logicas_de(bundle.read_text(encoding="utf-8"), "#")
        if _INVOCA_UAT.search(orden)
    )


def test_bundle_de_auditoria_ejecuta_los_uats() -> None:
    """El paso UAT del bundle debe ejecutar; releer evidencia no certifica.

    MEDIDO antes de arreglar: `scripts/audit_bundle.sh` invocaba
    `uv run python -m tests.uat_audit` sin flags, o sea el modo lectura.
    El `PASS=16` del bundle de WI-99 se habia obtenido sin ejecutar un
    solo UAT.
    """
    ordenes = _ordenes_uat_del_bundle()
    assert ordenes, "scripts/audit_bundle.sh ya no invoca tests.uat_audit (borrado el paso?)"

    for orden in ordenes:
        flags = set(_FLAG_LARGO.findall(orden))
        ejecutores = flags & _FLAGS_QUE_EJECUTAN
        assert ejecutores, (
            f"el bundle invoca uat_audit en modo lectura, que no ejecuta nada: {orden!r}"
        )


def test_bundle_usa_flags_que_existen_de_verdad() -> None:
    """Cada flag que el bundle pasa a uat_audit tiene que ser un flag real.

    Cierra la cadena: si el bundle citara un flag inexistente, argparse
    abortaria con codigo 2, que el bundle SIHonra como fallo — pero por
    unavia distinta a la que cree. Este test ata la referencia del script
    al parser real.
    """
    known = {
        action.option_strings[0]
        for action in uat_audit._build_parser()._actions
        for _ in (action.option_strings or ())
    }
    for orden in _ordenes_uat_del_bundle():
        for flag in set(_FLAG_LARGO.findall(orden)):
            if flag in {"--db", "--control-root", "--root", "--scope", "--name"}:
                continue  # flags de otras herramientas que comparten la linea
            assert flag in known, f"el bundle pasa {flag}, que uat_audit no declara: {orden!r}"


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
        import uat_audit as _ua

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
        import uat_audit as _ua

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
        import uat_audit as _ua

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
        import uat_audit as _ua

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
        import uat_audit as _ua

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
