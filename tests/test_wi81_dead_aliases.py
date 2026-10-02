"""WI-81: los alias de WI-56 en `row_mappers.py` son codigo muerto.

Deuda con decision normativa previa: ADR-0014 ("eliminacion de shims de
retro-compatibilidad") elimino los 20 shims de MODULO de `src/skillgraph/`
raiz. Esta es la segunda tanda: 7 ALIAS DE FUNCION que WI-56 (corte 3)
dejo en `platform/row_mappers.py`.

El docstring de cada uno de los 7 decia:

    "Alias de compatibilidad (WI-56 corte 3): mapper viviendo en
     `SqliteKnowledgeRepository.row_to_X`. El corte 5 reubicara los
     callers."

El corte 5 ocurrio (ADR-0020 movio los mappers a `knowledge_mappers.py` y
`knowledge_repository.py:696-702` creo aliases locales al mapper REAL).
Los callers se reubicaron. Los alias se quedaron, y `MAPPER_NAMES` +
`storage.__all__` siguieron prometiendo una API de 12 que son 5.

INERTIA MEDIDA EN RUNTIME (no por lectura), que es lo que hace el borrado
seguro:

    knowledge_repository._row_to_source  is  row_mappers._row_to_source
    -> False   (los 7)

Los aliases locales de `knowledge_repository` apuntan a
`knowledge_mappers.row_to_X`, NO a estos alias. Y ningun modulo de `src/`
importa los 7 desde `platform.storage`: `event_store.py:24` importa
`_SCHEMA_SQL, Storage, _row_to_stored_event`, y ese ultimo es uno de los
CINCO mappers reales, no uno de los siete alias.

La premisa del docstring del modulo ("NO renombrar ni mover sin migrar
event_store, policy_store y knowledge_repository") sigue vigente para los
5 reales y es OBSOLETA para estos 7. Este test la fija por ambos lados:
comprueba que los 7 no tienen callers (caracterizacion, para que el
borrado no rompa nada) y que ya no se publican (el contrato roto).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from skillgraph.platform import row_mappers
from skillgraph.platform.row_mappers import MAPPER_NAMES

# Los 7 alias de WI-56 corte 3. No son mappers: son reenvios a funciones
# que viven en `knowledge_mappers.py` y a las que nadie llama por aqui.
DEAD_ALIASES: frozenset[str] = frozenset(
    {
        "_row_to_source",
        "_row_to_evidence",
        "_row_to_stored_evidence",
        "_row_to_claim",
        "_row_to_stored_claim",
        "_row_to_resource",
        "_row_to_relation",
    }
)

# Los 5 que SI son mappers reales de este modulo. Protegerlos: el
# borrado no puede tocarlos.
LIVE_MAPPERS: frozenset[str] = frozenset(
    {
        "_row_to_stored_event",
        "_row_to_stored_promotion",
        "_row_to_stored_budget",
        "_row_to_run",
        "_row_to_node_execution",
    }
)

_SRC = Path("src/skillgraph")


def _modules_importing(name: str, from_module: str) -> list[str]:
    """Modulos de src/ que importan `name` desde `from_module`."""
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != from_module:
                continue
            if any(a.name == name for a in node.names):
                hits.append(str(path))
    return hits


class TestDeadAliasesHaveNoCallers:
    """Caracterizacion: por que el borrado es seguro.

    `test_nothing_imports_the_alias` es la excepcion: queda aqui porque
    comparte la caracterizacion (no hay caller ni directo ni por el
    facade) pero esta ROJO hasta que se aplica el fix.

    Nota sobre la comprobacion. Un barrido AST que buscase "quien llama
    a `_row_to_source`" daria un falso positivo: `knowledge_repository.py`
    tiene funciones que LLAMAN a `_row_to_source`, pero ese simbolo es un
    alias LOCAL suyo (`knowledge_repository.py:696-702`) que apunta a
    `knowledge_mappers.row_to_source`. La pregunta correcta no es "quien
    menciona el nombre" sino "el simbolo que se resuelve, es el alias de
    `row_mappers`". Eso solo se responde en runtime, con identidad de
    objetos, y es lo que se comprueba abajo.
    """

    @pytest.mark.parametrize("name", sorted(DEAD_ALIASES))
    def test_nothing_imports_the_alias(self, name: str) -> None:
        """Verde DESPUES del borrado. Antes falla por `storage.py:56`,
        que re-exporta los 7; ese re-export es parte de lo que se retira.
        Vive en esta clase porque la razon de que sea seguro borrarlos es
        que no hay NINGUN caller de ellos: ni directo ni por el facade.
        """
        from_rm = _modules_importing(name, "skillgraph.platform.row_mappers")
        from_st = _modules_importing(name, "skillgraph.platform.storage")
        assert not from_rm, f"se sigue importando desde row_mappers: {from_rm}"
        assert not from_st, f"se sigue importando desde storage: {from_st}"

    def test_live_mappers_are_still_imported_by_their_consumers(self) -> None:
        """Caracterizacion real: los 5 que quedan TIENEN consumers.

        Si esto dejara de ser cierto, `row_mappers.py` entero seria
        candidata a borrarse. Hoy `event_store` y `policy_store` lo usan.
        """
        from_rm = _modules_importing("_row_to_stored_event", "skillgraph.platform.row_mappers")
        assert from_rm, (
            "nadie importa _row_to_stored_event desde row_mappers: "
            "el modulo entero habria muerto sin que nada lo dijera"
        )

    def test_callers_resolve_to_real_mapper(self) -> None:
        """Los modulos que usan el NOMBRE resuelven al mapper real.

        Si alguno resolviera al alias, el alias tendria un caller real y
        borrarlo seria una regresion. Aqui se comprueba por identidad.
        """
        import importlib

        for module_name in (
            "skillgraph.platform.knowledge_repository",
            "skillgraph.platform.knowledge_claims",
        ):
            module = importlib.import_module(module_name)
            shadowed = [
                name
                for name in sorted(DEAD_ALIASES)
                if hasattr(module, name)
                and getattr(module, name) is getattr(row_mappers, name, None)
            ]
            assert not shadowed, (
                f"{module_name} resuelve {shadowed} al alias de row_mappers: "
                "ese alias TIENE un caller y no se puede borrar"
            )

    def test_knowledge_repository_aliases_point_at_real_mappers(self) -> None:
        """El otro lado: los aliases locales siguen apuntando al mapper real."""
        from skillgraph.platform import knowledge_mappers, knowledge_repository

        for name in sorted(DEAD_ALIASES):
            if not hasattr(knowledge_repository, name):
                continue
            real = "row_to_" + name.removeprefix("_row_to_")
            assert hasattr(knowledge_mappers, real), f"no existe el mapper real {real}"
            assert getattr(knowledge_repository, name) is getattr(knowledge_mappers, real), (
                f"{name} deberia resolver a knowledge_mappers.{real}"
            )


class TestDeadAliasesAreNotPublished:
    """El contrato roto: MAPPER_NAMES y storage.__all__ prometen 12
    mappers cuando 7 son alias sin callers."""

    def test_mapper_names_excludes_dead_aliases(self) -> None:
        leaked = DEAD_ALIASES & set(MAPPER_NAMES)
        assert not leaked, (
            f"MAPPER_NAMES publica alias muertos: {sorted(leaked)}. "
            "MAPPER_NAMES es la guarda de recuento de mappers reales."
        )

    def test_mapper_names_is_exactly_the_live_mappers(self) -> None:
        assert set(MAPPER_NAMES) == LIVE_MAPPERS, (
            f"MAPPER_NAMES={sorted(MAPPER_NAMES)} != mappers reales {sorted(LIVE_MAPPERS)}"
        )

    def test_row_mappers_does_not_define_them(self) -> None:
        still_there = [n for n in sorted(DEAD_ALIASES) if hasattr(row_mappers, n)]
        assert not still_there, f"row_mappers.py todavia define: {still_there}"

    def test_row_mappers_all_excludes_them(self) -> None:
        leaked = DEAD_ALIASES & set(row_mappers.__all__)
        assert not leaked, f"row_mappers.__all__ publica alias muertos: {sorted(leaked)}"

    def test_storage_does_not_reexport_them(self) -> None:
        from skillgraph.platform import storage

        leaked = DEAD_ALIASES & set(storage.__all__)
        assert not leaked, f"storage.__all__ publica alias muertos: {sorted(leaked)}"

    def test_storage_does_not_hold_them(self) -> None:
        from skillgraph.platform import storage

        still_there = [n for n in sorted(DEAD_ALIASES) if hasattr(storage, n)]
        assert not still_there, f"platform.storage todavia reexporta: {still_there}"


class TestLiveMappersAreUntouched:
    """El otro lado de la samurai: el borrado no puede tocar los 5."""

    @pytest.mark.parametrize("name", sorted(LIVE_MAPPERS))
    def test_live_mapper_still_exists(self, name: str) -> None:
        assert hasattr(row_mappers, name), f"{name} es un mapper real y no debe desaparecer"

    def test_live_mapper_is_not_in_storage(self) -> None:
        """WI-86: el facade ya no los anuncia, y no por descuido.

        Este test bornia la samurai por el otro lado: que el borrado de
        WI-81 no tocara los 5 mappers reales. La garantia sigue, pero en
        WI-86 cambio de forma: los 5 viven en `row_mappers` y los 5
        consumidores los toman de ahi. `storage` deja de exponerlos, y
        que no vuelvan es parte del contrato.
        """
        from skillgraph.platform import storage

        for name in sorted(LIVE_MAPPERS):
            assert not hasattr(storage, name), (
                f"storage.{name} vuelve a estar reexportado: el facade no usa "
                f"ninguno de ellos y anunciarlos es superficie que no sostiene"
            )

    def test_uid_not_exported_by_storage(self) -> None:
        """`_uid` no es un mapper de fila, pero WI-86 lo movio con los demas.

        Antes lo consumia `storage`; ahora lo consume `knowledge_repository`
        directamente desde `row_mappers`. Lo que se vigila es que no
        aparezca una segunda copia.
        """
        from skillgraph.platform import knowledge_repository, storage

        assert not hasattr(storage, "_uid"), "storage vuelve a reexportar _uid"
        assert knowledge_repository._uid is row_mappers._uid
