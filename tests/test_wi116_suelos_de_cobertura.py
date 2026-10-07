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
faltaban eran las dos lineas de la rama de CONFLICTO de la ingesta.

**Y B35 VUELVIO A DEJARLO EN 84 %, Y POR ESO ESTA OTRA VEZ AQUI.**

Se tapo la rama con un test que afirmaba lo contrario —«la ingesta no
recoge el conflicto»—, que era verdad y ademas hacia subir el suelo por el
motivo equivocado. MEDIDO al certify B35: la rama **no se puede ejecutar**, ni
siquiera con un test nuevo, porque `ingerir` es la unica funcion publica del
modulo y su unico camino es `normalizar(env)`. Fabricar un test que la
ejecute habria exigido monkeypatchear el normalizador, que es poner un
peine en la cobertura.

Aqui esta el segundo motivo por el que este fichero dice que no baja
suelos: **tambien hay que poder QUITAR codigo**. Un suelo que obliga a
fabricar una prueba para cubrir una rama inalcanzable no esta midiendo el
codigo que se ejecuta: esta obligando a que quede escrito. La rama se borro
—con un guard por AST que avise si vuelve— y el modulo subio de 84 % a 100 %.

# LO QUE ESTE FICHERO NO HACE

No baja ningun suelo. `SUELOS_ESPECIALES` y `EXCEPCIONES` siguen exactamente
como estaban: tocar un suelo para que un gate de en verde es la forma de
guarda que este repo lleva cinco bloques cerrando. Aqui la unica palanca es
**escribir los tests que faltan** y, cuando no faltan y no se pueden
escribir, **borrar lo que no se ejecuta**.
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


#: Los valores que `git status --porcelain` puede dar en cada columna.
#: Sacados de la especificacion del comando, no de los ejemplos que Writerra.
COLUMNAS_INDICE = frozenset(" MADRCU?!")
COLUMNAS_ARBOL = frozenset(" MDARCUT?")


def _sucio_por_columna(salida: str) -> tuple[str, ...]:
    """Las lineas de `git status --porcelain` que un harness PODRIA destruir.

    **POR QUE ESTA FUNCION EXISTE, Y POR QUE NO ESTA DENTRO DEL TEST.**

    `git status --porcelain` imprime `XY` donde X es el indice y Y el arbol de
    trabajo, y `git checkout -- <ruta>` restaura **del indice**. Luego lo unico
    que ese comando puede perder es lo que NO esta en el indice, que es
    exactamente la columna Y.

    MEDIDO en repos aislados, con `scripts/measure_b36_commit_gate.py`:

        cambio STAGEADO    -> 'M  src/a.py'    sobrevive al checkout
        cambio SIN stagear -> ' M src/a.py'    DESTRUIDO
        fichero nuevo      -> '?? src/x.py'    no lo toca checkout, pero si clean

    **LO QUE ESTO CORRIGE, MEDIDO EN VIVO.** La version anterior exigia la
    salida VACIA, luego un cambio stageado la hacia fallar. El hook de
    pre-commit corre pytest sobre lo STAGEADO, luego todo commit que toca
    `src/` o `scripts/` se ponia rojo. Capturado de verdad: el hook rechazo
    `5f3a739`, que era un commit correcto, con tres `M ` en la columna del
    indice, y la salida fue `HOOK_SKIP_TESTS=1`.

    Y el bypass apaga, MEDIDO en `scripts/hooks/pre-commit`, la UNICA
    comprobacion de que lo stageado sigue pasando: `ruff check` y `ruff format
    --check` corren siempre.

    La funcion es pura a proposito: la decision se prueba con las cuatro
    formas reales de `porcelain`, y no depender del estado del arbol en el
    momento del run. Un guard que solo se puede probar cuando el arbol esta
    sucio es un guard que casi nunca se prueba.
    """
    sucio: list[str] = []
    for linea in salida.splitlines():
        if not linea.strip():
            continue
        # `XY` y luego un espacio y la ruta. Con nombres raros git entrecomilla,
        # y lo que decide es la segunda columna, no el camino.
        estado = linea[:2]
        if len(estado) < 2:
            continue
        # **MEDIDO AL ESCRIBIRLO, Y MI PRIMERA VERSION ACUSABA DE MAS.** Sin
        # esta comprobacion, la linea `ruta sin estado` —que no es porcelain—
        # entra por `estado[1] == 'u'`, que no es ni espacio ni interrogante,
        # y el guard la cuenta como trabajo sin stagear. Un guard que acusa a
        # una linea que no sabe leer es un guard que miente, y miente en la
        # direccion que hace ruido. Los dos conjuntos salen de la
        # especificacion de `git status --porcelain`, no de una lista de
        # ejemplos que yo haya querido.
        if estado[0] not in COLUMNAS_INDICE or estado[1] not in COLUMNAS_ARBOL:
            continue
        if estado[1] != " ":
            sucio.append(linea)
    return tuple(sucio)


