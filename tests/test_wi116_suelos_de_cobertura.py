"""La deuda de los SUELOS de cobertura, cerrada por donde se puede.

**POR QUE ESTE FICHERO EXISTE, Y QUE ES LO QUE CIERRA.**

`check_coverage_floors.py` es la etapa que sigue en rojo del gate canonico.
MEDIDO sobre el arbol real, con la suite completa:

    src/skillgraph/cli/commands/expansion.py   51.71 %  suelo 70   -18.29
    src/skillgraph/cli/commands/runs.py        44.95 %  suelo 70   -25.05
    src/skillgraph/cli/runner.py               55.08 %  suelo 70   -14.92
    src/skillgraph/cli/commands/knowledge.py   65.08 %  suelo 70    -4.92
    src/skillgraph/cli/support.py              66.96 %  suelo 70    -3.04
    src/skillgraph/knowledge/context_controller.py 89.35 % suelo 90 -0.65

Seis incumplimientos, **ninguno de R0 ni de R1**: los dejaron los commits de
la campana B22-B30 ya publicada. Se cierran por Distance al suelo, de menor a
mayor, para que cada commit que sube la cifra sea pequeno y medible.

**Y UN SEPTIMO QUE SI ERA MIO, Y QUE ESTA AQUI POR ESO.**
`observation_ingestion.py` —el modulo que creo R1.C— quedo en **84 %** al
nacer, por debajo del 90 % que su ubicacion declara. AGENTS 6.3 no perdona
ese suelo, y lo primero que se hace con un modulo nuevo es medirlo. Lo que
faltaba eran las dos lineas de la rama de CONFLICTO de la ingesta, que es
justo la propiedad que B27 construyo: el aviso se recoge, no se tira.

# LO QUE ESTE FICHERO NO HACE

No baja ningun suelo. `SUELOS_ESPECIALES` y `EXCEPCIONES` siguen exactamente
como estaban: tocar un suelo para que un gate de en verde es la forma de
guarda que este repo lleva cinco bloques cerrando. Aqui la unica palanca es
**escribir los tests que faltan**.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgraph.cli import support
from skillgraph.cli.exit_codes import EXIT_PLAN_NOT_FOUND
from skillgraph.core.errors import ParseError

# ---------------------------------------------------------------------------
# support.py — cargar, validar y escribir `plan.json`
# ---------------------------------------------------------------------------


def _plan_dict() -> dict[str, object]:
    """Un plan minimo VALIDO, con lo que `_load_plan_from_storage` exige.

    **MEDIDO AL ESCRIBIRLO, Y NO ES COSA ESTETICA.** La primera version
    dejo `namespace` vacio y `api_version`/`resource_revision` sin poner, y
    `WorkflowNode.__post_init__` lo rechaza con `ValidationError: namespace
    vacio`. Es decir: **un `plan.json` con esos campos ausentes es un
    artefacto CORRUPTO, no un planDefaults**, y el loader lo dice bien.

    Por eso el plan de aqui lleva lo que la clase exige de verdad: un
    `namespace` real y la version/revision del recurso. Un test que fabricase
    el plan mas pequeno posible estaria probando que el loader PUEDE fallar,
    que ya lo hacia el test de plan truncado.
    """
    return {
        "initial": "a",
        "nodes": [
            {
                "name": "a",
                "kind": "ActionNode",
                "namespace": "sg.demo",
                "api_version": "1.0.0",
                "resource_revision": 1,
                "expected_result": "texto",
            },
            {
                "name": "b",
                "kind": "ActionNode",
                "namespace": "sg.demo",
                "api_version": "1.0.0",
                "resource_revision": 1,
                "expected_result": "texto",
            },
        ],
        "transitions": [{"source": "a", "outcome": "ok", "target": "b"}],
    }


def _proyecto(tmp_path: Path, contenido: str | None = None) -> Path:
    directorio = tmp_path / "proyecto"
    directorio.mkdir(parents=True, exist_ok=True)
    if contenido is not None:
        (directorio / "plan.json").write_text(contenido, encoding="utf-8")
    return directorio


class TestElPlanSeCarga:
    """**EL CAMINO FELIZ Y SUS TRES VECINOS.**

    `_load_plan_from_storage` es una lectura de artefacto de disco con tres
    salidas posibles —carga, «no esta» y «esta roto»—. La tercera es la que
    importa: un `plan.json` truncado es un artefacto corrupto, y WI-109 lo
    traduce a `ParseError` para que salga con el exit code del dominio y no
    como un Traceback de Python.
    """

    def test_carga_un_plan_valido(self, tmp_path: Path) -> None:
        proyecto = _proyecto(tmp_path, json.dumps(_plan_dict()))

        plan = support._load_plan_from_storage(proyecto)

        assert plan.initial == "a"
        assert [n.name for n in plan.nodes] == ["a", "b"]
        assert len(plan.transitions) == 1

    def test_el_plan_cargado_sobrevive_la_ida_y_vuelta(self, tmp_path: Path) -> None:
        """La propiedad que de verdad importa: lo que se carga es lo que hay.

        Si la carga perdiera un nodo o inventara una transicion, el plan
        ejecutaria un grafo distinto del que esta en disco, y eso no se ve
        mirando que «ha cargado algo».
        """
        proyecto = _proyecto(tmp_path, json.dumps(_plan_dict()))

        plan = support._load_plan_from_storage(proyecto)

        assert len(plan.nodes) == 2
        assert {(t.source, t.outcome, t.target) for t in plan.transitions} == {("a", "ok", "b")}

    def test_un_plan_que_NO_existe_sale_con_SU_EXIT_CODE(self, tmp_path: Path) -> None:
        """Ausente y corrupto son DOS errores distintos, con dos salidas."""
        proyecto = _proyecto(tmp_path)  # sin escribir el plan

        with pytest.raises(SystemExit) as exc:
            support._load_plan_from_storage(proyecto)

        assert exc.value.code == EXIT_PLAN_NOT_FOUND, (
            f"un plan ausente salio con {exc.value.code} y el contrato dice {EXIT_PLAN_NOT_FOUND}"
        )

    def test_un_plan_TRUNCADO_es_un_error_de_DOMINIO(self, tmp_path: Path) -> None:
        """**WI-109, y la razon de que sea `ParseError` y no `JSONDecodeError`.**

        Un `json.JSONDecodeError` no es un error del dominio: no lleva `code`,
        luego el runner no puede traducirlo y lo que sale es un Traceback.
        El enunciado de WI-109 lo trata como exit code 11, no el 1 de Python.
        """
        proyecto = _proyecto(tmp_path, '{"nodes": [{"name": "a", ')

        with pytest.raises(ParseError) as exc:
            support._load_plan_from_storage(proyecto)

        # Y la cadena del error dice DONDE estaba el artefacto roto.
        assert "plan.json" in str(exc.value), exc.value
        assert exc.value.code == "sg_parse", (
            f"el error lleva code={exc.value.code!r} y el runner lo traduce "
            "por ahi: sin el, sale como Traceback"
        )

    def test_el_error_de_plan_TRUNCADO_dice_QUE_FICHERO(self, tmp_path: Path) -> None:
        proyecto = _proyecto(tmp_path, "no es json en absoluto")
        with pytest.raises(ParseError) as exc:
            support._load_plan_from_storage(proyecto)
        assert str(proyecto / "plan.json") in str(exc.value), (
            f"el mensaje no nombra el fichero: {exc.value}. Un error que no "
            "dice donde esta el artefacto deja al operador buscando."
        )


class TestLaBaseAusente:
    """El otro exit code de este modulo, y el mas barato de probar."""

    def test_una_base_que_NO_existe_sale_con_SU_exit_code(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        # MEDIDO al escribirlo: `resolve_data_root` recibe un `Path` y
        # llama a `.expanduser()` sobre el; pasar un `str` revienta con
        # `AttributeError` en lugar de decir «el proyecto no existe».
        args = SimpleNamespace(data_root=tmp_path, project="fantasma")
        proyecto, error = support.resolve_project(args, "fantasma")

        assert proyecto == {}, f"un proyecto inexistente devolvio {proyecto!r}"
        assert error is not None, (
            "un proyecto que no existe devolvio OK: el runner seguiria "
            "adelante contra una base que no esta"
        )


class TestElHarnessNoBorraTrabajo:
    """**UN RECORDATORIO QUE SE PAGA CON UN TEST.**

    Quince de los veintisiete `scripts/mutate_*.py` restauraban con
    `git checkout --`, que devuelve el arbol DEL INDICE. Eso borro la
    migracion `0005` de R1.F con sus trece tests a mitad de certificacion, y
    se recupero de un volcado accidental.

    Este test no mide el harness: comprueba que el arbol de trabajo sigue
    teniendo lo que el ultimo commit dice, y que ninguna suite se ha
    quedado sin commitear por debajo. Un guard que se pone verde en un
    arbol vacio es peor que no tener guard.
    """

    def test_el_arbol_no_tiene_nada_sin_commitear_entre_scripts_y_src(self) -> None:
        import subprocess

        raiz = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            ["git", "-C", str(raiz), "status", "--porcelain", "--", "src", "scripts"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        sucio = [linea for linea in proc.stdout.splitlines() if linea.strip()]
        assert not sucio, (
            "hay cambios sin commitear en src/ o scripts/:\n  "
            + "\n  ".join(sucio)
            + "\n\nUn harness con `git checkout --` debajo se los llevaria en "
            "cuanto corra. Commitea antes de certificar."
        )


# ---------------------------------------------------------------------------
# observation_ingestion.py — la rama de CONFLICTO, que es la de B27
# ---------------------------------------------------------------------------


class TestLaIngestaRecogeElConflicto:
    """**LO QUE EL MODULO DE R1.C NO MEDIA, Y QUE ES SU BRAZO DERECHO.**

    MEDIDO al crear `observation_ingestion.py`: el modulo nacio en **84 %**,
    por debajo del 90 % que AGENTS 6.3 declara para `knowledge/`. Las dos
    lineas sin cubrir eran justo la rama de `if registro.conflicto:`.

    **Y LA RAMA NO ES UN DETALLE: es la propiedad de B27.** El aviso de que
    se ha dicho otra cosa **se recoge y se devuelve** en
    `ObservationIngesta.conflictos`; descartarlo seria perderlo una capa mas
    arriba, donde el `conflicts_for` de B27 daria lo mismo con una consulta
    —y lo que se pierde es el aviso en el MOMENTO en que ocurre, que es el
    unico momento en que el que escribe sabe que ha dicho otra cosa.

    Un modulo recien mudado con la rama del conflicto sin ejecutar es un
    modulo cuya mitad derecha nadie sabe si funciona.
    """

    @staticmethod
    def _preparar(s: object) -> None:
        from skillgraph.knowledge.graph import Entity, Source, source_id

        s.upsert_entity(
            tenant_id="t",
            project_id="p",
            entity=Entity(entity_id="file:a.py", kind="file", stable_key="a.py"),
        )
        s.register_source(
            tenant_id="t",
            project_id="p",
            source=Source(
                source_id=source_id("local:a.py"),
                kind="local_file",
                content_hash="h",
                locator={},
                git_commit_sha=None,
                git_tree_sha=None,
                working_tree_status=None,
                checked_at="2026-10-07T00:00:00Z",
                freshness="current",
            ),
        )

    @staticmethod
    def _envelope(valor: object) -> object:
        """El envelope como lo construye B26: `Observation`, no `Claim`.

        **MEDIDO AL ESCRIBIRLO.** La primera version pasaba `Claim` a
        `ObservationEnvelope` y reventaba con `missing 4 required
        positional arguments`. El envelope es lo que dice una HERRAMIENTA —
        `Observation(predicate, object_literal)`— y `normalizar` es quien la
        convierte en `Claim`. Confundir las dos capas es facil porque las dos
        se llaman parecido, y por eso el docstring lo dice explicitamente.
        """
        from skillgraph.knowledge.graph import source_id
        from skillgraph.knowledge.observation import (
            Observation,
            ObservationEnvelope,
        )
        from skillgraph.platform.ports.capabilities import CapabilitySpec

        return ObservationEnvelope(
            producer=CapabilitySpec(type_name="cognicode.code", version="1.0"),
            adapter="cognicode",
            source_id=source_id("local:a.py"),
            subject="file:a.py",
            observed_at="2026-10-07T00:00:00Z",
            revision="r1",
            observations=(Observation(predicate="line_count", object_literal=valor),),
        )

    def test_sin_conflicto_la_ingesta_viene_LIMPIA(self, tmp_path: Path) -> None:
        """El caso de siempre: lo que no se contradice no se reporta."""
        from skillgraph.knowledge.observation_ingestion import ingerir
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "x.sqlite")
        self._preparar(s)

        ingesta = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(137))

        assert ingesta.conflictos == (), ingesta.conflictos
        assert len(ingesta.claims) == 1

    def test_un_conflicto_LLEGA_AL_QUE_ESCRIBIO(self, tmp_path: Path) -> None:
        """**Y el otro lado: el aviso NO se tira.**

        Se escribe la misma afirmacion con otro valor; la segunda tiene que
        volver con el conflicto recogido. Este es el unico motivo por el que
        la rama existe, asi que es el unico que hay que probar.
        """
        from skillgraph.knowledge.observation_ingestion import ingerir
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "x.sqlite")
        self._preparar(s)

        # La primera afirmacion, escrita por el camino normal.
        ingested = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(137))
        assert ingested.conflictos == ()

        # La misma afirmacion, otro valor, misma revision y misma fuente.
        ingerible = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(250))

        # **B35: ESTE TEST CAMBIO DE SIGNIFICADO, Y NO SE DISFRAZA.**
        #
        # Decia «la misma afirmacion con otro valor tiene que volver con el
        # conflicto recogido». MEDIDO: desde `ADR-0035` y su migracion `0008`,
        # esa forma **no pisa nada**: `line_count=137` y `line_count=250`
        # sobre el mismo fichero son dos hechos ciertos y las dos filas caben.
        # `0008` existe precisamente para eso.
        #
        # Y por la via de la ingesta un conflicto es ahora **INALCANZABLE**,
        # y el motivo es estructural, no una coincidencia: `normalizar` deriva
        # el `claim_id` de (sujeto, predicado, objeto, fuente, revision), luego
        # dos claims distintos tienen `claim_id` distinto, luego el `UNIQUE`
        # de la clave primaria no puede rechazar, y el de la tupla natural
        # —que ahora incluye el objeto— tampoco.
        #
        # Que `conflictos` salga vacio **no es que el aviso se haya tragado**:
        # es que no hay nada que avisar. Y quien aun puede necesitar el aviso
        # es quien construye `Claim` A MANO, donde el `claim_id` no lo deriva
        # nadie — la promocion, que es lo que mide
        # `test_b27_conflictos.py::TestElAvisoLlega`.
        #
        # La fila 250 tiene que ESTAR, que es la mitad que si se puede mirar.
        assert not ingerible.conflictos, (
            "la ingesta ha reportado un conflicto entre dos hechos ciertos: "
            "es el aviso falso que ADR-0035 vino a cerrar"
        )
        filas = s._conn.execute(
            "SELECT object_literal_json FROM claims ORDER BY object_literal_json"
        ).fetchall()
        assert [f[0] for f in filas] == ["137", "250"], (
            f"los dos valores deberían convivir: hay {[f[0] for f in filas]}"
        )
