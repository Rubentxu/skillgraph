"""WI-90: `FileSignature` tiene `to_dict()` pero no `from_dict()`.

`record_evidence_for_file_signature` (knowledge_controller.py:234) persiste
`file_signature.to_dict()`. `list_file_signatures_for_source`
(knowledge_controller.py:285) lo lee escribiendo **a mano el inverso**, campo
a campo, con subindices crudos:

    foco=payload["foco"], contrato=payload["contrato"], ...
    procedencia=SignatureProcedencia(**payload["procedencia"]),

Nadie verifica que las dos mitades coincidan. Medido:

  - un campo de mas -> **se ignora en silencio**
  - falta una clave -> `KeyError` (no tipado)
  - `procedencia` incompleta -> `TypeError` (no tipado)

Los tres explotan en `governance/improvement.py`, que tiene tres call sites
sin proteger y es otra capa con otro vocabulario de errores (AGENTS 1.2: el
codigo de dominio lanza `SkillGraphError`, nunca genericos).

El caso del silencio tiene una consecuencia futura concreta: si
`FileSignature` gana un campo obligatorio, el lector construira sin el y la
lectura de datos YA persistidos se rompe. No al escribir: meses despues, al
leer.
"""

from __future__ import annotations

import pytest

from skillgraph.core.errors import SkillGraphError
from skillgraph.knowledge.file_signature import (
    EXTRACTION_STATES,
    FileSignature,
    SignatureProcedencia,
    SignatureVigencia,
)

VALIDO = {
    "foco": "module",
    "contrato": "module",
    "cobertura": 12,
    "procedencia": {"extraction_method": "regex_import", "extractor_version": "1"},
    "vigencia": {
        "state": "complete",
        "fresh": True,
        "stale": False,
        "checked_at_revision": "rev-1",
    },
    "metadata": {"nota": "x"},
}


def _sig(**over: object) -> FileSignature:
    base = {
        "foco": "function",
        "contrato": "def",
        "cobertura": 3,
        "procedencia": SignatureProcedencia("regex_def", "1"),
        "vigencia": SignatureVigencia("partial", fresh=False, stale=True),
    }
    base.update(over)
    return FileSignature(**base)  # type: ignore[arg-type]


class TestRoundTrip:
    """`from_dict(to_dict(s)) == s` para toda signature valida.

    Esta es la comprobacion que hacia falta y no existia: con el lector
    escrito a mano, anadir un campo a `FileSignature` lo hacia perder en
    silencio, y nada fallaba.
    """

    @pytest.mark.parametrize("state", sorted(EXTRACTION_STATES))
    def test_round_trip_for_every_extraction_state(self, state: str) -> None:
        fresh = state == "complete"
        stale = state in {"empty", "absent", "partial", "stale"}
        sig = _sig(
            vigencia=SignatureVigencia(state, fresh=fresh, stale=stale, checked_at_revision="r")
        )
        assert FileSignature.from_dict(sig.to_dict()) == sig

    def test_round_trip_preserves_metadata(self) -> None:
        sig = _sig(metadata={"a": 1, "b": "dos", "c": [3]})
        assert FileSignature.from_dict(sig.to_dict()).metadata == {"a": 1, "b": "dos", "c": [3]}

    def test_to_dict_and_from_dict_cover_the_same_fields(self) -> None:
        """La lista de campos no se puede desincronizar.

        Si `to_dict()` dejara de emitir un campo, `from_dict` lo pediria y el
        round trip reventaria; si `from_dict` lo exigiera y `to_dict` no lo
        emitiera, tambien. Lo que NO puede pasar es que los dos se olviden a
        la vez, y para eso esta esta asercion sobre las claves.
        """
        claves = set(_sig().to_dict())
        assert claves == {
            "foco",
            "contrato",
            "cobertura",
            "procedencia",
            "vigencia",
            "metadata",
        }
        # Y el dataclass no puede ganar un campo que nadie serializa.
        from dataclasses import fields

        assert {f.name for f in fields(FileSignature)} == claves


class TestFromDictIsTyped:
    """Todo fallo de forma sale como `SkillGraphError`, no como `KeyError`."""

    def test_missing_key_is_typed(self) -> None:
        payload = {k: v for k, v in VALIDO.items() if k != "foco"}
        with pytest.raises(SkillGraphError) as exc:
            FileSignature.from_dict(payload)
        assert "foco" in str(exc.value)

    def test_unknown_key_is_rejected_not_ignored(self) -> None:
        """El caso que hoy se pierde en silencio.

        Una signature escrita por una version futura trae campos que esta
        version no conoce. Perderlos en silencio es peor que fallar: el
        consumidor cree que tiene el dato completo y no lo tiene.
        """
        payload = dict(VALIDO, campo_del_futuro=1)
        with pytest.raises(SkillGraphError) as exc:
            FileSignature.from_dict(payload)
        assert "campo_del_futuro" in str(exc.value)

    def test_bad_procedencia_is_typed(self) -> None:
        payload = dict(VALIDO, procedencia={"extraction_method": "x"})
        with pytest.raises(SkillGraphError):
            FileSignature.from_dict(payload)

    def test_bad_vigencia_is_typed(self) -> None:
        payload = dict(VALIDO, vigencia={"state": "no-existe", "fresh": True, "stale": False})
        with pytest.raises(SkillGraphError):
            FileSignature.from_dict(payload)

    @pytest.mark.parametrize("campo", ["foco", "contrato", "cobertura"])
    def test_wrong_scalar_type_is_typed(self, campo: str) -> None:
        payload = dict(VALIDO, **{campo: {"no": "es"}})
        with pytest.raises(SkillGraphError):
            FileSignature.from_dict(payload)

    def test_non_dict_payload_is_typed(self) -> None:
        with pytest.raises(SkillGraphError):
            FileSignature.from_dict("no soy un dict")  # type: ignore[arg-type]


class TestNoRawSubscriptsRemainInTheReader:
    """La deriva no se repite: el lector no vuelve a deserializar a mano."""

    def test_controller_uses_from_dict(self) -> None:
        """La deriva no se repite: el lector no vuelve a leer claves a mano.

        Se buscan subindices cuyo *slice* sea una constante de string, que es
        lo que significa `payload["foco"]`. Un subindice de anotacion de
        tipo (`tuple[FileSignature, ...]`) no se cuenta: no lee nada.
        """
        import ast
        import inspect

        from skillgraph.knowledge.knowledge_controller import KnowledgeController

        src = inspect.cleandoc(
            inspect.getsource(KnowledgeController.list_file_signatures_for_source)
        )
        tree = ast.parse(src)
        lecturas = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Subscript)
            and isinstance(n.slice, ast.Constant)
            and isinstance(n.slice.value, str)
        ]
        assert lecturas == [], (
            "list_file_signatures_for_source ha vuelto a leer el payload con "
            f"claves literales: {[ast.unparse(n) for n in lecturas]}"
        )
        assert "from_dict" in src, "el lector no usa FileSignature.from_dict"
