"""B35 — de la capability al store: los tres pasos que no existian.

MEDIDO antes de escribir una linea (`scripts/measure_b35_vertical.py`):

    RONDA 1  CapabilityRegistry(...) en src/ : 0   (26 en tests/)
             *Capability instanciadas en src/ : 0 de 3
    RONDA 2  `envelope_a_payload`: 2 definiciones, 1 nombre, contratos distintos
    RONDA 3  el inverso no existe en src/; hay 2 copias a mano en tests/
             que YA DIVERGEN
    RONDA 4  AST sobre los imports de `cli/`: no llega a ninguna

Y un cuarto defecto que solo se vio al ejecutar la puerta de verdad, y que no
era de B35 sino de B31: el aviso de conflicto de `record_claim` seguia
comparando con la tupla ANTERIOR a la migracion `0008`.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.core.errors import EnvelopeInvalido
from skillgraph.knowledge.assembly import CAPACIDADES_ENSAMBLADAS, registro_de_conocimiento
from skillgraph.knowledge.code_analysis import CODE_ANALYSIS, CodeAnalysisCapability
from skillgraph.knowledge.graph import entity_ref
from skillgraph.knowledge.knowledge_query import KNOWLEDGE_QUERY
from skillgraph.knowledge.observation import (
    METODO_EXTERNO,
    Observation,
    ObservationEnvelope,
    envelope_a_payload,
    envelope_de_payload,
)
from skillgraph.platform.ports.capabilities import CapabilityRequest, CapabilitySpec

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src" / "skillgraph"

CODIGO = "import os\nimport sys\n\ndef saluda():\n    return 1\n"


def _env(observaciones: tuple[Observation, ...]) -> ObservationEnvelope:
    return ObservationEnvelope(
        producer=CapabilitySpec(type_name="sg.prueba", summary="prueba"),
        adapter="Prueba",
        source_id="s:1",
        subject="file:a.py",
        observed_at="2026-10-07T00:00:00Z",
        revision="r1",
        observations=observaciones,
        kind="local_file",
    )


# ---------------------------------------------------------------------------
# P1 — el contrato ida y vuelta
# ---------------------------------------------------------------------------


class TestElContratoTieneLasDosDirecciones:
    @pytest.mark.parametrize(
        "observacion",
        [
            Observation(predicate="line_count", object_literal=8),
            Observation(predicate="line_count", object_literal=0),
            Observation(predicate="file_exists", object_literal=False),
            Observation(predicate="line_count", object_literal=3, extraction_method=None),
            Observation(predicate="line_count", object_literal=3, extraction_method="regex_def"),
            Observation(
                predicate="imports_module",
                object_entity=entity_ref("module:os"),
                extraction_method="regex_import",
            ),
        ],
        ids=["int", "cero", "falso", "metodo-None", "metodo-propio", "entidad"],
    )
    def test_la_ida_y_la_vuelta_es_identidad(self, observacion: Observation) -> None:
        """`envelope_de_payload(envelope_a_payload(env)) == env`, y no «casi».

        Los seis casos estan porque cada uno ROMPE una forma de escribir el
        inverso que parece correcta:

        - `0` y `False`: un `or` los convierte en el valor por defecto, y el
          round-trip devuelve algo que no es lo que se puso.
        - `extraction_method=None`: es lo mismo que `METODO_EXTERNO` y no es
          la misma cadena, luego `==` falla aunque la affirmacion sea igual.
        - `object_entity`: `EntityRef` es un dataclass, no un `NewType` sobre
          `str`, luego `str()` de el devuelve su `repr`.
        """
        env = _env((observacion,))
        assert envelope_de_payload(envelope_a_payload(env)) == env

    def test_una_clave_ausente_no_es_un_None(self) -> None:
        """La AUSENCIA de la clave y un `None` EN la clave no son lo mismo.

        MEDIDO: con `dato.get("extraction_method") or METODO_EXTERNO` los dos
        casos colapsaban, y con `.get(k, POR_DEFECTO)` tambien, porque `or`
        trata `None` como falso. `dict.get(k, d)` devuelve `d` solo si la
        clave NO ESTA, que es exactamente la distinction que hace falta.

        El primero es un adaptador viejo, que no conoce el campo de B31. El
        segundo es el valor por defecto, que se conserva.
        """
        payload = envelope_a_payload(_env((Observation(predicate="line_count", object_literal=1),)))
        payload["observations"] = [
            {k: v for k, v in list(payload["observations"][0].items()) if k != "extraction_method"}
        ]
        env = envelope_de_payload(payload)
        assert env.observations[0].extraction_method == METODO_EXTERNO

        con_none = envelope_a_payload(
            _env((Observation(predicate="line_count", object_literal=1, extraction_method=None),))
        )
        assert envelope_de_payload(con_none).observations[0].extraction_method is None

    def test_el_producer_no_pierde_la_version(self) -> None:
        """MEDIDO: la primera version del serializador tiraba `version`.

        `CapabilitySpec` tiene tres campos y el `UNIQUE` de `CapabilityRegistry`
        es `(type_name, version)`. Un payload sin `version` permite registrar
        dos adapters que se solapan sin que nada lo diga.

        **Y EL SPEC DE ESTE TEST ES DELIBERADAMENTE DISTINTO DEL DE POR
        DEFECTO.** MEDIDO: con el `CapabilitySpec` de siempre, cuya `version` ya
        es `"v1"`, la sonda de mutacion que la fija a mano a `"v1"` daba
        **INOCUA** —el arbol seguia en verde— porque `"v1"` ES el valor por
        defecto. Se estaba midiendo un cambio que no es un cambio, que es la
        peor forma de sonda: parece que vigila y no vigila.

        Con un `version` que NO es la de por defecto, la ida y la vuelta
        tienen que conservarla, y cualquier cambio se ve.
        """
        env = ObservationEnvelope(
            producer=CapabilitySpec(type_name="sg.prueba", version="7.3", summary="prueba"),
            adapter="Prueba",
            source_id="s:1",
            subject="file:a.py",
            observed_at="2026-10-07T00:00:00Z",
            revision="r1",
            observations=(Observation(predicate="line_count", object_literal=1),),
            kind="local_file",
        )
        payload = envelope_a_payload(env)
        assert payload["producer"]["version"] == "7.3"
        assert envelope_de_payload(payload).producer == env.producer
        assert envelope_de_payload(payload).producer.version == "7.3"

    def test_un_payload_mal_formado_es_error_de_dominio(self) -> None:
        """El error sale de aqui, con su `code`, y no de un `TypeError`."""
        for roto in (
            "no soy un dict",
            {},
            {"producer": "no soy un dict de spec"},
        ):
            with pytest.raises(EnvelopeInvalido):
                envelope_de_payload(roto)  # type: ignore[arg-type]

    def test_named_arguments_deben_traer_lo_que_dicen(self) -> None:
        """`observations` que no es una lista de dicts es un error con indice."""
        payload = envelope_a_payload(_env((Observation(predicate="line_count", object_literal=1),)))
        payload["observations"] = ["no soy un dict"]
        with pytest.raises(EnvelopeInvalido) as exc:
            envelope_de_payload(payload)
        assert "observations[0]" in str(exc.value)


# ---------------------------------------------------------------------------
# P2 — un solo contrato
# ---------------------------------------------------------------------------


class TestElAvisoHablaDelClaimQueSeReEscribe:
    def test_el_valor_previo_es_el_suyo_y_no_el_de_otro(self, tmp_path: Path) -> None:
        """MEDIDO: la consulta previa era AMBIGUA, y su valor se colaba.

        Un fichero que importa dos modulos tiene DOS filas que encajan en la
        tupla (sujeto, predicado, fuente, revision). Con la consulta anterior
        a `0008` —que no llevaba el objeto— `fetchone()` devolvía una
        cualquiera, luego el aviso podia decir «habia 'os'» cuando lo que se
        reescribia era `'sys'`.

        Y esto **no lo media el booleano**: con `insertado` en la formula,
        `conflicto` ya era `False` igual. Lo que la consulta rota estropeaba
        es el CONTENIDO del aviso, que es justo lo que B27 pidio al principio
        y lo que `TestElOverwriteAvisa::test_el_aviso_dice_que_se_afirmo`
        ata para un caso. MEDIDO, y por eso esta sonda apuntaba al sitio
        equivocado dos veces: la primera a la comparacion y la segunda a la
        consulta, y las dos daba INOCUA.
        """
        from skillgraph.knowledge.graph import Claim, Entity, Source, source_id
        from skillgraph.platform.storage import Storage

        s = Storage(tmp_path / "x.sqlite")
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

        def _import(claim_id: str, modulo: str) -> Claim:
            return Claim(
                claim_id=claim_id,
                subject_entity_id="file:a.py",
                predicate="imports_module",
                object_literal=modulo,
                source_id=source_id("local:a.py"),
                checked_at_revision="r1",
            )

        for cid, modulo in (("c-os", "os"), ("c-sys", "sys")):
            s.record_claim(tenant_id="t", project_id="p", claim=_import(cid, modulo))

        # Se reescribe 'sys'. El aviso, si hay algo que decir, tiene que decir
        # lo que tenia 'sys' — y no 'os', que esta ahi al lado.
        r = s.record_claim(tenant_id="t", project_id="p", claim=_import("c-sys", "sys"))
        s.close()

        assert r.conflicto is False, "reingerir lo mismo no es conflicto"
        assert r.valor_previo == "sys", (
            f"el aviso habla de otro claim: valor_previo={r.valor_previo!r}, "
            "y quien lo recibe no puede saber si lo que se solapa es el suyo"
        )


class TestElContratoEsUno:
    def test_no_hay_dos_serializadores(self) -> None:
        """UN contrato, no dos homonimos.

        MEDIDO antes de B35: `code_analysis.envelope_a_payload` anadia
        `vocabulario` y devolvia `observations` como `list`;
        `telemetry_query.envelope_a_payload` era `asdict` a pelo y la
        devolvia como `tuple`. Dos funciones con el mismo nombre y contratos
        distintos obligan a quien importa a saber de cual trae.

        **Y NO ES UNA LISTA ESCRITA A MANO.** El conjunto sale del arbol: se
        buscan las DEFINICIONES de primer nivel en todo `src/`, no las
        llamadas. Una lista de «los sitios que deben delegar» es la misma
        trampa que `DIRECTORIOS_NO_RECETA` de WI-99.
        """
        definiciones: list[tuple[str, int]] = []
        for f in sorted(SRC.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            arbol = ast.parse(f.read_text(encoding="utf-8"))
            for nodo in arbol.body:
                if isinstance(nodo, ast.FunctionDef) and nodo.name == "envelope_a_payload":
                    definiciones.append((str(f.relative_to(RAIZ)), nodo.lineno))

        # Se permite UNA: la canonica de `observation.py`. Los dos modulos de
        # capability la IMPORTAN y la reexportan, que no es definirla.
        canonicas = [d for d in definiciones if d[0].endswith("knowledge/observation.py")]
        assert canonicas == [("src/skillgraph/knowledge/observation.py", definiciones[0][1])], (
            f"la definicion canonica de `envelope_a_payload` deberia estar solo en "
            f"`observation.py`, y hay {definiciones}"
        )

    def test_las_dos_capabilities_usan_la_misma(self) -> None:
        """Ejecutadas sobre el MISMO envelope, dan el MISMO dict."""
        from skillgraph.knowledge.code_analysis import envelope_a_payload as de_codigo
        from skillgraph.knowledge.telemetry_query import envelope_a_payload as de_runtime

        env = _env((Observation(predicate="line_count", object_literal=3),))
        assert de_codigo(env) == de_runtime(env)


# ---------------------------------------------------------------------------
# P3 — el ensamblado
# ---------------------------------------------------------------------------


class TestElDespliegueExiste:
    def test_ensambla_lo_que_se_puede_ensamblar(self) -> None:
        registro = registro_de_conocimiento(
            object(), tenant_id="t", project_id="p", source_id="s:1", revision="r1"
        )
        assert registro.types == (CODE_ANALYSIS, KNOWLEDGE_QUERY)
        assert registro.supports(CODE_ANALYSIS)
        assert registro.types == CAPACIDADES_ENSAMBLADAS

    def test_no_ensambla_lo_que_no_tiene_lector(self) -> None:
        """MEDIDO: `LectorTelemetria` es un `Protocol` con CERO implementaciones
        en `src/`. Ensamblar `sg.telemetry.query` seria inventar el lector, y una
        capability montada con un lector de carton daria respuestas sobre un
        runtime que no ha visto nunca.

        Por eso `CAPACIDADES_ENSAMBLADAS` tiene DOS entradas y no tres, y por
        eso esta asercion mira la constante y no una copia.
        """
        assert "sg.telemetry.query" not in CAPACIDADES_ENSAMBLADAS
        registro = registro_de_conocimiento(
            object(), tenant_id="t", project_id="p", source_id="s:1", revision="r1"
        )
        assert not registro.supports("sg.telemetry.query")

    @pytest.mark.parametrize("campo", ["tenant_id", "project_id", "source_id", "revision"])
    def test_un_identificador_vacio_no_se_traga(self, campo: str) -> None:
        """Cada uno de estos entra en un hash firmado o en un `UNIQUE`."""
        from skillgraph.core.errors import ValidationError

        kwargs = {"tenant_id": "t", "project_id": "p", "source_id": "s:1", "revision": "r1"}
        kwargs[campo] = "   "
        with pytest.raises(ValidationError) as exc:
            registro_de_conocimiento(object(), **kwargs)  # type: ignore[arg-type]
        assert campo in str(exc.value)

    def test_dos_despliegues_iguales_declaran_lo_mismo(self) -> None:
        """Es un VALOR, no un singleton. `AGENTS.md` 1.4.

        **Y LA IGUALDAD QUE SE MIDE ES `types`, NO EL REGISTRO ENTERO.**
        Las capabilities no son dataclasses, luego dos instancias construidas
        por separado no son `==`, y el `CapabilityRegistry` las contiene por
        valor luego su `==` compara identidades. MEDIDO: asertarlo daba falso.

        Lo que si es propiedad del despliegue —y es la que importa— es que dos
        despliegues con los MISMOS parametros **saben resolver lo mismo**. Si
        eso variara, un plan que declara `sg.code.analysis` dejaria de
        funcionar en un despliegue identico al de al lado.
        """
        a = registro_de_conocimiento(
            object(), tenant_id="t", project_id="p", source_id="s", revision="r"
        )
        b = registro_de_conocimiento(
            object(), tenant_id="t", project_id="p", source_id="s", revision="r"
        )
        assert a.types == b.types == (CODE_ANALYSIS, KNOWLEDGE_QUERY)


# ---------------------------------------------------------------------------
# P4 — la puerta, de verdad
# ---------------------------------------------------------------------------


class TestLaPuertaExiste:
    def test_la_cli_importa_lo_que_dice_importar(self) -> None:
        """**POR QUE AST Y NO TEXTO, Y QUE CUESTO LA PRIMERA VEZ.**

        La primera version buscaba el nombre con `in` sobre el texto y dio
        `KnowledgeQueryCapability : SI`. Falso: la unica mencion esta en un
        docstring que lo describe en pasado. Es la cuarta vez que sale este
        defecto en el repo (B15, WI-92, B34 con su sonda M10, y aqui), y por
        eso esto mira `ast.ImportFrom`, que es lo que ata un modulo a otro.
        """
        importados: set[str] = set()
        for f in sorted((SRC / "cli").rglob("*.py")):
            arbol = ast.parse(f.read_text(encoding="utf-8"))
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.ImportFrom) and nodo.module:
                    importados.add(nodo.module)
                    importados.update(a.name for a in nodo.names)
        assert "skillgraph.knowledge.code_analysis" in importados
        assert "skillgraph.knowledge.assembly" in importados

    def test_la_vertical_entera_por_la_cli(self, tmp_path: Path) -> None:
        """SEIS PASOS QUE ANTES NO TENIAN PUERTA, con un fichero de verdad.

        Antes de B35, lanzar `sg.code.analysis` exigia escribir Python: leer el
        fichero, construir la `Source`, montar la capability, invocar,
        deserializar el envelope e ingerirlo. Aqui se hacen los seis con un
        subcomando, y lo que se comprueba no es la salida sino **la tabla**.
        """
        proyecto = tmp_path / "p"
        proyecto.mkdir()
        (proyecto / "app.py").write_text(CODIGO, encoding="utf-8")
        datos = tmp_path / "data"

        def _sg(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "skillgraph", "--data-root", str(datos), *args],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                check=True,
            )

        _sg("init")
        _sg("project", "create", "demo")

        primera = _sg("knowledge", "ingest-code", "demo", str(proyecto / "app.py"))
        assert "afirmacion(es) escritas" in primera.stdout

        import sqlite3

        db = datos / "tenants" / "default" / "projects" / "demo" / "project.sqlite"
        with sqlite3.connect(db) as con:
            filas = con.execute(
                "SELECT predicate, object_literal_json FROM claims ORDER BY predicate, claim_id"
            ).fetchall()
        predicados = {p for p, _ in filas}
        assert {
            "line_count",
            "function_count",
            "file_exists",
            "imports_module",
            "defines_symbol",
        } <= predicados

        # Y la idempotencia: la segunda pasada no crece y no avisa de nada.
        segunda = _sg("knowledge", "ingest-code", "demo", str(proyecto / "app.py"))
        # **B35, AL CERTIFICAR: ESTA ASERCION DEJO DE PODER FALLAR.** El print
        # que imprimia la palabra «conflicto» se borro porque era codigo muerto
        # —`ObservationIngesta.conflictos` no tiene productor—, luego la palabra
        # ya no puede aparecer en ninguna salida y la asercion pasa siempre.
        # Una asercion que no puede fallar esta DECORADA. Se queda por
        # documentar la intension; lo que puede fallar es el guard de AST de
        # abajo, `test_la_cli_no_vuelve_a_imprimir_un_aviso_imposible`.
        assert "conflicto" not in segunda.stdout
        with sqlite3.connect(db) as con:
            assert con.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == len(filas)

    def test_la_cli_no_vuelve_a_imprimir_un_aviso_imposible(self) -> None:
        """**EL QUE SI PUEDE FALLAR, MEDIDO SOBRE EL AST DEL MODULO REAL.**

        El aviso que la CLI imprimia salia de `ingesta.conflictos`, y ese campo
        no lo produce nadie: `normalizar` deriva el `claim_id` de (sujeto,
        predicado, objeto, fuente, revision), luego dos claims distintos tienen
        id distinto y el `UNIQUE` no puede rechazar ninguno.

        Reintroducir el aviso no rompe una asercion de texto —la palabra volveria
        a salir y el `assert "conflicto" not in ...` la cazaria— pero si nadie
        escribe esa asercion, el modulo volveria a mentir con la misma
        tranquila. El guard mide la MENTIRA, no su sintomas.
        """
        import ast
        import inspect

        from skillgraph.cli.commands import knowledge as modulo

        arbol = ast.parse(inspect.getsource(modulo))
        usa_el_campo = any(
            isinstance(nodo, ast.Attribute) and nodo.attr == "conflictos"
            for nodo in ast.walk(arbol)
        )
        assert not usa_el_campo, (
            "la CLI vuelve a leer ingesta.conflictos: ese campo no lo produce "
            "nadie y lo que volveria a imprimir es un aviso que no puede "
            "existir"
        )

    def test_un_fichero_con_dos_imports_no_avisa_de_un_conflicto_falso(
        self, tmp_path: Path
    ) -> None:
        """EL DEFECTO DE B31, VISTO POR LA PUERTA.

        `imports_module='os'` y `imports_module='sys'` sobre el mismo fichero
        son **dos hechos ciertos**, y `ADR-0035` (migracion `0008`) vino a
        permitir que las dos filas vivan juntas.

        MEDIDO antes del arreglo: la deteccion de conflicto comparaba contra
        una consulta previa que seguia con la tupla ANTERIOR a `0008` —sin el
        objeto—, luego `imports_module='sys'` salia como conflicto con `'os'`.
        Las filas estaban bien; **el aviso mentia**.

        Y por eso B31 no lo vio: su test miraba FILAS, y las filas estaban
        bien. Es la quinta vez que sale este defecto de fondo —un guard que
        mide la mitad de una propiedad y da verde porque esa mitad esta
        bien—, y por eso este test mide el AVISO y no las filas.
        """
        proyecto = tmp_path / "p"
        proyecto.mkdir()
        (proyecto / "app.py").write_text(CODIGO, encoding="utf-8")
        datos = tmp_path / "data"

        def _sg(*args: str) -> str:
            return subprocess.run(
                [sys.executable, "-m", "skillgraph", "--data-root", str(datos), *args],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                check=True,
            ).stdout

        _sg("init")
        _sg("project", "create", "demo")
        salida = _sg("knowledge", "ingest-code", "demo", str(proyecto / "app.py"))

        assert "imports_module = 'os'" in salida
        assert "imports_module = 'sys'" in salida
        assert "conflicto" not in salida, (
            "dos hechos ciertos se han reportado como conflicto: es el aviso "
            "falso que la migracion 0008 vino a cerrar"
        )
        # MEDIDO al certificar: con el print borrado, esta asercion ya no puede
        # fallar. Lo que la sustituye como guarda real es
        # `test_la_cli_no_vuelve_a_imprimir_un_aviso_imposible`.

    def test_el_vocabulario_no_contamina_el_envelope(self) -> None:
        """`vocabulario` estaba DENTRO del dict que dice ser un envelope.

        MEDIDO: era una de las dos diferencias entre los dos serializadores
        con el mismo nombre. Un campo que no es del envelope, dentro del
        envelope, es indistinguible de un campo de verdad para quien lo lee.

        Va al nivel del `payload`, que es donde puede vivir algo que describe
        ESTA capability y no el contrato.
        """
        cap = CodeAnalysisCapability(source_id="s:1", revision="r1")
        resultado = cap.invoke(
            CapabilityRequest(
                spec=cap.spec,
                subject="app.py",
                arguments={
                    "path": "app.py",
                    "content": CODIGO,
                    "observed_at": "2026-10-07T00:00:00Z",
                },
            )
        )
        assert "vocabulario" in resultado.payload
        assert "vocabulario" not in resultado.payload["envelope"]
        # Y lo que el envelope SI declara, el deserializador lo acepta.
        assert envelope_de_payload(resultado.payload["envelope"]).kind == "local_file"


# ---------------------------------------------------------------------------
# P5 — lo que B35 NO hace
# ---------------------------------------------------------------------------


class TestLoQueNoSeToca:
    def test_la_politica_de_capabilities_none_no_cambia(self) -> None:
        """**B35 LE DA QUIEN DESPLIEGA, NO CAMBIA QUE SE EXIJA.**

        `runcontroller.py:148` declara la costura con default `None` y su
        motivo: la exigencia la PIDE quien despliega. Que exista un
        ensamblado no significa que un plan deba declarar capabilities, y
        exigirlo siempre habria roto los sitios que construyen
        `node.capabilities`.
        """
        import inspect

        from skillgraph.runtime.runcontroller import RunController

        firma = inspect.signature(RunController.__init__)
        assert firma.parameters["capabilities"].default is None
