#!/usr/bin/env python3
"""Comprueba los criterios de éxito que AGENTS.md declara para un run.

Por qué existe
--------------
`AGENTS.md` («CI Local Obligatorio») enumera SEIS criterios que un run
«debe cumplir». Antes de WI-105 **ninguna herramienta comprobaba ninguno
de ellos**: la etapa `evidence` de `.pipeline.kts` —el único sitio de la
receta que toca `.pipelinek/`— hacía tres cosas,

    ls -la .pipelinek/db.sqlite
    test -d .pipelinek/control/last-run  && echo 'last-run present'
    test -d .pipelinek/control/workspace && echo 'workspace tracking present'

y los tres operandos los crea el motor ANTES de la etapa. MEDIDO contra
el journal real de este repo: 15 runs, 3 de ellos `RunFinished/failure`, y
la etapa dice exactamente lo mismo en los quince. Es la forma de WI-101
aplicada al registro del propio CI: una etapa que certifica sin ejecutar
la comprobación.

El único criterio referenciado en algún sitio era el 1, con un `grep`
sobre el stdout en `scripts/hooks/pre-push` — hook que no está instalado,
y cuyo `grep` ya se comió esa cadena exacta una vez en la historia de
este repo.

Qué NO es el fallo
------------------
No es que un run pueda estar rojo sin que se note: eso es lo normal. Es
que **un `SUCCESS` que no ejecutó nada es indistinguible de una
verificación real**, y `Pipeline finished with SUCCESS` lo dicen los dos.
AGENTS.md lo describe con sus palabras —«sin `--rerun`, un run cuyo
script no ha cambiado reutiliza el veredicto previo y termina en
`Pipeline finished with SUCCESS` sin ejecutar un solo step»— y el
criterio 2 existe para separar esos dos casos. Ese criterio era
precisamente el que no comprobaba nadie.

Qué se comprueba, y qué NO
--------------------------
Se comprueban los criterios **1, 2, 3, 4 y 5**, que son propiedades del
journal y del árbol. El **criterio 6 no se comprueba aquí**: es el SHA-256
del `.pipeline.kts` «registrado en la sesión», y una sesión es del agente,
no del repo. Decir que se comprueba sería la misma mentira que este
script viene a arreglar, así que se declara y se queda fuera.

Por qué verifica el run ANTERIOR
--------------------------------
La receta no puede verificar su propio run: cuando la etapa `evidence`
se ejecuta, el run en curso todavía no tiene su `RunFinished`. La
propiedad es real —el huevo y la gallina no es una excusa— y la
resolución sale del propio motor: **`RunFinished` más reciente** es, durante
un run, el run anterior. Así el mismo script sirve para los dos usos:

  * la receta, sin `--run-id`, verifica el último run terminado;
  * la certificación, con `--run-id <id>`, verifica uno concreto.

Sin journal no hay nada que verificar y se pasa con un mensaje, porque en
un clon nuevo `.pipelinek/` no está versionado y exigir un run sería
hacer la receta inejecutable donde no puede ser ejecutable.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent

#: Resumen de pytest tal y como lo emite `scripts/coverage.sh`: la línea
#: que separa una ejecución real de un veredicto cacheado. `N passed in Xs`.
RESUMEN_PYTEST: Final = re.compile(r"\b\d+\s+(?:passed|failed|error)\b")

#: Numero de tests que NO se ejecutaron, tal y como los imprime pytest.
#:
#: `skipped` y `xfailed` son la misma propiedad con dos nombres: un test que
#: se salta y uno que se sabe que falla y no se mira. MEDIDO el 2026-10-03:
#: con un run cuyo resumen es `2715 passed, 3 skipped`, `evaluar` devolvia
#: cero problemas y decia «OK: el run cumple los criterios que declara
#: AGENTS.md». El criterio 2 —el que existe para separar un run real de un
#: veredicto cacheado— aceptaba el resumen con skips sin pestanear, porque la
#: pregunta por los skips no existia. No era un bug del regex: era que nadie
#: la habia hecho.
TESTS_SALTEADOS: Final = re.compile(r"\b(\d+)\s+(?:skipped|xfailed)\b", re.IGNORECASE)

#: Los skips LEGITIMOS del repo, declarados uno a uno (WI-108).
#:
#: No es la lista de los skips que hay: es la lista de los skips cuya
#: AUSENCIA seria un defecto. La prohibition de AGENTS §6.2 es contra
#: *esconder fallos*, y `fcntl` no existir en Windows no es un fallo
#: escondido: es una diferencia real entre maquinas. Lo que §6.2 prohibe con
#: nombre es el skip POR FALTA DE ARTEFACTO, y ese no entra aqui por mucho que
#: alguien quiera declararlo.
#:
#: Vive en el guard y no en el test, y `tests/test_wi108_zero_skips.py`
#: comprueba que las dos copias no han divergido. Vigilar solo en una
#: direccion deja de ser vigilar: un skip de plataforma que se borra deja su
#: declaracion sin suelo, igual que una desviacion de cobertura que apunta a
#: un fichero que ya no esta.
SKIPS_PLATAFORMA: Final[dict[str, str]] = {
    "tests/test_locks.py": "fcntl no existe en Windows: no es un fallo escondido",
    "tests/test_evidence_lock.py": "idem: el test toma el lock con fcntl",
}

#: Los cuatro paths que AGENTS.md declara obligatorios en el control root.
CONTROL_ROOT: Final = ("last-run", "retry-control", "wait-until-control", "workspace")


@dataclass(frozen=True, slots=True)
class Problema:
    """Un incumplimiento del contrato. Inmutable: se acumula en tuplas."""

    codigo: str
    mensaje: str


@dataclass(frozen=True, slots=True)
class InformeRun:
    """Lo medido sobre el journal de UN run. Inmutable."""

    run_id: str
    steps_iniciados: int
    pasos_capturados: int
    etapas_ok: int
    etapas_total: int
    step_failed: int
    outcome: str | None
    resumen_pytest: str | None


def _evento(payload: str) -> dict:
    """El `payload` del journal es una LISTA JSON con un dict dentro.

    MEDIDO: `json_extract(payload, '$.outcome')` devuelve NULL en SQLite
    sobre este schema, y `RunFinished` aparecía con outcome `None` en las
    15 filas. El listón es una lista, no un objeto.
    """
    datos = json.loads(payload)
    if isinstance(datos, list):
        return datos[0] if datos else {}
    return datos


def informes(db: Path) -> tuple[InformeRun, ...]:
    """Un `InformeRun` por `run_id` del journal, en orden de terminación.

    El `run_id` **se reutiliza entre replays**, así que dos ejecuciones
    pueden compartirlo y arrastrar `StepFailed` históricos. Por eso el
    `InformeRun` acumula sobre el `run_id` y no pretende ser «una
    ejecución»: es «lo que el journal sabe de ese identificador». Es lo
    que declara el criterio 5, y la limitación se dice en el mensaje
    cuando aparece.
    """
    if not db.exists():
        return ()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        filas = con.execute(
            "SELECT run_id, kind, payload FROM events ORDER BY sequence, rowid"
        ).fetchall()
    except sqlite3.DatabaseError as exc:  # journal ilegible o corrupto
        raise SystemExit(f"no se pudo leer el journal {db}: {exc}") from exc
    finally:
        con.close()

    acumulado: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "steps": 0,
            "echo": 0,
            "etapas_ok": 0,
            "etapas": 0,
            "fallos": 0,
            "outcome": None,
            "resumen": None,
        }
    )
    orden: list[str] = []
    for run_id, kind, payload in filas:
        if run_id not in acumulado:
            orden.append(run_id)
        evento = _evento(payload)
        if not evento:
            continue
        estado = acumulado[run_id]
        if kind == "StepStarted":
            estado["steps"] = int(estado["steps"]) + 1
        elif kind == "EchoOutputCaptured":
            estado["echo"] = int(estado["echo"]) + 1
            if estado["resumen"] is None:
                for linea in str(evento.get("content") or "").splitlines():
                    if RESUMEN_PYTEST.search(linea):
                        estado["resumen"] = linea.strip()
                        break
        elif kind == "StageFinished":
            estado["etapas"] = int(estado["etapas"]) + 1
            if evento.get("outcome") == "success":
                estado["etapas_ok"] = int(estado["etapas_ok"]) + 1
        elif kind == "StepFailed":
            estado["fallos"] = int(estado["fallos"]) + 1
        elif kind == "RunFinished":
            estado["outcome"] = evento.get("outcome")

    return tuple(
        InformeRun(
            run_id=run_id,
            steps_iniciados=int(acumulado[run_id]["steps"]),
            pasos_capturados=int(acumulado[run_id]["echo"]),
            etapas_ok=int(acumulado[run_id]["etapas_ok"]),
            etapas_total=int(acumulado[run_id]["etapas"]),
            step_failed=int(acumulado[run_id]["fallos"]),
            outcome=acumulado[run_id]["outcome"],  # type: ignore[arg-type]
            resumen_pytest=acumulado[run_id]["resumen"],  # type: ignore[arg-type]
        )
        for run_id in orden
    )


def ultimo_terminado(todos: tuple[InformeRun, ...]) -> InformeRun | None:
    """El `InformeRun` más reciente que tiene `RunFinished`.

    Devolver el ÚLTIMO Y NO EL PRIMERO importa: `informe()` acumula en
    orden de lectura, y el criterio 5 habla «de los eventos de la
    ejecución actual». Durante un run, este es el run ANTERIOR — que es
    justo lo que la receta puede verificar.
    """
    terminados = [i for i in todos if i.outcome is not None]
    return terminados[-1] if terminados else None


def _control_incompleto(control: Path) -> tuple[str, ...]:
    if not control.is_dir():
        return CONTROL_ROOT
    return tuple(n for n in CONTROL_ROOT if not (control / n).is_dir())


def resumen_sin_skips(resumen: str | None) -> bool:
    """¿Este resumen de pytest declara cero tests sin ejecutar?

    Predicado PURO y separado a proposito, por la misma razon que
    `_bump_valido` en WI-106: un predicado que solo se llama con el valor
    de hoy no comprueba un dominio, comprueba una coincidencia. Hoy el
    resumen real no trae `skipped`, asi que aqui se le llama con numeros
    que el repo no produce.

    La pregunta es por el VALOR, no por la presencia: «2718 passed, 0
    skipped» declara cero tests sin ejecutar y es un run limpio. pytest no
    imprime el cero (lo omite), asi que un guard que mirara «hay skipped»
    en vez de «cuantos» trataria una linea limpia como un incumplimiento —
    un falso positivo que entrena a su lector a ignorar sus avisos.

    `None` (sin resumen) devuelve `True`: la ausencia de resumen la juzga
    otro criterio, y hacer que esta funcion dijera «no» anadiria un
    incumplimiento duplicado con un mensaje que no sabe cual de los dos es
    el bueno.
    """
    return _conteo_salteados(resumen) == 0


def _conteo_salteados(resumen: str | None) -> int:
    """Cuantos tests NO se ejecutaron, sumando `skipped` y `xfailed`."""
    if resumen is None:
        return 0
    return sum(int(m) for m in TESTS_SALTEADOS.findall(resumen))


def evaluar(informe: InformeRun, control: Path) -> tuple[Problema, ...]:
    """Los criterios que este run incumple. Vacío = cumple.

    Función PURA sobre un `InformeRun`: no lee disco ni reloj. El
    `control` entra como argumento justamente para que se pueda probar
    con un árbol que no es el del repo.
    """
    problemas: list[Problema] = []
    rid = informe.run_id[:8]

    if informe.outcome != "success":
        problemas.append(
            Problema(
                "sg_pipeline_run_failure",
                f"el run {rid} termino en {informe.outcome!r}, no en 'success'",
            )
        )

    if informe.step_failed:
        problemas.append(
            Problema(
                "sg_pipeline_step_failed",
                f"el run {rid} registra {informe.step_failed} StepFailed; "
                "el criterio 5 exige cero en la ejecucion. Ojo: el run_id "
                "se reutiliza entre replays, asi que un StepFailed puede "
                "ser de una ejecucion anterior del mismo identificador",
            )
        )

    if informe.steps_iniciados == 0:
        problemas.append(
            Problema(
                "sg_pipeline_run_cacheado",
                f"el run {rid} termino en {informe.outcome!r} SIN ejecutar un "
                "s solo step: es un veredicto cacheado, no una verificacion. "
                "Falta --rerun en el comando canonico",
            )
        )

    if informe.steps_iniciados and informe.resumen_pytest is None:
        problemas.append(
            Problema(
                "sg_pipeline_sin_resumen_pytest",
                f"el run {rid} ejecuto {informe.steps_iniciados} pasos pero "
                "ningun EchoOutputCaptured trae el resumen de pytest "
                "('N passed in Xs'); el criterio 2 lo exige y es lo que "
                "separa un run real de uno que no midio la suite",
            )
        )

    salteados = _conteo_salteados(informe.resumen_pytest)
    if salteados:
        problemas.append(
            Problema(
                "sg_pipeline_tests_skipped",
                f"el run {rid} ejecuto la suite con {salteados} "
                "test(s) sin ejecutar (skipped o xfailed) en "
                f"{informe.resumen_pytest!r}. AGENTS.md 6.2 prohibe "
                "pytest.skip para esconder fallos y dice que un skip por "
                "falta de artefacto es el mismo defecto con otra forma: un "
                "test que no se ejecuta no mide nada y el run pasa en verde "
                "igual. Los skips de plataforma estan declarados en "
                "SKIPS_PLATAFORMA; este no lo es",
            )
        )

    faltan = _control_incompleto(control)
    if faltan:
        problemas.append(
            Problema(
                "sg_pipeline_control_root_incompleto",
                f"el control root {control} no tiene: {', '.join(faltan)}. "
                "AGENTS.md los declara obligatorios",
            )
        )

    return tuple(problemas)


def formatear(problemas: tuple[Problema, ...], informe: InformeRun | None) -> str:
    if informe is None:
        return (
            "OK: no hay ningun run terminado en el journal que verificar. "
            "Es lo normal en un clon nuevo, donde .pipelinek/ no esta "
            "versionado."
        )
    cabecera = (
        f"run {informe.run_id}: {informe.etapas_ok}/{informe.etapas_total} "
        f"etapas, {informe.steps_iniciados} pasos, veredicto {informe.outcome!r}"
    )
    if not problemas:
        return (
            f"OK: el run cumple los criterios que declara AGENTS.md. {cabecera}. "
            "Criterio 6 (SHA-256 del .pipeline.kts) NO se comprueba aqui: es "
            "una accion del agente, no una propiedad del journal."
        )
    lineas = [f"FALLO: {len(problemas)} incumplimiento(s) de los criterios de exito ({cabecera})"]
    lineas.extend(f"  [{p.codigo}] {p.mensaje}" for p in problemas)
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Comprueba los criterios de exito que AGENTS.md declara para un run."
    )
    parser.add_argument("--db", type=Path, default=ROOT / ".pipelinek/db.sqlite")
    parser.add_argument("--control-root", type=Path, default=ROOT / ".pipelinek/control")
    parser.add_argument(
        "--run-id",
        default=None,
        help="verificar este run; por defecto, el ultimo terminado",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    todos = informes(args.db)
    if args.run_id is not None:
        candidatos = tuple(i for i in todos if i.run_id.startswith(args.run_id))
        informe = candidatos[-1] if candidatos else None
        if informe is None:
            print(f"FALLO: el journal no tiene ningun run con id {args.run_id!r}")
            return 1
    else:
        informe = ultimo_terminado(todos)

    problemas = () if informe is None else evaluar(informe, args.control_root)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not problemas,
                    "run_id": None if informe is None else informe.run_id,
                    "problemas": [{"codigo": p.codigo, "mensaje": p.mensaje} for p in problemas],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(formatear(problemas, informe))
    return 0 if not problemas else 1


if __name__ == "__main__":
    raise SystemExit(main())
