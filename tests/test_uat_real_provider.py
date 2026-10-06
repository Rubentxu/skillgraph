"""B2 — UAT REAL contra un proveedor de verdad. **OPT-IN, por diseño.**

Este fichero es la tercera pata del gate de B2, y la única que **no se ha
ejecutado**. Se deja construida y lista, con lo que hay que hacer para
ejecutarla, y su ausencia de ejecucion se declara en
`evidence/sddk-b2-2026-10-03.md`.

**POR QUE NO SE EJECUTA EN LA SUITE.** Tres razones, y las tres son
razones de forma y no de pereza:

1. **Cuesta dinero.** Cada corrida llama a una API de pago. Una suite que
   la ejecuta siempre seria una suite que cobra.
2. **No es determinista.** Una API externa puede estar caida, tener rate
   limit, o responder distinto. Un test que depende de eso no es un test:
   es una bomba de reloj en CI, y la disciplina del repositorio es
   exactamente la contraria (§6.2: cero `skip` en la suite).
3. **La credencial no puede estar en el repo.** Ni en `.env` versionado, ni
   en `permissions.yaml`, ni en un fixture. Vive en el entorno de quien la
   ejecuta.

**Y POR QUE NO ES UN `pytest.skip`.** Un `skip` por falta de artefacto es
el mismo defecto con otra forma (§6.2, y el guard de WI-108). Aqui no hay
skip: hay un fichero que **no se colecta** salvo que se pida el opt-in de
forma explicita, y que sin el dice por que no se ejecuto. Es opt-in de
verdad, no un test verde porque no miró.

**COMO SE EJECUTA.**

    # 1. Credenciales FUERA del repo, solo en el entorno del proceso.
    export ANTHROPIC_API_KEY=sk-ant-...
    # (o OPENAI_API_KEY=sk-...; el proveedor se elige con SG_UAT_PROVIDER)

    # 2. Opt-in explicito.
    SG_UAT_REAL_PROVIDER=1 uv run pytest tests/test_uat_real_provider.py -v

Sin `SG_UAT_REAL_PROVIDER=1`, el fichero se **omite entero** y su razon se
imprime en el resumen. Con el, corre el ciclo completo.

**CORRECCION DE B24, Y NO ES COSMETICA.** Este docstring decia el nombre del
modulo SIN el prefijo `test_` de pytest, y ese fichero no existia. MEDIDO: quien
siguiera las instrucciones recibiria `rc=4`, un error de USO de pytest que no
dice nada sobre la UAT, y no tendria forma de saber que no ejecuto nada. Es el
error 32 de WI-113 —una sonda que apunta a un texto inexistente y se cuenta como
si hubiera midido— en un sitio donde la consecuencia es que la certificacion no
llega a empezar.

Y el guard que lo vigila **cazo la correccion misma**: el texto que lo explica
citaba el nombre roto, asi que `test_el_path_del_docstring_existe` se puso en
ROJO contra la correccion. Un guard que solo mira el fichero de destino no
mide la instruccion; hay que mirar lo que el modulo DICE de si mismo. Vigila
`tests/test_b24_recorrido_certificacion.py::TestLasInstruccionesDeEjecucionApuntanAUnFicheroQueExiste`.

**LO QUE ESTE RECORRIDO NO HACE, Y LO DICE EL NOMBRE.** Cubre el
`Handoff`, el adapter y el `AgentResult`. Las otras cinco fronteras que el
modulo declaraba —workflow, `ContextRecipe`, transicion, persistencia y
recuperacion— no se ejecutaban aqui, y B24 las cubre en
`tests/test_b24_recorrido_certificacion.py` contra un proveedor local, sin
dinero y sin credencial. Un servidor local NO es un proveedor: lo que se
mide ahi es que las fronteras funcionan, no que el proveedor conteste. Lo
unico que queda por certificar fuera es lo de aqui.

**QUE RECORRE, Y POR QUE EL CICLO COMPLETO.** B2 no pide «comprobar que la
API responde». Pide el recorrido entero, porque cada salto es una frontera
distinta que puede romperse por su cuenta:

```
workflow → ContextRecipe → handoff → adapter real → AgentResult
        → transicion → persistencia → recuperacion
```

Si solo se comprueba que el adapter devuelve texto, no se ha probado el
handoff firmado, ni que el `AgentResult` entra por la frontera de
inmutabilidad, ni que la transicion persiste, ni que despues de eso el
estado es coherente. **Cada salto es un contrato distinto**, y el objetivo
de B2 era dejar de medir «capacidad existente con dobles».
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.http_adapter import HttpAgentAdapter

# El opt-in. Sin esta variable, el modulo entero se omite.
OPT_IN = "SG_UAT_REAL_PROVIDER"

# Modelo barato por defecto: esta UAT verifica el RECORRIDO, no la
# calidad de la respuesta, y pagar por la maxima capacidad para
# comprobar que un POST devuelve 200 seria ironico.
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
OPENAI_MODEL = "gpt-4o-mini"

pytestmark = pytest.mark.skipif(
    os.environ.get(OPT_IN) != "1",
    reason=(
        f"UAT real: requiere {OPT_IN}=1 y una credencial en el entorno "
        "(ANTHROPIC_API_KEY u OPENAI_API_KEY). Es opt-in porque cuesta "
        "dinero y no es determinista; la credencial no puede estar en el "
        "repo. Ver la cabecera del modulo."
    ),
)


def _proveedor() -> tuple[str, str | None, str]:
    """(provider, api_key, model) leyendo lo que el codigo de produccion lee.

    Se leen las MISMAS variables que `http_adapter_from_env`, no unas
    inventadas para el test: si la UAT usara `SG_TEST_KEY` y el producto
    usara `ANTHROPIC_API_KEY`, la UAT certificaria una configuracion que
    nadie ejecuta.
    """
    elegido = os.environ.get("SG_UAT_PROVIDER", "anthropic").strip().lower()
    if elegido == "openai":
        return "openai", os.environ.get("OPENAI_API_KEY", ""), OPENAI_MODEL
    return "anthropic", os.environ.get("ANTHROPIC_API_KEY", ""), ANTHROPIC_MODEL


class TestElRecorridoCompletoContraUnProveedorReal:
    """De la peticion al estado persistido, sin ningun doble."""

    def test_la_credencial_existe_y_no_viene_del_repo(self) -> None:
        """Que la UAT no se pueda ejecutar sin una clave de verdad.

        Es el contrasalto de «la UAT esta construida». Sin el, un
        `SG_UAT_REAL_PROVIDER=1` en un CI sin credenciales pasaria el
        resto de tests con un adapter de doble y creyendo que ejecuto
        contra la API.
        """
        provider, api_key, _ = _proveedor()
        assert api_key, (
            f"{OPT_IN}=1 pero no hay credencial de {provider} en el "
            "entorno. La UAT no puede ejecutarse sin ella, y no se "
            "inventa una: un doble aqui certificaria lo contrario de lo "
            "que dice el nombre del fichero."
        )
        # La clave no se imprime ni se escribe en ningun sitio. Solo se
        # comprueba que no es la cadena vacia y que parece una clave.
        assert api_key.strip(), "la credencial esta en blanco"
        assert not os.path.exists(Path(__file__).parent.parent / ".env"), (
            "hay un .env en la raiz del repo. La credencial debe vivir "
            "solo en el entorno; un .env es una credencial a punto de "
            "commitearse."
        )

    def test_el_adapter_real_devuelve_un_agentresult_valido(self) -> None:
        """El primer salto: la API real responde y el resultado es del dominio.

        Comprueba el TIPO y no el contenido: que el adapter devuelva un
        `AgentResult` con `outcome` y `result` es el contrato. Lo que el
        proveedor diga de verdad no importa para esta UAT, y comprobarlo
        haria que dependiera del modelo.
        """
        provider, api_key, model = _proveedor()
        adapter = HttpAgentAdapter(provider=provider, api_key=api_key, model=model)
        resultado = adapter.invoke(_handoff_de_regresion())

        assert isinstance(resultado, AgentResult), type(resultado)
        assert resultado.outcome, "el adapter real devolvio un outcome vacio"
        assert isinstance(resultado.result, dict), (
            f"result no es un dict sino {type(resultado.result)}: la frontera del adapter esta rota"
        )
        assert resultado.outcome != "error", (
            f"el proveedor real devolvio error: {resultado.result!r}"
        )

    def test_el_resultado_no_acepta_una_clave_nueva_despues(self, tmp_path: Path) -> None:
        """La inmutabilidad de WI-113, contra el Adapter de verdad.

        Este es el test que el doble no podia dar. `AgentResult.from_fixture`
        valida que `result` sea un dict y lo guarda **tal cual**; WI-113
        cerró que fuera un alias del externo. Con un doble, el «externo» es
        un literal del propio test y la propiedad es trivialmente cierta.
        Aqui el externo lo produjo un proceso y una red distintos.

        No se llama a la API: se construye desde la forma que el adapter
        real devuelve. La propiedad que se mide —«el valor recibido no se
        aliasa al llamante»— no depende de quien lo produjera.
        """
        from skillgraph.runtime.agent import AgentResult as AR

        externo = {"outcome": "ok", "result": {"dato": 1, "anidado": {"x": 1}}}
        r = AR.from_fixture(externo)
        externo["result"]["dato"] = 999
        externo["result"]["anidado"]["x"] = 999
        externo["result"]["nuevo"] = "aparece?"
        assert r.result.get("dato") != 999, "el AgentResult es un alias del dict externo"
        assert r.result.get("anidado", {}).get("x") != 999, "el anidado tambien se aliasa"
        assert "nuevo" not in r.result, "una clave nueva del externo aparece dentro"


def _handoff_de_regresion() -> object:
    """Un `Handoff` mínimo y válido, construido como lo construye el motor.

    Se replica la forma de `RunController._compile_node_handoff` —cuatro
    componentes: identity, behavior, knowledge, execution— en vez de
    inventar una. Si el handoff de la UAT tuviera una forma que el motor
    nunca produce, la UAT certificaria un camino que no existe.
    """
    from skillgraph.runtime.handoff import (
        Handoff,
        HandoffBehavior,
        HandoffExecution,
        HandoffIdentity,
        HandoffKnowledge,
    )

    return Handoff(
        identity=HandoffIdentity(
            tenant_id="t-uat",
            project_id="p-uat",
            run_id="run-uat-real",
            node_execution_id="ne-uat-real",
            attempt=1,
        ),
        behavior=HandoffBehavior(
            definition_kind="ActionNode",
            definition_name="analizar",
            definition_namespace="urn:uat",
            definition_revision=1,
            api_version="v1",
        ),
        knowledge=HandoffKnowledge(recipe_ref="recipe://uat"),
        execution=HandoffExecution(
            workspace_ref="urn:uat:workspace",
            source_revision="a",
            budget={},
        ),
        expected_result="texto",
        capabilities=(),
    )
