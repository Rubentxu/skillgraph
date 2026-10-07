"""B30 — un contexto truncado DICE que se truncó.

**LO QUE MIDE ESTE FICHERO, Y POR QUÉ NO ES «UN CAMPO MÁS».** La fila de B30
decía: *«Traer el contexto es traerlo todo, o traerlo truncado sin decir qué
se cayó»*. La primera mitad es **falsa** y medida: `apply_budget` ya funciona y
ya es exacto —los obligatorios no se truncan y los opcionales entran en orden
hasta que uno no cabe—. Lo que no existe es el registro.

Y lo grave, que la fila no menciona, está en la otra mitad de la propiedad:

    should_skip_adapter(*, manifest) -> manifest.is_complete and all_fresh

Esa función decide **no invocar al Adapter** (UAT-EVO-11: la respuesta
determinista es completa, no hace falta un LLM), y **recibe solo el manifest**:
nunca ve el `Handoff` compilado, luego **no puede saber** que el presupuesto
cortó opcionales. El sistema puede **quedarse sin agente por el motivo de que la
respuesta es completa, cuando la respuesta se cortó**.

El propio módulo lo prohíbe en su documentación: `HandoffBlockedError` —
*«NUNCA debe presentarse como completado»*.

# LAS CINCO MEDIDAS DEL INSTRUMENTO, Y DONDE ESTAN AQUI

    P1  el presupuesto DECLARA lo que dejo fuera  -> TestElPresupuestoDeclara
    P2  el Handoff lo carga (y lo firma)          -> TestElHandoffLoCarga
    P3  lo omitido entra en el hash firmado       -> TestElHashFirmaLasOmisiones
    P4  un truncado LO DICE y uno holgado no      -> TestLoDiceYNoSeInventa  (CONTRA SALTO)
    P5  el SKIP no declara completo un truncado   -> TestElSkipNoSeEngaña

P4 y P5 son las dos que hacen que las otras midan algo. Un arreglo que
declarara `omitidos=()` siempre cumpliría P1, P2 y P3 sin medir nada; P4 lo
caza. Y un arreglo que solo declarara, sin cambiar quién decide, cumpliría P1 a
P4 y dejaría al sistema **quedándose sin agente sobre una respuesta cortada**;
P5 lo caza.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Escenario: un presupuesto que obliga a cortar
# ---------------------------------------------------------------------------

CHARS_OPCIONAL = 500
CHARS_OBLIGATORIO = 400
BUDGET_AJUSTADO = 1200
BUDGET_HOLGADO = 99_999


def _recurso(ns: str, chars: int) -> object:
    from skillgraph.knowledge.context_controller import CompiledResource

    return CompiledResource(
        resource_kind="claim",
        resource_namespace=f"claim:{ns}",
        resource_name=ns,
        body={"texto": "x" * chars},
    )


def approx_chars_de(recurso: object) -> int:
    """La medida que el presupuesto **tomó** de este recurso.

    Wrapper sobre `approx_chars` para que los tests puedan citar la medida
    sin abrir un import dentro de cada aserción.
    """
    from skillgraph.knowledge.context_controller import approx_chars

    return approx_chars(recurso.body)  # type: ignore[attr-defined]


def _candidatos() -> tuple[list[object], list[object]]:
    obligatorios = [_recurso(f"obl-{i}", CHARS_OBLIGATORIO) for i in (1, 2)]
    opcionales = [_recurso(f"opt-{i}", CHARS_OPCIONAL) for i in (1, 2, 3)]
    return obligatorios, opcionales


def _aplicar(budget: int = BUDGET_AJUSTADO) -> object:
    from skillgraph.knowledge.context_controller import apply_budget

    obligatorios, opcionales = _candidatos()
    return apply_budget(
        obligatory=obligatorios,
        optional=opcionales,
        budget_chars=budget,
        overflow_strategy="drop_optional",
    )


# ---------------------------------------------------------------------------
# P1 — el presupuesto DECLARA lo que dejó fuera
# ---------------------------------------------------------------------------


class TestElPresupuestoDeclara:
    def test_devuelve_lo_omitido(self) -> None:
        """**La fila, literalmente.** Tres opcionales de 500 en un hueco de 374."""
        resultado = _aplicar()
        incluidos = {r.resource_name for r in resultado.incluidos}
        omitidos = {o.name for o in resultado.omitidos}
        esperados = {"opt-1", "opt-2", "opt-3"}

        assert omitidos == esperados, f"omitidos={sorted(omitidos)}"
        assert incluidos.isdisjoint(omitidos), "un recurso no puede estar en ambos"

    def test_cada_omision_declara_SU_TAMANO(self) -> None:
        """**El tamaño es lo que hace la omisión accionable.**

        Saber que se cayó «opt-2» sin saber cuánto era deja al receptor sin
        poder ni decidir si le importa ni pedirlo con otro presupuesto.

        Y el tamaño que se declara es **el que el presupuesto usó para
        decidir**, no el largo del texto escrito. No es un matiz: si la
        omisión dijera 500 y el motor hubiera medido 513, el receptor
        recalcularía con el número que le dieron y sacaría una cuenta
        distinta a la que el Core tomó. Se declara `approx_chars(body)`.
        """
        from skillgraph.knowledge.context_controller import approx_chars

        resultado = _aplicar()
        _, opcionales = _candidatos()
        esperados = [approx_chars(o.body) for o in opcionales]

        assert [o.chars for o in resultado.omitidos] == esperados
        assert esperados != [CHARS_OPCIONAL], (
            "si lo declarado coincidiera con el texto crudo, este test "
            "estaría comprobando que approx_chars no hace nada"
        )

    def test_lo_que_ENTRA_Y_LO_que_SE_CAYO_SON_PARTICIONES(self) -> None:
        """Un candidato está **o** entra **o** se declara caído. Nunca las dos,
        y nunca ninguno de los dos: un recurso que desapareciera en silencio
        sin declararse omitido sería el defecto original."""
        resultado = _aplicar()
        incluidos = {r.resource_name for r in resultado.incluidos}
        omitidos = {o.name for o in resultado.omitidos}
        candidatos = {f"opt-{i}" for i in (1, 2, 3)} | {f"obl-{i}" for i in (1, 2)}

        assert incluidos | omitidos == candidatos, "alguien desaparecio sin declararse"
        assert incluidos & omitidos == set(), "alguien esta en ambos"

    def test_los_OBLIGATORIOS_no_se_truncan_ni_se_declaran_omitidos(self) -> None:
        """**La regla que B30 NO toca.** Los obligatorios entran siempre, o
        `apply_budget` lanza. Declarar uno omitido sería comprar el defecto
        desactivando el presupuesto."""
        resultado = _aplicar()
        incluidos = {r.resource_name for r in resultado.incluidos}
        omitidos = {o.name for o in resultado.omitidos}
        assert {"obl-1", "obl-2"} <= incluidos
        assert not (omitidos & {"obl-1", "obl-2"})

    def test_obligatorios_que_no_caben_siguen_dando_error(self) -> None:
        """**Y con la firma nueva, ese comportamiento no cambia.**"""
        from skillgraph.core.errors import TokenBudgetExceededError
        from skillgraph.knowledge.context_controller import apply_budget

        with pytest.raises(TokenBudgetExceededError):
            apply_budget(
                obligatory=[_recurso("obl-1", 400)],
                optional=(),
                budget_chars=10,
                overflow_strategy="drop_optional",
            )

    def test_registra_los_chars_usados_y_el_presupuesto(self) -> None:
        """El límite **y** lo usado. Con los dos, el receptor sabe cuánto
        margen quedó, que es lo que convierte «se cayó algo» en «se cayó algo y
        por mucho»."""
        resultado = _aplicar()
        assert resultado.budget_chars == BUDGET_AJUSTADO
        assert 0 < resultado.chars_usados < BUDGET_AJUSTADO

    def test_el_registro_es_inmutable(self) -> None:
        """`frozen=True, slots=True`: el resultado del presupuesto no se
        toca después de devuelto, que es la regla de inmutabilidad de
        `AGENTS.md` §1.1 aplicada a lo que cruza la frontera."""
        resultado = _aplicar()
        assert type(resultado).__dataclass_params__.frozen is True
        with pytest.raises(AttributeError):
            resultado.omitidos = ()  # type: ignore[misc]

    def test_la_omision_es_inmutable(self) -> None:
        resultado = _aplicar()
        omision = resultado.omitidos[0]
        assert type(omision).__dataclass_params__.frozen is True
        with pytest.raises(AttributeError):
            omision.chars = 0  # type: ignore[misc]

    def test_la_omision_declara_TODO_el_curso_de_su_identidad(self) -> None:
        """`kind`, `namespace` y `name`, como `included`. Un omitido que solo
        dijera el nombre no se podría volver a pedir: `included` dice el
        namespace entero y el omitido tiene que decir lo mismo.

        La comparación es contra **el mismo recurso por el que se construyó la
        omisión**, no contra el primer incluido: son recursos distintos, y
        `opt-1` no puede tener el namespace de `obl-1`.
        """
        from skillgraph.knowledge.context_controller import Omision

        _, opcionales = _candidatos()
        recurso = opcionales[0]
        omision = Omision.desde_recurso(recurso)

        assert omision.kind == recurso.resource_kind
        assert omision.namespace == recurso.resource_namespace
        assert omision.name == recurso.resource_name

        # Y sobre el presupuesto de verdad, cada omitido reconstruye el suyo.
        resultado = _aplicar()
        for o, r in zip(resultado.omitidos, opcionales, strict=True):
            assert o.como_tupla() == (
                r.resource_kind,
                r.resource_namespace,
                r.resource_name,
                approx_chars_de(r),
            )


# ---------------------------------------------------------------------------
# La cobertura: `complete` / `partial`, y por qué NO `blocked`
# ---------------------------------------------------------------------------


class TestLaCobertura:
    def test_truncado_es_PARCIAL(self) -> None:
        assert _aplicar().cobertura == "partial"

    def test_holgado_es_COMPLETO(self) -> None:
        assert _aplicar(BUDGET_HOLGADO).cobertura == "complete"

    def test_la_cobertura_se_DERIVA_y_no_se_declara(self) -> None:
        """**No es un campo que alguien pueda mentir.**

        `07-SPEC` §7 dice que el slice «declara» `complete`/`partial`/
        `blocked`. Declarar sería un campo, y un campo lo puede declarar
        cualquiera. La cobertura es una **propiedad derivada** de si hay
        omisiones: no hay dos verdades que puedan discrepar.
        """
        assert "cobertura" not in type(_aplicar()).__dataclass_fields__

    def test_no_declara_un_valor_que_nadie_puede_producir(self) -> None:
        """**`blocked` NO ESTÁ, Y POR QUÉ — la lección de B28 aplicada hacia
        delante.**

        `07-SPEC` §7 lista tres valores. `blocked` **no se puede representar en
        un `Handoff` que existe**: cuando falta algo, `compile_handoff` lanza
        `TokenBudgetExceededError`, `StaleKnowledgeError` o
        `MissingObligatoryError` — una **excepción tipada**, no un handoff.

        Declararlo sería repetir `empate_en_la_jerarquia`, el valor que B28
        eliminó de `MotivoDescarte` por inalcanzable: un Literal cerrado que
        nombra algo que ninguna ejecución puede producir.
        """
        from typing import get_args

        from skillgraph.knowledge.context_controller import Cobertura

        assert set(get_args(Cobertura)) == {"complete", "partial"}
        assert "blocked" not in get_args(Cobertura)

    def test_no_hay_UN_CONJUNTO_de_cobertura_que_pueda_discrepar(self) -> None:
        """**Y la mitad que evita que la verdad se duplique.**

        `AGENTS.md` §2.4 pide una constante `Final` cuando el `Literal` se usa
        para **validar entrada**. Aquí no se valida entrada:
        `PresupuestoAplicado.cobertura` es una **propiedad derivada** de si hay
        omisiones, y nadie la comprueba contra un conjunto. Publicar el
        conjunto sería un segundo sitio donde la verdad vive —y este bloque
        entero va de que no haya dos verdades que puedan discrepar—.

        **EL PREDICADO ES «¿ES UN CONJUNTO?», NO «¿EXISTE EL NOMBRE?».** La
        versión por nombre cazaba de más: `Cobertura`, el alias del `Literal`,
        cumple `n.upper() == "COBERTURA"` y no es un conjunto — es el tipo de
        una propiedad. Preguntar por el nombre hace que este guard señale
        precisamente la declaración que sí queremos, y un guard que obliga a
        borrar lo correcto enseña a no mirar el otro.
        """
        from skillgraph.knowledge import context_controller

        conjuntos = [
            n
            for n in dir(context_controller)
            if n.upper() == "COBERTURA"
            and isinstance(getattr(context_controller, n), (set, frozenset))
        ]
        assert conjuntos == [], (
            f"hay un conjunto de cobertura publicado ({conjuntos}) que nadie "
            "valida contra: es una segunda verdad"
        )

        # El alias del Literal sí está, y sí es lo que debe estar: es el tipo
        # de una propiedad derivada, no un conjunto contra el que comparar.
        assert context_controller.Cobertura is not None

    def test_blocked_existe_como_excepcion_tipada(self) -> None:
        """**Y la cobertura de `blocked` no se pierde: cambia de forma.** El
        receptor que no puede tener contexto recibe una excepción que lo dice,
        que es más fuerte que un campo que valdría `blocked`."""
        from skillgraph.core.errors import TokenBudgetExceededError
        from skillgraph.knowledge.context_controller import apply_budget

        with pytest.raises(TokenBudgetExceededError) as exc:
            apply_budget(
                obligatory=[_recurso("obl-1", 400)],
                optional=(),
                budget_chars=10,
                overflow_strategy="fail",
            )
        assert "budget" in str(exc.value)


# ---------------------------------------------------------------------------
# P2 y P3 — el Handoff lo carga, y lo firma
# ---------------------------------------------------------------------------


def _handoff(omitidos: tuple[tuple[str, str, str, int], ...]) -> object:
    from skillgraph.runtime.handoff import (
        Handoff,
        HandoffBehavior,
        HandoffExecution,
        HandoffIdentity,
        HandoffKnowledge,
    )

    return Handoff(
        identity=HandoffIdentity(
            tenant_id="t", project_id="p", run_id="r", node_execution_id="n", attempt=1
        ),
        behavior=HandoffBehavior(
            definition_kind="ActionNode",
            definition_name="d",
            definition_namespace="ns",
            definition_revision=1,
            api_version="v1",
        ),
        knowledge=HandoffKnowledge(recipe_ref="rc", omitidos=omitidos),
        execution=HandoffExecution(
            workspace_ref="ws",
            source_revision="rev",
            budget={"token_budget_chars": BUDGET_AJUSTADO},
        ),
        expected_result="x",
    )


class TestElHandoffLoCarga:
    def test_handoff_knowledge_declara_omitidos(self) -> None:
        from skillgraph.runtime.handoff import HandoffKnowledge

        assert "omitidos" in HandoffKnowledge.__dataclass_fields__

    def test_el_campo_nuevo_va_AL_FINAL(self) -> None:
        """**La lección de B25, y es la misma.** `HandoffKnowledge` se construye
        posicionalmente en código existente; un campo nuevo **en medio** haría
        que `HandoffKnowledge("rc", ())` metiera el included en el sitio
        equivocado."""
        from skillgraph.runtime.handoff import HandoffKnowledge

        campos = list(HandoffKnowledge.__dataclass_fields__)
        assert campos[-1] == "omitidos"
        assert campos[:2] == ["recipe_ref", "included"]

    def test_la_ida_y_vuelta_ANTIGUA_sigue_funcionando(self) -> None:
        """Posicional de dos campos, como antes del bloque: el campo nuevo **no**
        rompe a quien ya construía."""
        from skillgraph.runtime.handoff import HandoffKnowledge

        viejo = HandoffKnowledge("rc", (("claim", "claim:a", "a"),))
        assert viejo.recipe_ref == "rc"
        assert viejo.omitidos == ()

    def test_el_presupuesto_al_handoff_lleva_las_OMISIONES(self) -> None:
        """El camino real: de `apply_budget` a `Handoff`, sin que nadie tenga
        que reconstruir la diferencia."""
        from skillgraph.runtime.handoff import HandoffKnowledge

        resultado = _aplicar()
        conocimiento = HandoffKnowledge(
            recipe_ref="rc",
            included=tuple(r.as_tuple() for r in resultado.incluidos),
            omitidos=tuple(o.como_tupla() for o in resultado.omitidos),
        )
        assert [o[2] for o in conocimiento.omitidos] == ["opt-1", "opt-2", "opt-3"]


class TestElHashFirmaLasOmisiones:
    def test_dos_handoffs_que_difieren_SOLO_en_omisiones_difieren_en_el_hash(
        self,
    ) -> None:
        """**P3, y la razón de que el campo esté dentro del handoff.**

        `WI-111` midió ladistance entre el instante en que el Core calcula
        `context_hash` y el instante en que los eventos lo llevan. Un campo
        `omitidos` **fuera** del hash repetiría eso: el Adapter vería unas
        omisiones que el Core no firmó.
        """
        uno = _handoff((("claim", "claim:opt-1", "opt-1", 500),))
        dos = _handoff(())
        assert uno.context_hash != dos.context_hash

    def test_el_mismo_handoff_es_determinista(self) -> None:
        """Y que no sea determinista tampoco serviría de firma."""
        assert _handoff(()).context_hash == _handoff(()).context_hash

    def test_cambiar_el_TAMANO_de_una_omision_cambia_el_hash(self) -> None:
        """El tamaño importa: si no entrara en la firma, dos slices que
        pierden cosas distintas se declararían iguales."""
        uno = _handoff((("claim", "claim:opt-1", "opt-1", 500),))
        dos = _handoff((("claim", "claim:opt-1", "opt-1", 499),))
        assert uno.context_hash != dos.context_hash


# ---------------------------------------------------------------------------
# P4 — la CONTRA SALTO: lo dice cuando se cayó, y no se inventa cuando no
# ---------------------------------------------------------------------------


class TestLoDiceYNoSeInventa:
    def test_el_caso_truncado_declara_LOS_TRES(self) -> None:
        resultado = _aplicar()
        assert len(resultado.omitidos) == 3
        assert resultado.cobertura == "partial"

    def test_el_caso_holgado_NO_declara_ninguno(self) -> None:
        """**La otra mitad, y sin ella P4 no mide nada.** Un campo que siempre
        dijera tres sería tan mentiroso como el que no dice ninguno: el
        receptor dejaría de creerlo en el primer caso que no se cayó nada."""
        resultado = _aplicar(BUDGET_HOLGADO)
        assert resultado.omitidos == ()
        assert resultado.cobertura == "complete"

    def test_un_presupuesto_exacto_no_declora_ninguno(self) -> None:
        """El borde: si **cabe justo**, no hay omisión. Declarar una sería
        enseñar a desconfiar del campo justo donde es verdad."""
        from skillgraph.knowledge.context_controller import apply_budget

        resultado = apply_budget(
            obligatory=[_recurso("obl", 10)],
            optional=[],
            budget_chars=100,
            overflow_strategy="drop_optional",
        )
        assert resultado.omitidos == ()

    def test_un_omitido_nunca_puede_ser_un_incluido(self) -> None:
        """Y la propiedad más trivial es la que más se rompe si alguien cambia
        el orden de los iterables."""
        resultado = _aplicar()
        incluidos = {r.as_tuple() for r in resultado.incluidos}
        omitidos = {o.como_tupla()[:3] for o in resultado.omitidos}
        assert incluidos & omitidos == set()


# ---------------------------------------------------------------------------
# P5 — el skip no puede declarar completo un slice truncado
# ---------------------------------------------------------------------------


def _manifest_completo() -> object:
    from skillgraph.knowledge.file_handoff import CoverageManifest
    from skillgraph.knowledge.file_signature import FileSignature, SignatureVigencia

    firma = FileSignature(
        foco="a.py",
        contrato="file_summary",
        cobertura=1,
        procedencia="heuristica:0.1.0",
        vigencia=SignatureVigencia(
            state="complete", fresh=True, stale=False, checked_at_revision="revA"
        ),
    )
    return CoverageManifest(
        scope=object(),
        signatures=(firma,),
        fuentes=("local:a.py",),
        procedencia_por_firma={"a.py": "local"},
        revisiones_por_fuente={"local:a.py": "revA"},
        cobertura_total=1,
        required_coverage=1,
        limites={"token_budget": BUDGET_AJUSTADO, "freshness_policy": "best_effort"},
    )


class TestElSkipNoSeEngana:
    def test_la_firma_admite_las_omisiones(self) -> None:
        """**La propiedad que se midió, no su consecuencia.** Un guard que
        comprueba «¿hay omisiones y aun así se salta?» da verde en verde
        mientras el campo no exista —el vacuous pass que casi entra en el
        instrumento de este bloque—, porque `bool(omitidos)` es `False` antes
        del bloque y siempre. Lo que se mide es si el skip **puede enterarse**."""
        from skillgraph.knowledge.file_handoff import should_skip_adapter

        assert "omitidos" in inspect.signature(should_skip_adapter).parameters

    def test_no_se_salta_si_hay_omisiones(self) -> None:
        """**MEDIDO antes del bloque: devolvía `True`.** El sistema se quedaba
        sin agente por el motivo de que la respuesta era completa, cuando la
        respuesta se había cortado."""
        from skillgraph.knowledge.file_handoff import should_skip_adapter

        omitidos = tuple(o.como_tupla() for o in _aplicar().omitidos)
        assert not should_skip_adapter(manifest=_manifest_completo(), omitidos=omitidos)

    def test_si_no_hay_omisiones_sigue_saltando(self) -> None:
        """**Y la otra mitad: B30 no desactiva el skip.** Declarar «nunca te
        saltes» sería tan defectuoso como el original: convertir un skip útil
        en otro bug distinto, y dejar al sistema sin agente aunque la respuesta
        determinista fuera completa de verdad."""
        from skillgraph.knowledge.file_handoff import should_skip_adapter

        assert should_skip_adapter(manifest=_manifest_completo(), omitidos=())

    def test_omitidos_es_opcional_para_no_romper_a_quien_llama(self) -> None:
        """Quien ya llamaba `should_skip_adapter(manifest=...)` sigue
        compilando: el parámetro tiene default."""
        from skillgraph.knowledge.file_handoff import should_skip_adapter

        param = inspect.signature(should_skip_adapter).parameters["omitidos"]
        assert param.default == ()

    def test_sin_firmas_no_salta_nunca(self) -> None:
        """El comportamiento previo, intacto."""
        from skillgraph.knowledge.file_handoff import CoverageManifest, should_skip_adapter

        vacio = CoverageManifest(
            scope=object(),
            signatures=(),
            fuentes=(),
            procedencia_por_firma={},
            revisiones_por_fuente={},
            cobertura_total=0,
            required_coverage=0,
        )
        assert not should_skip_adapter(manifest=vacio, omitidos=())


# ---------------------------------------------------------------------------
# La superficie que se toca
# ---------------------------------------------------------------------------


class TestLasSuperficiesQueSeTocan:
    def test_apply_budget_es_PURA(self) -> None:
        """**Y NO HAY I/O OCULTO EN EL CAMINO QUE SE ABRE.** `apply_budget` es
        pura: recibe recursos ya resueltos y devuelve el reparto. Lo que
        `compile_handoff` hace —resolver selectores contra el `Storage`— es
        I/O y vive en otro sitio, como antes del bloque."""
        from skillgraph.knowledge import context_controller

        fuente = Path(inspect.getfile(context_controller)).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                nodo.name == "apply_budget"
            ):
                llamadas = {
                    n.func.id
                    for n in ast.walk(nodo)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                }
                prohibidas = {"open", "connect", "execute", "input", "print"}
                assert not (llamadas & prohibidas), (
                    f"apply_budget hace E/S: {llamadas & prohibidas}"
                )

    def test_el_tamano_de_una_omision_es_POSITIVO(self) -> None:
        """Un omitido de 0 chars no es un omitido: es ruido, y hace que quien
        lea dude de los otros."""
        resultado = _aplicar()
        assert all(o.chars > 0 for o in resultado.omitidos)

    def test_la_cobertura_es_un_LITERAL_CERRADO(self) -> None:
        from typing import get_args

        from skillgraph.knowledge.context_controller import Cobertura

        assert set(get_args(Cobertura)) == {"complete", "partial"}


# ---------------------------------------------------------------------------
# El contrasalto del propio diseño
# ---------------------------------------------------------------------------


class TestLaFormaNoSePuedeEludir:
    def test_el_TIPO_de_omitidos_no_es_un_dict(self) -> None:
        """**`dict` dentro de un `frozen` es deuda, y WI-113 la midió en
        `AgentResult.result`.** Las omisiones son tuplas inmutables y
        tipadas, no un `Mapping` que alguien pueda mutar después de calcular el
        hash."""

        h = _handoff((("claim", "claim:opt-1", "opt-1", 500),))
        assert isinstance(h.knowledge.omitidos, tuple)
        assert all(isinstance(o, tuple) for o in h.knowledge.omitidos)

    def test_el_presupuesto_devuelve_TUPLAS(self) -> None:
        resultado = _aplicar()
        assert isinstance(resultado.incluidos, tuple)
        assert isinstance(resultado.omitidos, tuple)

    def test_la_omision_no_es_un_string_suelto(self) -> None:
        """**Por qué hay un ADT y no un `tuple[str]`.** Un string se puede
        construir en cualquier sitio y nadie lo revisa; un `Omision` con
        `chars` obliga a que quien lo construye **sepa** el tamaño, que es la
        mitad de lo que hace la omisión accionable."""
        from skillgraph.knowledge.context_controller import Omision

        resultado = _aplicar()
        assert all(isinstance(o, Omision) for o in resultado.omitidos)

    def test_la_omision_no_puede_quedar_SIN_NAMESPACE(self) -> None:
        """Sin namespace una omisión es irreferenciable: no se puede volver a
        pedir, y entonces omitirla no es información sino ruido."""
        from skillgraph.core.errors import ValidationError
        from skillgraph.knowledge.context_controller import Omision

        with pytest.raises(ValidationError):
            Omision(kind="claim", namespace="", name="a", chars=1)
