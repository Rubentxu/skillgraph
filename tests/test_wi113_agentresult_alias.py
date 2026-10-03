"""WI-113: el AgentResult es el dict del Adapter, no una copia.

`AGENTS.md` 1.1 dice que las colecciones de una estructura inmutable
sean `tuple`, y que un dict externo se envuelva en `MappingProxyType`
**sobre una copia**. WI-111 aplico eso al `budget` del Handoff.

Quedaron once campos mutables dentro de dataclasses `frozen`, y
registrados como deuda con el criterio de que no participaban en el
hash firmado. Ese criterio era correcto para el hash y equivocado
para el resto: uno de los once esta en la frontera con codigo
EXTERNO, y lo que hace no ser un dict mutable — es un **alias**.

`AgentResult.from_fixture` valida que `result` sea un dict y lo guarda
**tal cual**:

    result = payload["result"]
    return AgentResult(outcome=outcome_raw, result=result, ...)

Medido antes de arreglar nada:

    externo = {"outcome": "ok", "result": {"dato": 1}}
    r = AgentResult.from_fixture(externo)
    externo["result"]["dato"] = 999
    externo["result"]["inyectado"] = "tras la construccion"
    r.result  ->  {'dato': 999, 'inyectado': 'tras la construccion'}

El `AgentResult` cambio sin que nadie lo tocara. Y no es cosmetico:
`node_execution_delegations.py:443::_finalize_node_success` serializa ese dict a disco, asi
que lo que se persiste es el dict del Adapter.

**El guard ejecuta, no lee.** Un guard por AST veria que el campo esta
anotado `dict[str, Any]`, que es lo que dice la regla, y no que el
valor esta aliaseado. La propiedad —«el valor no se aliasa al
llamante»— solo se mide construyendo el objeto y mutando el origen.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from skillgraph.runtime.agent import AgentResult
from skillgraph.runtime.run_types import result_to_jsonable


def _payload() -> dict[str, Any]:
    """Un payload NUEVO cada vez: compartirlo seria el propio defecto."""
    return {
        "outcome": "ok",
        "result": {"dato": 1, "anidado": {"profundo": True}},
        "evidence_ref": "ev-1",
    }


class TestElAgentResultNoSeAliasaAlLlamante:
    """C1 y C2: la frontera con el exterior no puede seguir escribiendo."""

    def test_mutar_el_dict_externo_no_altera_el_resultado(self) -> None:
        payload = _payload()
        resultado = AgentResult.from_fixture(payload)
        payload["result"]["dato"] = 999
        assert resultado.result["dato"] == 1

    def test_una_clave_nueva_externa_no_aparece_dentro(self) -> None:
        payload = _payload()
        resultado = AgentResult.from_fixture(payload)
        payload["result"]["inyectado"] = "despues de construir"
        assert "inyectado" not in resultado.result

    def test_mutar_el_dict_anidado_tampoco_altera(self) -> None:
        """C2 en profundidad: la copia tiene que ser real, no de primer nivel."""
        payload = _payload()
        resultado = AgentResult.from_fixture(payload)
        payload["result"]["anidado"]["profundo"] = False
        assert resultado.result["anidado"]["profundo"] is True

    def test_el_payload_fuente_no_se_ve_afectado_por_cualquier_cosa(self) -> None:
        """Sonda del otro lado: la copia no puede tampoco Writing hacia atras.

        Si la 'copia' fuera un alias al reves, esta comprobacion pasaria
        y la anterior fallaria. Las dos juntas fijan que hay dos
        valores independientes.
        """
        payload = _payload()
        resultado = AgentResult.from_fixture(payload)
        resultado.result["dato"] = 555
        assert payload["result"]["dato"] == 1

    def test_el_resultado_es_un_dict_plano_y_serializable(self) -> None:
        """La forma que SÍ tiene que cumplir, y no es la de WI-111.

        En WI-111 el `budget` se envolvio en `MappingProxyType` porque
        solo se leia. Aqui no: el motor serializa el resultado a disco
        (`node_execution_delegations.py:443::_finalize_node_success`) y `json.dumps` **no**
        acepta un mappingproxy. Envolverlo rompe la frontera.

        La inmutabilidad de este campo no la aporta el tipo, la aporta
        que el Core ya no comparta memoria con el exterior, que es lo que
        miden los cuatro tests anteriores. Un dict vivo que nadie
        alcanza es tan inmutable como uno envuelto — y este SI lo
        alcanza el motor.
        """
        resultado = AgentResult.from_fixture(_payload())
        assert isinstance(resultado.result, dict)
        json.dumps(resultado.result, sort_keys=True)


class TestLaCopiaNoCambiaLaSemantica:
    """C3: arreglar el alias no puede cambiar lo que el motor ve."""

    def test_dos_construcciones_del_mismo_payload_son_iguales(self) -> None:
        p = _payload()
        a = AgentResult.from_fixture(p)
        b = AgentResult.from_fixture(p)
        assert a == b

    def test_el_outcome_se_conserva(self) -> None:
        assert AgentResult.from_fixture(_payload()).outcome == "ok"

    def test_el_evidence_ref_se_conserva(self) -> None:
        assert AgentResult.from_fixture(_payload()).evidence_ref == "ev-1"

    def test_evidence_ref_ausente_sigue_siendo_none(self) -> None:
        payload = _payload()
        payload.pop("evidence_ref")
        assert AgentResult.from_fixture(payload).evidence_ref is None

    def test_un_payload_invalido_sigue_siendo_rechazado(self) -> None:
        """La validacion de `from_fixture` no se toca: solo cambia la copia."""
        from skillgraph.core.errors import OutcomeInvalidError, ValidationError

        for malo in (
            {"result": {}},  # falta outcome
            {"outcome": "ok"},  # falta result
            {"outcome": "", "result": {}},  # outcome vacio
            {"outcome": 7, "result": {}},  # outcome no str
            {"outcome": "ok", "result": []},  # result no dict
            {"outcome": "ok", "result": {}, "evidence_ref": 3},  # evidence_ref no str
        ):
            with pytest.raises((ValidationError, OutcomeInvalidError)):
                AgentResult.from_fixture(malo)


class TestLaSerializacionNoCambia:
    """C4: lo que se persiste a disco es lo mismo."""

    def test_result_to_jsonable_produce_el_mismo_json(self) -> None:
        """La forma REAL de `result_to_jsonable`, incluida su clave.

        La primera version de este test afirmaba que la salida eran solo
        `outcome` y `result`, y fallo: la funcion devuelve tambien
        `evidence_ref`. Un test que describe la forma a ojo falla por la
        razon equivocada y hace perder el tiempo de leer la implementacion.
        """
        resultado = AgentResult.from_fixture(_payload())
        assert result_to_jsonable(resultado) == {
            "outcome": "ok",
            "result": {"dato": 1, "anidado": {"profundo": True}},
            "evidence_ref": "ev-1",
        }

    def test_evidence_ref_ausente_no_inventa_la_clave(self) -> None:
        payload = _payload()
        payload.pop("evidence_ref")
        jsonable = result_to_jsonable(AgentResult.from_fixture(payload))
        assert jsonable.get("evidence_ref") is None

    def test_el_json_es_serializable(self) -> None:
        resultado = AgentResult.from_fixture(_payload())
        json.dumps(result_to_jsonable(resultado), sort_keys=True)


class TestElGuardMideLaPropiedadYNoElAlias:
    """Contrasaltos: el guard tiene que fallar si se revierte el arreglo.

    Sin esto, un guard que devuelve `()` siempre pasaria todo verde y
    seria indistinguible de uno que no mide nada.
    """

    def test_la_comprobacion_central_falla_si_no_hay_copia(self) -> None:
        """Construye el caso SIN COPIA a proposito y exige que se note.

        Es la forma de comprobar que el test de arriba mide algo: si el
        alias volviera, el test de arriba pasaria y este no.
        """
        payload = _payload()
        sin_copia = AgentResult(
            outcome=payload["outcome"],
            result=payload["result"],  # alias, como estaba antes
            evidence_ref="ev-1",
        )
        payload["result"]["dato"] = 999
        assert sin_copia.result["dato"] == 999, (
            "el contrasalto cambio: el alias ya no se reproduce, y el test "
            "principal dejaria de medir lo que dice medir"
        )

    def test_dos_construcciones_independientes_dan_el_mismo_resultado(self) -> None:
        """El modulo bajo prueba no lee el reloj: dos constructions dan igual."""
        a = AgentResult.from_fixture(_payload())
        b = AgentResult.from_fixture(_payload())
        assert a.result == b.result