class TestElHarnessNoBorraTrabajo:
    """**UN RECORDATORIO QUE SE PAGA CON UN TEST, Y QUE MEDIA LO QUE DICE.**

    Quince de los veintisiete `scripts/mutate_*.py` restauraban con
    `git checkout --`, que devuelve el arbol DEL INDICE. Eso borro la
    migracion `0005` de R1.F con sus trece tests a mitad de certificacion, y
    se recupero de un volcado accidental.

    **Y MEDIDO AL ABRIR B36: el antipatron SIGUE VIVO.** Siete harnesses siguen
    con `_restaura()` -> `git checkout --` y `cwd=RAIZ`, y este test no lo
    hubiera visto nunca, porque solo miraba el estado del arbol y no el arbol
    del codigo. De ahi la clase de al lado.

    Un guard que se pone verde en un arbol vacio es peor que no tener guard;
    uno que se pone rojo en un commit correcto es peor todavia, porque su
    salida es desactivar el gate que lo contiene.
    """

    def test_el_arbol_no_tiene_nada_SIN_STAGEAR_entre_scripts_y_src(self) -> None:
        """Lo que NO esta en el indice, que es lo unico que un checkout pierde."""
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
        sucio = _sucio_por_columna(proc.stdout)
        assert not sucio, (
            "hay cambios SIN STAGEAR en src/ o scripts/:\n  "
            + "\n  ".join(sucio)
            + "\n\nUn harness con `git checkout --` debajo se los llevaria en "
            "cuanto corra: restaura del indice. Commitea o stagea antes de "
            "certificar.\n\nLo que YA esta stageado NO se lista, y es a "
            "proposito: es lo que sobrevive, y es justo lo que hace un commit."
        )


class TestLaDecisionDelGuardEsMedible:
    """**POR QUE LA DECISION ESTA FUERA DEL TEST Y SE PROBEA A SEPARTE.**

    El guard mira el arbol de trabajo real, y en una certificacion el arbol esta
    limpio: luego la condicion que decide nunca se ejecuta. Un guard que solo
    puede fallar cuando el arbol esta sucio no se ha probado nunca, y este es
    el sitio donde se prueba.

    Las cuatro formas de abajo son MEDIDAS, no inventadas: salen de crear un
    repo, tocarlo y ejecutar `git status --porcelain` en cada estado.
    """

    def test_un_cambio_STAGEADO_no_culpa_al_operador(self) -> None:
        """Es la forma de un commit correcto, y el hook la rechazaba."""
        assert _sucio_por_columna("M  src/skillgraph/cli/parser.py") == ()

    def test_un_cambio_SIN_STAGEAR_si_culpa(self) -> None:
        """Es la unica forma que un `git checkout --` puede perder."""
        assert _sucio_por_columna(" M src/skillgraph/cli/parser.py") != ()

    def test_un_fichero_NUEVO_tambien_culpa(self) -> None:
        """`??` no lo destruye `checkout --`, pero si `git clean -fd`."""
        assert _sucio_por_columna("?? scripts/nuevo.py") != ()

    def test_stageado_Y_sin_stagear_a_la_vez_culpa(self) -> None:
        """`MM`: la parte del worktree sigue sin estar a salvo."""
        assert _sucio_por_columna("MM src/skillgraph/cli/parser.py") != ()

    def test_el_arbol_LIMPIO_no_culpa(self) -> None:
        assert _sucio_por_columna("") == ()

    def test_una_linea_QUE_NO_entiende_no_inventa_cargos(self) -> None:
        """Un guard que acusa a una linea que no sabe leer es un guard que miente.

        No es un caso teorico: `git status --porcelain` imprime una linea por
        entrada, y un nombre de fichero con salto de linea produce una forma
        que no es `XY`. Acusar de lo que no se ha leido es peor que callar.
        """
        assert _sucio_por_columna("?\n") == ()
        assert _sucio_por_columna("   \n") == ()
        assert _sucio_por_columna("ruta sin estado\n") == ()


