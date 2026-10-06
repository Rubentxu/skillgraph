"""B24 — la etapa `evidence` era un trinquete que no se podia deshacer.

**MEDIDO AL ABRIR ESTE BLOQUE, en este repo, con el journal real:**

    15:56:33  5229e03b  unit-tests  3473 passed, 0 failed, 96 % de cobertura
    16:07:02  5229e03b  las ocho etapas de codigo en success
    16:07:07  5229e03b  RunFinished/failure  — y lo unico que fallo fue la
              etapa `evidence`, mirando el run ANTERIOR (a5cf5a1a), que habia
              fallado de verdad por tres reds de estado.

El razonamiento de WI-110 era correcto y aun asi dejaba un agujero: la
exculparion perdona el `StepFailed` de `evidence/sh-0`, y **nunca** el
veredicto del run. Con la etapa mirando el run ANTERIOR, la cadena es:

    run N falla de verdad      -> run N+1 se juzga con N y falla
    run N+1 fallo en evidence  -> run N+2 se juzga con N+1, cuyo VEREDICTO es
                                  failure, y ese veredicto no se exculpa
    run N+2 falla              -> y asi hasta el infinito

No es un fallo de medicion: es un **trinquete**. Un solo rojo de verdad deja el
proyecto sin poder publicar otra vez, y la unica salida que ofrece el hook es
`--no-verify`, que es exactamente lo que este bloque no va a usar.

**LO QUE SE ARREGLA.** La etapa verifica el run **EN CURSO** —el suyo—, con
los criterios que ya existen mientras corre: sus `StepStarted`, sus
`EchoOutputCaptured` y sus `StepFailed`. El veredicto final no se verifica
porque todavia no se ha emitido, y no se finge que si: esa certificacion
puntual se sigue haciendo con `--run-id`.

La exculparion de WI-110 **no se extiende**: durante un run en curso no hay
run siguiente todavia, asi que un `StepFailed` propio es un fallo real.

Los informes son SINTETICOS porque `evaluar()` es pura sobre `InformeRun`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from check_pipeline_receipt import (  # noqa: E402
    CONTROL_ROOT,
    InformeRun,
    en_curso,
    evaluar,
    informes,
    main,
    ultimo_terminado,
)

CONTROL = RAIZ / ".pipelinek" / "control"

#: La linea que el criterio 2 busca en un `EchoOutputCaptured`.
_RESUMEN = "pytest: 3473 passed, 3 skipped in 624.86s (0:10:24)"


def informe(
    *,
    run_id: str = "sintetico-0001",
    outcome: str | None = "success",
    step_failed: int = 0,
    paso_fallido: str | None = None,
    steps: int = 11,
    etapas_ok: int = 9,
    etapas_total: int = 9,
    resumen: str | None = "3473 passed, 3 skipped in 624.86s (0:10:24)",
) -> InformeRun:
    kwargs: dict[str, object] = {
        "run_id": run_id,
        "steps_iniciados": steps,
        "pasos_capturados": steps,
        "etapas_ok": etapas_ok,
        "etapas_total": etapas_total,
        "step_failed": step_failed,
        "outcome": outcome,
        "resumen_pytest": resumen,
    }
    if "paso_fallido" in InformeRun.__dataclass_fields__:
        kwargs["paso_fallido"] = paso_fallido
    return InformeRun(**kwargs)  # type: ignore[arg-type]


def codigos(info: InformeRun, *, curso: bool = False) -> tuple[str, ...]:
    return tuple(p.codigo for p in evaluar(info, CONTROL, en_curso=curso))


# ---------------------------------------------------------------------------
# 1. El caso que hoy bloquea la publicacion
# ---------------------------------------------------------------------------


class TestElRunAnteriorFallidoNoCondenaAlSiguiente:
    def test_el_contrarregresivo_del_trinquete(self) -> None:
        """El caso EXACTO que dejo al proyecto sin poder publicar.

        Run anterior que fallo de verdad, run en curso sano. Antes de este
        arreglo, la etapa elegia el anterior y caia; ahora mide el suyo.
        """
        anterior = informe(
            run_id="a5cf5a1a-roto",
            outcome="failure",
            step_failed=1,
            paso_fallido="unit-tests/sh-0",
            steps=4,
            etapas_ok=2,
            etapas_total=9,
            resumen=None,
        )
        actual = informe(run_id="5229e03b-en-curso", outcome=None)

        elegido = en_curso((anterior, actual))

        assert elegido is not None and elegido.run_id == "5229e03b-en-curso", (
            "la etapa debe medir el run EN CURSO, no el anterior: si elige el "
            "anterior, un fallo de verdad condena a todos los runs siguientes "
            "para siempre"
        )
        assert codigos(elegido, curso=True) == (), (
            "el run en curso es sano y no debe tener problemas"
        )

    def test_sin_run_en_curso_sigue_usando_el_ultimo_terminado(self) -> None:
        """La certificacion puntual sobre el journal no se pierde."""
        anterior = informe(
            run_id="a5cf5a1a-roto",
            outcome="failure",
            step_failed=1,
            paso_fallido="unit-tests/sh-0",
            steps=4,
            etapas_ok=2,
            etapas_total=9,
            resumen=None,
        )
        bueno = informe(run_id="5229e03b-bueno", outcome="success")

        assert en_curso((anterior, bueno)) is None
        elegido = ultimo_terminado((anterior, bueno))
        assert elegido is not None and elegido.run_id == "5229e03b-bueno"


# ---------------------------------------------------------------------------
# 2. Medir el run en curso no puede volverse permisivo
# ---------------------------------------------------------------------------


class TestElRunEnCursoNoEsUnaExcusa:
    def test_un_step_failed_propio_sigue_fallando(self) -> None:
        """El arreglo no compra permiso: baja un criterio, no todos."""
        info = informe(outcome=None, step_failed=1, paso_fallido="lint/sh-0")
        assert "sg_pipeline_step_failed" in codigos(info, curso=True)

    def test_la_exculparion_no_alcanza_al_run_en_curso(self) -> None:
        """WI-110 perdona el fallo de la etapa autoevaluada EN EL RUN ANTERIOR.

        En el propio no hay run siguiente todavia que envenenar, asi que un
        fallo de `evidence/sh-0` propio es un fallo real. Sin esto, el arreglo
        seria perdonar de mas.
        """
        info = informe(outcome=None, step_failed=1, paso_fallido="evidence/sh-0")
        assert "sg_pipeline_step_failed" in codigos(info, curso=True), (
            "la exculparion de WI-110 es para el run ANTERIOR; extenderla al "
            "propio perdonaria el fallo de la etapa que se verifica a si misma"
        )

    def test_sin_resumen_de_pytest_todavia_no_pasa(self) -> None:
        """El criterio 2 se puede medir en vivo: el resumen ya esta capturado."""
        info = informe(outcome=None, resumen=None, steps=11)
        assert "sg_pipeline_sin_resumen_pytest" in codigos(info, curso=True)

    def test_un_run_sin_pasos_sigue_siendo_uno_cacheado(self) -> None:
        info = informe(outcome=None, steps=0, resumen=None)
        assert "sg_pipeline_run_cacheado" in codigos(info, curso=True)

    def test_un_run_sin_terminar_no_exige_veredicto_que_no_existe(self) -> None:
        """El criterio del veredicto se omite, y solo ese."""
        assert codigos(informe(outcome=None), curso=True) == ()

    def test_el_ultimo_terminado_sigue_exigiendo_veredicto(self) -> None:
        """Control: el camino de certificacion NO se relajó.

        Sin este, un `en_curso=True` colado por todas partes dejaria pasar runs
        rotos por el otro camino.
        """
        info = informe(outcome="failure", step_failed=1, paso_fallido="lint/sh-0")
        assert "sg_pipeline_run_failure" in codigos(info, curso=False)


# ---------------------------------------------------------------------------
# 3. Y que `main` de verdad elige el run en curso
# ---------------------------------------------------------------------------


class TestMainEligeElRunEnCurso:
    """Lo que falla si `main` vuelve a llamar a `ultimo_terminado`.

    Los tests de arriba miden `en_curso()` y `evaluar()`, que son funciones
    puras. Si `main` no los usara —si eligiera otra vez el ultimo TERMINADO—
    pasarian todos ellos y el trinquete volveria sin que nada lo notara. Por eso
    este bloque ejecuta el script de verdad, contra un journal SINTETICO en
    `tmp_path`: la unica forma de que la SELECCION sea medida y no supuesta.
    """

    def test_un_journal_con_run_anterior_roto_pasa(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = _journal(tmp_path)
        control = _control(tmp_path)

        rc = main(["--db", str(db), "--control-root", str(control), "--json"])

        assert rc == 0, (
            "con un run anterior que fallo de verdad y este en curso sano, el "
            f"script tiene que dar verde; dio rc={rc}. Si vuelve a mirar el "
            "anterior, el trinquete sigue cerrado y no se puede publicar"
        )
        capsys.readouterr()

    def test_la_salida_dice_que_midio_el_run_en_curso(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No basta con dar verde: tiene que decir a que run miro."""
        db = _journal(tmp_path)
        control = _control(tmp_path)

        rc = main(["--db", str(db), "--control-root", str(control), "--json"])
        datos = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert datos["run_id"] == "en-curso", datos
        assert datos["en_curso"] is True, datos

    def test_sin_run_en_curso_verifica_el_ultimo_terminado(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """La certificacion puntual no se pierde: sin nada en curso, el ultimo."""
        db = tmp_path / "solo-terminados.sqlite"
        _crea(
            db,
            [
                ("roto", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
                ("roto", "StepFailed", {"stepName": "lint/sh-0"}),
                ("roto", "RunFinished", {"outcome": "failure"}),
                ("bueno", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
                ("bueno", "EchoOutputCaptured", {"content": _RESUMEN}),
                ("bueno", "StageFinished", {"outcome": "success"}),
                ("bueno", "RunFinished", {"outcome": "success"}),
            ],
        )
        control = _control(tmp_path)

        rc = main(["--db", str(db), "--control-root", str(control), "--json"])
        datos = json.loads(capsys.readouterr().out)

        assert rc == 0
        assert datos["run_id"] == "bueno", datos
        assert datos["en_curso"] is False, datos


def _crea(db: Path, eventos: list[tuple[str, str, dict[str, object]]]) -> None:
    """Journal minimo con el schema real: `events(run_id, kind, payload)`.

    MEDIDO al leer el codigo, no de memoria: el `payload` es una LISTA JSON con
    un dict dentro, no un objeto —`_evento` lo declara y explica que
    `json_extract(payload, '$.outcome')` devuelve NULL sobre este schema.
    """
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (run_id TEXT, kind TEXT, payload TEXT, sequence INTEGER)")
    for i, (run_id, kind, payload) in enumerate(eventos, start=1):
        con.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            (run_id, kind, json.dumps([payload]), i),
        )
    con.commit()
    con.close()


def _journal(tmp_path: Path) -> Path:
    """Dos runs: el ANTERIOR fallo de verdad y este EN CURSO esta sano.

    Es el estado real del repo al abrir B24: `a5cf5a1a` fallo por tres reds de
    estado, y `5229e03b` —con 3473 tests verdes y las ocho etapas de codigo en
    `success`— cayo en la etapa `evidence` por mirar el anterior.
    """
    db = tmp_path / "journal.sqlite"
    _crea(
        db,
        [
            ("anterior-roto", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
            ("anterior-roto", "EchoOutputCaptured", {"content": "..."}),
            ("anterior-roto", "StepFailed", {"stepName": "unit-tests/sh-0"}),
            ("anterior-roto", "RunFinished", {"outcome": "failure"}),
            ("en-curso", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
            ("en-curso", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
            ("en-curso", "EchoOutputCaptured", {"content": _RESUMEN}),
            ("en-curso", "StageFinished", {"outcome": "success"}),
        ],
    )
    return db


def _control(tmp_path: Path) -> Path:
    control = tmp_path / "control"
    for nombre in CONTROL_ROOT:
        (control / nombre).mkdir(parents=True)
    return control


class TestUnRunApareceUnaSolaVez:
    """MEDIDO AL ESCRIBIR ESTO: `informes()` devolvia 5 informes para 2 runs.

    La razon es un `defaultdict` usado como conjunto: `if run_id not in
    acumulado` NO crea la clave, y el `continue` por payload vacio pasaba antes
    de `acumulado[run_id]`. Un run cuyo PRIMER evento trae payload vacio no
    dejaba rastro, y la siguiente fila del mismo run lo volvia a anadir. La
    eleccion entre runs se hace sobre esa lista, asi que una lista con
    duplicados es la peor forma de tener una eleccion.
    """

    def test_un_run_no_se_repite_aunque_empiece_vacio(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = tmp_path / "journal.sqlite"
        _crea(
            db,
            [
                ("roto", "StepStarted", {}),  # payload VACIO a proposito
                ("roto", "StepFailed", {"stepName": "lint/sh-0"}),
                ("roto", "RunFinished", {"outcome": "failure"}),
                ("sano", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
                ("sano", "EchoOutputCaptured", {"content": _RESUMEN}),
                ("sano", "StageFinished", {"outcome": "success"}),
                ("sano", "RunFinished", {"outcome": "success"}),
            ],
        )
        control = _control(tmp_path)

        rc = main(["--db", str(db), "--control-root", str(control), "--json"])
        datos = json.loads(capsys.readouterr().out)

        assert rc == 0, datos
        assert datos["run_id"] == "sano", (
            f"con duplicados, la eleccion se hace sobre una lista en la que "
            f"'roto' aparece varias veces y puede ganar: {datos}"
        )

    def test_informes_no_repite_run_ids(self, tmp_path: Path) -> None:
        """La propiedad EN SI: un `run_id`, un informe. Sin contar, no hay nada.

        El test de arriba mira que gane el run sano, y eso lo hace el ULTIMO de
        la lista tanto con duplicados como sin ellos: mide el resultado, no la
        causa. Este mide la longitud, que es exactamente lo que se rompio.
        """
        db = tmp_path / "journal.sqlite"
        _crea(
            db,
            [
                ("roto", "StepStarted", {}),  # payload VACIO a proposito
                ("roto", "StepFailed", {"stepName": "lint/sh-0"}),
                ("roto", "RunFinished", {"outcome": "failure"}),
                ("sano", "StepStarted", {"stepIndex": 0, "stepName": "x/sh-0"}),
                ("sano", "EchoOutputCaptured", {"content": _RESUMEN}),
                ("sano", "RunFinished", {"outcome": "success"}),
            ],
        )

        ids = [i.run_id for i in informes(db)]

        assert ids == ["roto", "sano"], (
            f"un run_id debe dar UN informe; salieron {ids}. MEDIDO al "
            "escribir esto: un defaultdict usado como conjunto no crea la clave "
            "con `in`, y el `continue` del payload vacio pasaba antes de "
            "registrarla, asi que un run cuyo primer evento va vacio se anadia "
            "una vez POR CADA evento suyo"
        )
