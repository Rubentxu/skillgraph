"""WI-110: la etapa `evidence` tiene que poder volver a pasar.

Medido en WI-110, sobre el journal real y con sonda valida
(`.pipelinek/wi110_measure.py`):

    03:48:17  8d6a9594  7/7 OK  success   <- ultimo run con 8/8
    04:26:49  e722fe84  2/2     failure
    04:35:23  16251236  7/7 OK  failure
    04:49:20  a6c81d08  7/7 OK  failure
    05:26:52  234d7817  7/7 OK  failure
    05:31:46  b774ad14  7/7 OK  failure
    05:37:28  bf2a8e23  7/7 OK  failure

Cinco runs seguidos con las siete etapas de codigo en `success`, y
ninguno se recupero. La razon es que `evaluar()` no puede distinguir un
fallo de codigo de un fallo de la etapa que se verifica a si misma:
`step_failed` es un CONTADOR, y un contador no sabe quien fallo.

Este fichero fija las dos mitades de la exculparion, que son las que
pueden salir mal:

  - Exculpar de mas: perdonar un fallo que no era de `evidence`, y la
    etapa dejaria de vigilar. Es el riesgo real y por eso hay mas tests
    que lo miran.
  - Exculpar de menos: seguir como estaba, que es el deadlock.

Los informes son SINTETICOS porque `evaluar()` es pura sobre `InformeRun`
(no lee disco ni reloj). Asi el guard mide la propiedad sin depender del
estado del journal de esta maquina, que es la clase de razon por la que
WI-105 perdio tres tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_pipeline_receipt import InformeRun, evaluar  # noqa: E402

CONTROL = RAIZ / ".pipelinek" / "control"


def informe(
    *,
    outcome: str = "success",
    step_failed: int = 0,
    paso_fallido: str | None = None,
    steps: int = 11,
    etapas_ok: int = 8,
    etapas_total: int = 8,
    resumen: str | None = "2754 passed in 250.84s",
) -> InformeRun:
    """Informe sintetico. Por defecto, un run sano.

    Los nombres de campo se LEEN de la dataclass real, no de memoria: el
    primer intento de este bloque los invento y revento con
    `unexpected keyword argument`, que es la forma mas rapida de
    descubrir que no se estaba leyendo la firma.
    """
    kwargs: dict[str, object] = {
        "run_id": "sintetico-0001",
        "steps_iniciados": steps,
        "pasos_capturados": steps,
        "etapas_ok": etapas_ok,
        "etapas_total": etapas_total,
        "step_failed": step_failed,
        "outcome": outcome,
        "resumen_pytest": resumen,
    }
    # El campo nuevo se pasa solo si existe: asi este test sigue
    # IMPORTANDO (y fallando) contra el codigo anterior, en vez de
    # reventar al importar.
    if "paso_fallido" in InformeRun.__dataclass_fields__:
        kwargs["paso_fallido"] = paso_fallido
    return InformeRun(**kwargs)  # type: ignore[arg-type]


def problemas(informe_: InformeRun) -> tuple[str, ...]:
    return tuple(p.codigo for p in evaluar(informe_, CONTROL))


# ---------------------------------------------------------------------------
# 1. La exculparion: el caso que envenena la cadena
# ---------------------------------------------------------------------------


def test_un_run_roto_no_pasa() -> None:
    """Control: un run sano no tiene problemas. Sin esto, «todo pasa»."""
    assert problemas(informe()) == ()


def test_la_etapa_que_se_verifica_a_si_misma_no_bloquea_la_cadena() -> None:
    """C1: 7/7 etapas de codigo en success y UNICO StepFailed en `evidence`.

    Este es el caso exacto que produjo cinco runs en FAILURE seguidos.
    Si este test falla, la cadena sigue envenenada.
    """
    r = informe(
        outcome="failure",
        step_failed=1,
        paso_fallido="evidence/sh-0",
        etapas_ok=7,
        etapas_total=8,
    )
    assert problemas(r) == (), (
        "un run cuyo UNICO fallo es la etapa que se verifica a si misma "
        "tiene que pasar: si no, ningun run vuelve a terminar en success"
    )


# ---------------------------------------------------------------------------
# 2. La mitad peligrosa: NO exculpar de mas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre_paso", "etapas_ok"),
    [
        ("unit-tests/sh-0", 6),
        ("lint/sh-0", 7),
        ("coverage-floors/sh-0", 7),
        ("package-build/sh-0", 7),
        ("ci-parity/sh-0", 7),
        ("discover-repo/sh-1", 7),
        # MEDIDO: la mutacion M5 (comparar contra 'e' en vez de contra
        # `ETAPA_AUTOEVALUADA`) sobrevivio a las seis etapas de arriba,
        # porque NINGUNA empieza por 'e'. El codigo era correcto por
        # casualidad, no por diseno. Estos dos casos cierran el hueco: un
        # nombre que COMPARE con 'evidence' pero no sea la etapa tiene que
        # seguir sin pasar, y uno que no compare tiene que fallar.
        ("evidence-hack/sh-0", 7),
        ("export/sh-0", 7),
    ],
)
def test_cualquier_otra_etapa_rota_sigue_sin_pasar(nombre_paso: str, etapas_ok: int) -> None:
    """C2: exculpar `evidence` NO puede volverse en perdonar cualquier cosa.

    Seis etapas distintas, con el mismo informe salvo el nombre del paso
    que fallo. Una exculparion demasiado ancha pasaria todas; una
    demasiado estrecha pasaria la primera y solo la primera.
    """
    r = informe(
        outcome="failure",
        step_failed=1,
        paso_fallido=nombre_paso,
        etapas_ok=etapas_ok,
        etapas_total=8,
    )
    codigos = problemas(r)
    assert "sg_pipeline_step_failed" in codigos, (
        f"el paso {nombre_paso!r} fallo y el verificador lo aprueba: "
        "la exculparion se ha abierto de mas"
    )
    assert "sg_pipeline_run_failure" in codigos


def test_dos_pasos_rotos_nunca_se_exculpan() -> None:
    """Con dos `StepFailed` no hay exculparion, aunque uno sea `evidence`.

    El caso de un solo fallo es el unico exculpable. Dos ya son un fallo
    de codigo, y perdonar la mitad de un fallo es la forma sutil de
    dejar de vigilar.
    """
    r = informe(
        outcome="failure",
        step_failed=2,
        paso_fallido="evidence/sh-0",
        etapas_ok=6,
        etapas_total=8,
    )
    codigos = problemas(r)
    assert "sg_pipeline_step_failed" in codigos, (
        "con dos pasos rotos, uno de ellos `evidence`, no se exculpa nada"
    )


def test_un_run_abortado_sigue_sin_pasar() -> None:
    """C3: `outcome != success` sin `StepFailed` se rechaza igual.

    Un run puede terminar en `failure` sin un solo `StepFailed`: abortion
    del motor, por ejemplo. La exculparion es para la etapa `evidence` y
    su paso, NUNCA para el veredicto del run.
    """
    r = informe(outcome="failure", step_failed=0, etapas_ok=7, etapas_total=8)
    codigos = problemas(r)
    assert "sg_pipeline_run_failure" in codigos, (
        "un run abortado tiene que seguir sin pasar, aunque no haya "
        "ningun StepFailed: si no, la exculparion se ha tragado el run"
    )


def test_sin_el_nombre_del_paso_no_se_exculpa_nada() -> None:
    """Un `StepFailed` SIN nombre no se puede exculpar: no se sabe quien fallo.

    Es el estado actual del repo antes de WI-110, y por eso el deadlock
    era inevitable. Si este test falla, el nombre no se esta propagando y
    la exculparion seria una conjetura.
    """
    r = informe(
        outcome="failure",
        step_failed=1,
        paso_fallido=None,
        etapas_ok=7,
        etapas_total=8,
    )
    codigos = problemas(r)
    assert "sg_pipeline_step_failed" in codigos, (
        "sin el nombre del paso fallido no hay base para exculpar: "
        "el verificador no sabe si fue `evidence` o el codigo"
    )


# ---------------------------------------------------------------------------
# 3. El nombre tiene que llegar desde el journal
# ---------------------------------------------------------------------------


def _journal_con(tmp_path: Path, eventos: list[tuple[str, str]]) -> InformeRun:
    """Escribe un journal SQLite real y devuelve el `InformeRun` que sale.

    Se usa la interfaz REAL (`informes(db)`) contra un journal SQLite de
    verdad, no una reimplementacion: la propiedad que importa es que el
    nombre viaje desde el journal hasta `InformeRun`, y probarlo con una
    copia probaria la copia. Ademas `informes()` lee en modo `ro`, asi que
    el fichero tiene que existir de verdad en disco.
    """
    import sqlite3

    import check_pipeline_receipt as cpr

    db = tmp_path / "journal.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE events (run_id TEXT, kind TEXT, occurred_at TEXT, "
        "payload TEXT, sequence INTEGER)"
    )
    for i, (kind, payload) in enumerate(eventos):
        con.execute(
            "INSERT INTO events VALUES (?,?,?,?,?)",
            ("r-1", kind, "2026-10-03T00:00:00Z", payload, i),
        )
    con.commit()
    con.close()

    resultado = cpr.informes(db)
    assert resultado, "el journal sintetico no produjo ningun informe"
    return resultado[0]


def test_el_acumulador_guarda_el_nombre_del_paso(tmp_path: Path) -> None:
    """El `StepFailed` tiene que guardar SU NOMBRE, no solo contar.

    Sin esto, `evaluar()` no tiene con que decidir: recibe un `1` y no
    puede saber si fue la etapa de evidencia o el linter. El nombre es
    el cambio de fondo de WI-110, y se prueba en la frontera donde se
    pierde: el journal de verdad.
    """
    assert "paso_fallido" in InformeRun.__dataclass_fields__, (
        "`InformeRun` no lleva el nombre del paso que fallo: la "
        "exculparion no tendria en que basarse"
    )

    import json

    informe_ = _journal_con(
        tmp_path,
        [
            ("StepStarted", json.dumps([{"stepName": "lint/sh-0"}])),
            ("StepFailed", json.dumps([{"stepName": "evidence/sh-0", "stepIndex": 0}])),
        ],
    )
    assert informe_.step_failed == 1
    assert informe_.paso_fallido == "evidence/sh-0", (
        f"el journal perdio el nombre del paso: {informe_.paso_fallido!r}"
    )


def test_sin_nombre_en_el_payload_no_hay_nombre(tmp_path: Path) -> None:
    """Un `StepFailed` sin `stepName` deja el nombre a `None`, no lo inventa.

    El journal real de un replay antiguo puede no traer el campo. En ese
    caso el verificador tiene que FALLAR POR DEFAULT, porque no sabe si
    fue la etapa de evidencia o el codigo.
    """
    import json

    informe_ = _journal_con(tmp_path, [("StepFailed", json.dumps([{"stepIndex": 0}]))])
    assert informe_.paso_fallido is None
    assert "sg_pipeline_step_failed" in problemas(informe_), (
        "sin nombre no se exculpa: perdonar a ciegas es peor que no perdonar"
    )


def test_la_etapa_que_se_exculpa_esta_declarada_una_sola_vez() -> None:
    """La exculparion mira un nombre de etapa declarado, no una cadena suelta.

    Si el nombre estuviera escrito dentro de `evaluar()`, cambiarlo
    exigiria tocar el verificador. Declarandolo aqui, el guard de
    abajo puede exigir que las dos copias no diverjan, que es el mismo
    patron que usa WI-108 con `SKIPS_PLATAFORMA`.
    """
    import check_pipeline_receipt as cpr

    assert hasattr(cpr, "ETAPA_AUTOEVALUADA"), (
        "el nombre de la etapa que se exculpa debe ser una constante "
        "declarada, no una cadena dentro de la funcion"
    )
    assert cpr.ETAPA_AUTOEVALUADA == "evidence", (
        f"la etapa autoevaluada deberia ser 'evidence', es {cpr.ETAPA_AUTOEVALUADA!r}"
    )


# ---------------------------------------------------------------------------
# 4. La exculparion es minima y esta escrita
# ---------------------------------------------------------------------------


def test_la_exculparion_no_esta_oculta_en_el_texto() -> None:
    """El comentario que explica la exculparion tiene que estar.

    Una exculparion sin escribir es una exculparion que nadie puede
    revisar. Y el comentario NO se busca por la cadena del nombre de la
    etapa —busca el CONCEPTO— porque citar el literal lo volveria a hacer
    dispara el patron.
    """
    fuente = (SCRIPTS / "check_pipeline_receipt.py").read_text(encoding="utf-8")
    bloque = fuente.split("def evaluar(", 1)[1].split("\ndef ", 1)[0]
    minusculas = bloque.lower()
    tiene_explicacion = any(
        clave in minusculas for clave in ("autoevaluada", "si misma", "a si misma", "exculpa")
    )
    assert tiene_explicacion, (
        "`evaluar()` exculpa a la etapa que se verifica a si misma y no "
        "lo explica: una exculparion sin escribir no se puede revisar"
    )


def test_la_exculparion_no_depende_del_orden_de_las_etapas() -> None:
    """Contar etapas NO es la via: el nombre del paso es la via.

    Si la exculparion se apoyara en `etapas_ok == etapas_total - 1`, un
    run con una etapa cualquiera caida y otra de mas pasaria. Este test
    fija que el caso se decide por el NOMBRE, no por la aritmetica.
    """
    r = informe(
        outcome="failure",
        step_failed=1,
        paso_fallido="lint/sh-0",
        etapas_ok=7,
        etapas_total=8,
    )
    assert "sg_pipeline_step_failed" in problemas(r), (
        "7 de 8 etapas con `lint` caida NO puede pasar: la exculparion "
        "tiene que mirar el nombre del paso, no la aritmetica de etapas"
    )


# ---------------------------------------------------------------------------
# 5. La regla dice como se comprueba
# ---------------------------------------------------------------------------


def test_la_receta_no_cambio() -> None:
    """C6: el arreglo NO toca `.pipeline.kts`.

    Es la decision de alcance de WI-110, y es la que hace que las
    certificaciones de WI-101 a WI-109 sigan valiendo. Un cambio aqui
    invalidaria todas a la vez, asi que se fija con un test: el
    digest es parte del contrato de CI.

    B10 anadio la etapa `public-surfaces` y actualizo el digest A
    PROPOSITO. El mensaje de este test dice exactamente eso: si cambias
    la receta, el digest hay que actualizarlo a proposito y las
    certificaciones anteriores quedan reinterpretadas. Ese es el
    contrato, y por eso el digest se cambia con el motivo escrito al
    lado y no en silencio.
    """
    import hashlib

    # 7541ced5... era el digest con las ocho etapas. B10 anadio
    # `public-surfaces` (nona), el guard WI-98 lo exigio al descubrir el
    # checker huerfano, y el digest paso a de3fbf76... al registrarlo aqui.
    # B24 cambio el COMENTARIO de la etapa `evidence`, no su comando: la
    # etapa paso de verificar el run ANTERIOR a verificar el EN CURSO, porque
    # lo anterior era un trinquete que tras un rojo real impedia publicar para
    # siempre. El digest cambia con el motivo escrito al lado, que es
    # exactamente lo que este test exige. Detector de cambios: los comentarios
    # no ejecutan codigo, asi que este digest mide que alguien leyo el bloque.
    esperado = "a8c59c949362a12b97a00a9df3bfa47201589d098d507a03412da89c937b32a3"
    real = hashlib.sha256((RAIZ / ".pipeline.kts").read_bytes()).hexdigest()
    assert real == esperado, (
        f"`.pipeline.kts` cambio: {real}\n"
        "WI-110 arreglo el verificador, no la receta. Si cambias la "
        "receta, este digest hay que actualizarlo a proposito y las "
        "certificaciones anteriores quedan reinterpretadas."
    )


def test_la_regla_dice_que_la_etapa_es_autoevaluada() -> None:
    """`AGENTS.md` debe decir que la etapa se exculpa a si misma, y por que.

    Una exculparion que solo vive en el codigo es una exculparion que
    el siguiente que lea la regla no puede prever.
    """
    texto = (RAIZ / "AGENTS.md").read_text(encoding="utf-8")
    assert "wi110" in texto.lower(), (
        "la seccion de criterios debe registrar WI-110: sin eso, el "
        "arreglo es invisible para quien lea la regla"
    )


def test_ambos_criterios_siguen_vigentes() -> None:
    """El arreglo NO puede haber desactivado los criterios que ya existian.

    Contraejemplo del propio guard: si `evaluar()` dejo de mirar
    `outcome` o `step_failed` para que todo pasara, los tests de arriba
    seguirian verdes y aqui no.

    Se mira el AST y no el texto, porque la primera version buscaba
    `informe.step_failed` como cadena y la mutacion M10 —cambiar el
    `if` por `if False:`— la sobrevivio: la cadena seguia ahi, en el
    cuerpo del `if` muerto. Un guard que busca una cadena busca la
    cadena: es la misma regla de la serie, tercera vez en tres semanas.
    """
    import ast

    fuente = (SCRIPTS / "check_pipeline_receipt.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente, filename="check_pipeline_receipt.py")
    cuerpo = next(
        n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "evaluar"
    )

    # Los `if` que MUEVEN un Problema hacia la lista: sus condiciones
    # tienen que Mentionar el campo que vigilan.
    problemas_emitidos: set[str] = set()
    campos_por_codigo = {
        "sg_pipeline_run_failure": "informe.outcome",
        "sg_pipeline_step_failed": "informe.step_failed",
    }
    for stmt in cuerpo.body:
        if not isinstance(stmt, ast.If):
            continue
        for sub in ast.walk(stmt):
            if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)):
                continue
            if sub.func.id != "Problema" or not sub.args:
                continue
            primero = sub.args[0]
            if not (isinstance(primero, ast.Constant) and isinstance(primero.value, str)):
                continue
            problemas_emitidos.add(primero.value)
            campo = campos_por_codigo.get(primero.value)
            if campo is not None:
                # La CONDICION del `if` tiene que mirar el campo que el
                # problema afirma vigilar. Sin esto, cambiar el `if` por
                # `if False:` deja el criterio muerto y silencioso.
                condicion = ast.unparse(stmt.test)
                if campo not in condicion:
                    raise AssertionError(
                        f"{primero.value} se emite sin mirar {campo!r}: "
                        f"la condicion es {condicion!r}, que no comprueba nada"
                    )

    assert "sg_pipeline_run_failure" in problemas_emitidos, (
        "`evaluar()` dejo de emitir sg_pipeline_run_failure"
    )
    assert "sg_pipeline_step_failed" in problemas_emitidos, (
        "`evaluar()` dejo de emitir sg_pipeline_step_failed"
    )


def test_el_guard_mira_lo_que_dice_que_mira() -> None:
    """Contraejemplo del contador: si `evaluar()` no existiera, esto pasaria."""
    assert problemas(informe(step_failed=99, paso_fallido="lo-que-sea")) != (), (
        "un informe con 99 pasos rotos tiene que producir problemas: "
        "si no, `evaluar()` dejo de mirar `step_failed` del todo"
    )