class TestNingunInstrumentoPuedeBorrarTrabajo:
    """**EL GUARD QUE FALTA, Y QUE SE DERIVA DEL ARBOL.**

    El test de al lado vigila el ESTADO. Este vigila la CAPACIDAD: que ningun
    instrumento pueda ejecutar un comando que devuelve ficheros a otro estado.

    **POR QUE ESTE Y NO UNO SOLO.** MEDIDO al abrir B36: siete
    `scripts/mutate_*.py` siguen con

        subprocess.run(["git", "checkout", "--", ...], cwd=RAIZ, check=True)

    que es exactamente el antipatron. El guard de estado no lo veria nunca
    porque solo mira el arbol, no el codigo que lo puede romper.

    **EL CONJUNTO SE DERIVA, NO SE ESCRIBE.** Sale de `scripts/`, que es donde
    viven los instrumentos; la lista de ficheros seria una fuente de verdad mas
    —la trampa de WI-99— y ademas dejaria fuera cualquier harness nuevo.

    **Y EL CONTRA SALTO, SIN EL CUAL ESTA GUARDA ES VERDE EN EL VACIO:** el
    derivado tiene que traer AL MENOS veinte modulos. Una derivacion que
    devolviera la lista vacia daria verde con los siete problemas puestos.
    """

    MINIMO_INSTRUMENTOS = 20
    VERBOS = frozenset({"checkout", "restore", "reset", "clean", "stash"})
    BINARIOS = frozenset({"git"})

    @staticmethod
    def _instrumentos() -> list[Path]:
        raiz = Path(__file__).resolve().parent.parent
        return sorted(
            p
            for p in (raiz / "scripts").rglob("*.py")
            if not any(x in {"__pycache__", ".venv", "node_modules"} for x in p.parts)
        )

    @classmethod
    def _destructivos(cls, fichero: Path) -> list[str]:
        """Llamadas `git <verbo>`, por AST y por POSICION del argumento.

        **MEDIDO, Y LA PRIMERA VERSION DE ESTE RASTREO MENTIA DOS VECES.**
        (1) Buscaba la palabra suelta en cualquier literal y contaba
        `print("... git checkout ...")` —que es prosa. (2) Peor: exigia que el
        primer argumento fuera una cadena, luego
        `subprocess.run(["git", "checkout", ...])` —una lista— nunca se miraba,
        y los siete problemas reales quedaron en cero.

        Es la quinta vez que sale este defecto en el repo. Aqui se exige la
        FORMA: una lista de argumentos donde el binario va seguido del verbo.
        """
        import ast

        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        hallados: list[str] = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call) or not nodo.args:
                continue
            lista = nodo.args[0]
            if not isinstance(lista, (ast.List, ast.Tuple)):
                continue
            elementos = [
                e.value
                for e in lista.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if not (cls.BINARIOS & set(elementos)):
                continue
            for indice, palabra in enumerate(elementos):
                if palabra in cls.VERBOS and any(b in cls.BINARIOS for b in elementos[:indice]):
                    hallados.append(
                        f"{fichero.name}:{nodo.lineno}  {' '.join(elementos[: indice + 1])}"
                    )
                    break
        return hallados

    def test_el_derivado_NO_sale_vacio(self) -> None:
        """El contrasalto: sin esto, una derivacion rota daria verde."""
        assert len(self._instrumentos()) >= self.MINIMO_INSTRUMENTOS, (
            f"el derivado trae {len(self._instrumentos())} instrumentos y se "
            f"esperan al menos {self.MINIMO_INSTRUMENTOS}: si baja, el conjunto "
            "se esta deixando de medir y este guard pasaria en verde sin mirar"
        )

    def test_ningun_instrumento_llama_a_un_git_DESTRUCTIVO(self) -> None:
        problemas: list[str] = []
        for fichero in self._instrumentos():
            problemas.extend(self._destructivos(fichero))
        assert not problemas, (
            "hay instrumentos que pueden devolver ficheros a otro estado:\n  "
            + "\n  ".join(problemas)
            + "\n\n`git checkout --` restaura DEL INDICE: se lleva el trabajo "
            "sin stagear. Se restaura ESCRIBIENDO el contenido original, como "
            "ya hacen nueve harnesses de este repo."
        )

    def test_la_prosa_NO_cuenta_como_llamada(self) -> None:
        """**EL DEFECTO DE FONDO DEL REPO, Y EL QUE MAS CARO SALE.**

         Si este guard buscara palabras en vez de formas, contaria su propio
         docstring y el del propio bloque, y se pondria en rojo solo. MEDIDO: la
         primera version del rastreo hacia exactamente eso, y devolvia 4
        strumentos de `scripts/` — todos prosa.

         El contraejemplo se construye aqui, con el fichero que HABLA del
         comando presente en el arbol: si el guard lo contara, este test falla.
        """
        raiz = Path(__file__).resolve().parent.parent
        propio = raiz / "scripts" / "measure_b36_commit_gate.py"
        assert propio.exists(), "el instrumento de medicion deberia estar en el arbol"
        texto = propio.read_text(encoding="utf-8")
        assert "git checkout --" in texto, (
            "el fichero deberia hablar del comando: si ya no lo hace, este "
            "contrajemplo ha dejado de probarlo"
        )
        assert self._destructivos(propio) == [], (
            "el guard se esta contando a si mismo: su prosa menciona el comando y no lo ejecuta"
        )


# ---------------------------------------------------------------------------
# observation_ingestion.py — la rama de CONFLICTO, que B35 dejo MUERTA
# ---------------------------------------------------------------------------


class TestLaIngestaNoPuedeRecogerElConflicto:
    """**EL CONTRASALTO, Y EL MOTIVO POR EL QUE HAY UN CONTRASALTO.**

    Este fichero nacio con una clase al lado que afirmaba lo contrario —«la
    ingesta recoge el conflicto»— porque el modulo `observation_ingestion.py`
    tenia esta rama:

        registro = storage.record_claim(...)
        if registro.conflicto:
            conflitos = (*conflictos, registro.claim_id)

    MEDIDO al certify B35: **esa rama no la ejecuta nadie**, y por eso el
    modulo mide 84 %, seis puntos por debajo del suelo de AGENTS 6.3.

    **Y NO ES QUE NO SE HAYA MEDIDO: es que no se puede.** `ingerir` es la
    UNICA funcion publica del modulo (`__all__ = ["ingerir"]`) y su unico
    camino es `normalizar(env)`, que deriva el `claim_id` de (sujeto,
    predicado, objeto, fuente, revision). Dos claims distintos tienen
    `claim_id` distinto, luego el `UNIQUE` de clave primaria no puede
    rechazar, y el de la tupla natural —que desde `ADR-0035` lleva el
    objeto— tampoco. MEDIDO en los siete estados de B35: por esta via
    `conflicto` es SIEMPRE `False`.

    **LO QUE NO SE PIERDE, MEDIDO EN LA OTRA DIRECCION:** detectar sigue
    pudiendo. `conflicts_for` ve la auto-contradiccion de una fuente —su
    docstring cita el caso de «2 filas de la MISMA fuente en revisiones
    consecutivas»— y B28 la resuelve por intencion. Lo que se deja de
    recoger es el aviso PUNTUAL en el instante de escribir, que es lo unico
    que la rama Hacia.

    Por eso el suelo no se baja: se borra la rama. Un suelo que hay que
    bajar para que un modulo con codigo muerto pase es un suelo que ya no
    dice nada.
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

    def test_dos_hechos_ciertos_conviven_Y_NO_se_reportan_como_conflicto(
        self, tmp_path: Path
    ) -> None:
        """La ingestion no inventa un aviso entre dos afirmaciones ciertas.

        `line_count=137` y `line_count=250` sobre el mismo fichero son dos
        hechos ciertos: el segundo es la MISMA afirmacion con el valor
        actualizado, y `ADR-0035` vino precisamente a que las dos filas
        convivan.
        """
        from skillgraph.knowledge.observation_ingestion import ingerir
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "x.sqlite")
        self._preparar(s)

        primera = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(137))
        segunda = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(250))

        assert not primera.conflictos, primera.conflictos
        assert not segunda.conflictos, segunda.conflictos
        filas = s._conn.execute(
            "SELECT object_literal_json FROM claims ORDER BY object_literal_json"
        ).fetchall()
        assert [f[0] for f in filas] == ["137", "250"], (
            f"los dos valores deberían convivir: hay {[f[0] for f in filas]}"
        )

    def test_los_claim_id_derivados_son_distintos_LA_RAZON_por_la_que_no_puede(
        self, tmp_path: Path
    ) -> None:
        """**La causa, medida y no narrada.**

        Si los dos `claim_id` fueran iguales, el `UNIQUE` de clave primaria
        podria rechazar y habria conflicto. Lo que afirma este bloque es que
        **no lo son**, y por eso la rama no tiene por que existir.

        Un guard que solo comprobara «`conflictos` sale vacio» pasaria igual
        con los ids iguales: el `UNIQUE` rechazaria, `insertado` seria falso
        y el valor coincidiria, luego `conflicto` seguiria siendo `False`.
        Este mide la razon.
        """
        from skillgraph.knowledge.observation_ingestion import ingerir
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "x.sqlite")
        self._preparar(s)
        primera = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(137))
        segunda = ingerir(s, tenant_id="t", project_id="p", env=self._envelope(250))

        assert len(primera.claim_ids) == len(segunda.claim_ids) == 1
        assert primera.claim_ids[0] != segunda.claim_ids[0], (
            "si los dos ids coincidieran, el UNIQUE de clave primaria podria "
            "rechazar y habria conflicto: es lo que haria alcanzable la rama"
        )

    def test_la_deteccion_sigue_viviendo_en_conflicts_for(self, tmp_path: Path) -> None:
        """**EL OTRO LADO, Y ES EL QUE IMPORTA.**

        Borrar la rama no puede costar una deteccion. Aqui se afirma que la
        auto-contradiccion de una MISMA fuente sigue siendo consultable, que
        es lo que hacia el aviso puntual que se ha dejado de recoger.
        """
        from skillgraph.knowledge.observation_ingestion import ingerir
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "x.sqlite")
        self._preparar(s)
        ingerir(s, tenant_id="t", project_id="p", env=self._envelope(137))
        ingerir(s, tenant_id="t", project_id="p", env=self._envelope(250))

        conflictos = s.conflicts_for(tenant_id="t", project_id="p", subject_entity_id="file:a.py")
        assert conflictos, "las dos filas tienen que seguir siendo visibles como conflicto"
        assert len(conflictos) == 1, [c.claim_ids for c in conflictos]

    def test_el_modulo_no_declara_una_capacidad_que_no_tiene(self) -> None:
        """**Y QUE NO VUELVA A DECIR QUE LA RECOGE.**

        Un modulo que vuelve a escribir `if registro.conflicto:` reintroduce
        la rama muerta y con ella los seis puntos de suelo. Se mide sobre el
        AST del modulo real, no sobre una copia de su texto.
        """
        import ast

        from skillgraph.knowledge import observation_ingestion

        arbol = ast.parse(Path(observation_ingestion.__file__).read_text(encoding="utf-8"))
        mira_conflicto = any(
            isinstance(nodo, ast.Attribute) and nodo.attr == "conflicto" for nodo in ast.walk(arbol)
        )
        assert not mira_conflicto, (
            "observation_ingestion.py vuelve a mirar registro.conflicto: la rama "
            "es inalcanzable desde normalizar y deja el modulo bajo su suelo"
        )
