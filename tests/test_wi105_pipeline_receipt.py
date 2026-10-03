"""WI-105 — los criterios de éxito que AGENTS.md declara, y nadie comprueba.

Por qué este fichero
--------------------
`AGENTS.md` («CI Local Obligatorio») enumera SEIS criterios que un run
«debe cumplir», y les llama «todos deben cumplirse». La etapa `evidence`
de `.pipeline.kts` es el único sitio de la receta que toca
`.pipelinek/`, y sus tres comandos son:

    ls -la .pipelinek/db.sqlite
    test -d .pipelinek/control/last-run  && echo 'last-run present'
    test -d .pipelinek/control/workspace && echo 'workspace tracking present'

Los tres operandos los crea el motor ANTES de la etapa, así que los tres
pueden imprimir «present» y ninguno puede fallar. MEDIDO contra el journal
real de este repo: 15 runs, 3 de ellos `RunFinished/failure`, y la etapa
dice exactamente lo mismo en los quince.

Es la forma de WI-101 aplicada al registro del propio CI: una etapa que
certifica sin ejecutar la comprobación. Y el alcance es mayor — el único
criterio referenciado en algún sitio es el 1, con un `grep` sobre el
stdout dentro de `scripts/hooks/pre-push`, que no está instalado y cuyo
`grep` ya se comió esa cadena exacta una vez.

El contraejemplo que manda
-------------------------
No es el run rojo: es el run **verde que no ejecutó nada**. AGENTS.md lo
describe con estas palabras —«sin `--rerun`, un run cuyo script no ha
cambiado reutiliza el veredicto previo y termina en `Pipeline finished
with SUCCESS` sin ejecutar un solo step»— y añade que el criterio 1 por sí
solo lo satisfacen runs que no ejecutan nada. El criterio 2 existe
justamente para separar los dos casos, y era el único modo de fallo que
no distinguía de una verificación real.

Los seis tests de acá comprueban una cosa cada uno, y cada uno exige el
CÓDIGO del problema, no solo que la lista no esté vacía. Exigir solo
«hay problemas» es lo que dejó pasar a tres contraejemplos en WI-104:
pasaban por la rama equivocada y nadie lo vio hasta que las mutaciones
sobrevivieron. Un test que dice «algo falla» no dice QUÉ.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_pipeline_receipt as recibo  # noqa: E402

evaluar = recibo.evaluar
formatear = recibo.formatear
informes = recibo.informes
ultimo_terminado = recibo.ultimo_terminado
DB_REAL: Path = REPO_ROOT / ".pipelinek/db.sqlite"
CONTROL_REAL: Path = REPO_ROOT / ".pipelinek/control"

#: Los cuatro paths que AGENTS.md declara obligatorios en el control root.
CONTROL_COMPLETO: tuple[str, ...] = (
    "last-run",
    "retry-control",
    "wait-until-control",
    "workspace",
)

DDL = (
    "CREATE TABLE events ("
    " event_id TEXT NOT NULL, run_id TEXT NOT NULL, sequence INTEGER NOT NULL,"
    " kind TEXT NOT NULL, occurred_at TEXT NOT NULL, payload TEXT NOT NULL)"
)


def _evento(run_id: str, sequence: int, kind: str, **campos: object) -> tuple:
    payload: dict[str, object] = {
        "eventId": f"evt-{run_id[:8]}-{sequence}",
        "runId": run_id,
        "sequence": sequence,
        "kind": kind,
        "occurredAt": f"2026-10-03T00:{sequence:02d}:00Z",
    }
    payload.update(campos)
    return (
        payload["eventId"],
        run_id,
        sequence,
        kind,
        payload["occurredAt"],
        json.dumps([payload]),
    )


def _journal(tmp_path: Path, eventos: tuple) -> Path:
    db = tmp_path / "db.sqlite"
    con = sqlite3.connect(db)
    con.execute(DDL)
    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?)", eventos)
    con.commit()
    con.close()
    return db


def _control_completo(tmp_path: Path, *faltan: str) -> Path:
    root = tmp_path / "control"
    for nombre in CONTROL_COMPLETO:
        if nombre not in faltan:
            (root / nombre).mkdir(parents=True, exist_ok=True)
    return root


def _run_sano(run_id: str = "run-sano-0001") -> tuple:
    """Un run que cumple los seis criterios. Base de los casos negativos."""
    return (
        _evento(run_id, 1, "RunStarted", scriptPath=".pipeline.kts"),
        _evento(run_id, 2, "StageStarted", stageIndex=0, stageName="discover-repo"),
        _evento(run_id, 3, "StepStarted", stageIndex=0, stepIndex=0, stepName="a", stepType="sh"),
        _evento(run_id, 4, "EchoOutputCaptured", stepIndex=0, content="ok"),
        _evento(
            run_id,
            5,
            "EchoOutputCaptured",
            stepIndex=0,
            content="pytest: 2684 passed in 239.16s (0:03:59)",
        ),
        _evento(
            run_id, 6, "StageFinished", stageIndex=0, stageName="discover-repo", outcome="success"
        ),
        _evento(run_id, 7, "RunFinished", outcome="success"),
    )


def _codigos(tmp_path: Path, eventos: tuple, control: Path | None = None) -> set[str]:
    informe = ultimo_terminado(informes(_journal(tmp_path, eventos)))
    assert informe is not None, "el journal no tiene ningun run terminado"
    problemas = evaluar(informe, control or _control_completo(tmp_path))
    return {p.codigo for p in problemas}


class TestUnRunSanoNoProduceProblemas:
    def test_no_produce_ninguno(self, tmp_path: Path) -> None:
        informe = ultimo_terminado(informes(_journal(tmp_path, _run_sano())))
        assert informe is not None
        assert evaluar(informe, _control_completo(tmp_path)) == ()


class TestUnRunVerdeQueNoEjecutoNadaNoVale:
    """EL contraejemplo del bloque: un SUCCESS cacheado."""

    def test_lo_rechaza_por_no_ejecutar_un_solo_step(self, tmp_path: Path) -> None:
        cacheado = (
            _evento("run-cacheado-01", 1, "RunStarted", scriptPath=".pipeline.kts"),
            _evento("run-cacheado-01", 2, "RunFinished", outcome="success"),
        )
        codigos = _codigos(tmp_path, cacheado)
        assert "sg_pipeline_run_cacheado" in codigos, codigos

    def test_el_verde_sin_pasos_y_el_verde_sin_resumen_se_distinguen(self, tmp_path: Path) -> None:
        """El criterio 2 tiene DOS mitades y cada una tiene su código.

        Con `StepStarted` pero sin el resumen de pytest, el run no es un
        veredicto cacheado: ejecutó pasos, pero no los que miden la
        suite. Si un solo código tapara las dos, el mensaje le diría a
        quien lo lee que el run no corrió, que sería mentira.
        """
        sin_resumen = (
            _evento("run-sinres-01", 1, "RunStarted", scriptPath=".pipeline.kts"),
            _evento("run-sinres-01", 2, "StepStarted", stageIndex=0, stepIndex=0, stepName="a"),
            _evento(
                "run-sinres-01", 3, "StageFinished", stageIndex=0, stageName="a", outcome="success"
            ),
            _evento("run-sinres-01", 4, "RunFinished", outcome="success"),
        )
        codigos = _codigos(tmp_path, sin_resumen)
        assert "sg_pipeline_sin_resumen_pytest" in codigos, codigos
        assert "sg_pipeline_run_cacheado" not in codigos, codigos


class TestUnRunRojoFalla:
    def test_una_ejecucion_fallida_falla(self, tmp_path: Path) -> None:
        eventos = (*_run_sano()[:-1], _evento("run-sano-0001", 7, "RunFinished", outcome="failure"))
        assert "sg_pipeline_run_failure" in _codigos(tmp_path, eventos)

    def test_un_step_failed_falla_aunque_el_run_diga_success(self, tmp_path: Path) -> None:
        """El caso que midio WI-102: `StepFailed` con `RunFinished/success`.

        El exit code del motor y el veredicto del journal son dos cosas
        distintas, y el journal es el que dice la verdad.
        """
        eventos = (
            *_run_sano(),
            _evento(
                "run-sano-0001", 8, "StepFailed", stepIndex=0, message="shell exited with code 1"
            ),
        )
        codigos = _codigos(tmp_path, eventos)
        assert "sg_pipeline_step_failed" in codigos, codigos


class TestElControlRootIncompletoFalla:
    @pytest.mark.parametrize("falta", CONTROL_COMPLETO)
    def test_falta_uno_de_los_cuatro(self, tmp_path: Path, falta: str) -> None:
        informe = ultimo_terminado(informes(_journal(tmp_path, _run_sano())))
        assert informe is not None
        problemas = evaluar(informe, _control_completo(tmp_path, falta))
        assert "sg_pipeline_control_root_incompleto" in {p.codigo for p in problemas}

    def test_nombra_cual_falta(self, tmp_path: Path) -> None:
        """Un guard que dice «incompleto» sin decir QUÉ obliga a mirar a mano."""
        informe = ultimo_terminado(informes(_journal(tmp_path, _run_sano())))
        assert informe is not None
        problemas = evaluar(informe, _control_completo(tmp_path, "retry-control"))
        joined = " ".join(p.mensaje for p in problemas)
        assert "retry-control" in joined, joined


class TestElJournalRealDelRepo:
    """Comprobación de extremo a extremo, sobre el journal de verdad.

    Con una entrada sintetica el guard podría estar midiendo otra cosa.
    """

    def test_el_ultimo_run_real_cumple_los_criterios(self) -> None:
        if not DB_REAL.exists():
            pytest.skip("sin journal: clon nuevo, no hay run que verificar")
        informe = ultimo_terminado(informes(DB_REAL))
        assert informe is not None, "el journal real no tiene ningun run terminado"
        assert evaluar(informe, CONTROL_REAL) == (), (
            "el ultimo run real del repo incumple los criterios que AGENTS.md declara obligatorios"
        )

    def test_el_ultimo_run_real_no_es_una_mediacion_vacia(self) -> None:
        """Un guard que no puede ver nada tampoco puede fallar.

        Si el ultimo run real no tuviera pasos, el test anterior pasaria
        por la rama de «no hay nada que comprobar» y no mediria nada.
        Este test exige que el run real que se verifica se ejecuto de
        verdad, para que el anterior tenga sobre que pronunciarse.
        """
        if not DB_REAL.exists():
            pytest.skip("sin journal: clon nuevo")
        informe = ultimo_terminado(informes(DB_REAL))
        assert informe is not None
        assert informe.steps_iniciados > 0
        assert informe.resumen_pytest is not None

    def test_el_journal_real_registra_runs_que_este_guard_rechazaria(self, tmp_path: Path) -> None:
        """La prueba de que el guard muerde sobre historia REAL.

        El journal del repo contiene runs que, con veredicto 'success', no
        cumplen criterio alguno. Si ninguno existiera, el guard solo
        estaría probado contra dummies.
        """
        if not DB_REAL.exists():
            pytest.skip("sin journal: clon nuevo")
        # Control root vacio a proposito: deja que la unica causa de
        # problema sea el run, para que este test pronunciese sobre el
        # journal y no sobre el arbol.
        control = tmp_path / "control-vacio"
        control.mkdir()
        malos = [inf for inf in informes(DB_REAL) if evaluar(inf, control)]
        assert malos, (
            "ningun run del journal real incumple los criterios: el guard "
            "esta probado solo contra entradas inventadas"
        )


class TestElFormateoDiceQueHaPasado:
    def test_un_run_sano_formatea_como_verde(self, tmp_path: Path) -> None:
        informe = ultimo_terminado(informes(_journal(tmp_path, _run_sano())))
        assert informe is not None
        salida = formatear((), informe)
        assert salida.startswith("OK")

    def test_un_run_rojo_formatea_con_el_codigo(self, tmp_path: Path) -> None:
        eventos = (*_run_sano()[:-1], _evento("run-sano-0001", 7, "RunFinished", outcome="failure"))
        informe = ultimo_terminado(informes(_journal(tmp_path, eventos)))
        assert informe is not None
        problemas = evaluar(informe, _control_completo(tmp_path))
        salida = formatear(problemas, informe)
        assert "sg_pipeline_run_failure" in salida
        assert "FALLO" in salida
