"""Red de contrato WI-65 fase 1: el facade `Storage` hereda sus delegaciones.

Fija el contrato del corte 1 de WI-65 (ADR pendiente, mismos numeros
que el patron estrangulador de ADR-0016/WI-56):

1. Los 67 metodos de delegacion de ``Storage`` NO se redefinen en el
   cuerpo de la clase: se heredan de los cinco mixin por componente
   (``RunDelegations``, ``KnowledgeDelegations``,
   ``PromotionDelegations``, ``EventStoreDelegations``,
   ``PolicyDelegations``).
2. ``Storage.<metodo>`` es **la misma funcion** que
   ``<Mixin>.<metodo>``: identidad de funcion, no solo igualdad de
   comportamiento. Esto es lo que detecta una copia divergente.
3. La superficie publica de ``Storage`` no se pierde: los metodos
   siguen siendo alcanzables desde la clase. La cifra viva no es esta,
   es ``TestPublicSurfacePreserved.EXPECTED_PUBLIC``, y su motivo esta
   al lado; un numero en la prosa envejece sin que nadie lo note.
4. Los metodos con SQL vivo (los 7 que usan ``_conn``/``_tx``/
   ``_atomic``) **siguen definidos en ``Storage``**: los mixin solo
   anaden nombres, nunca los pisan (orden de resolucion MRO).
5. Cada mixin es disjunto: ningun metodo aparece en dos mixin, y cada
   mixin delega a un unico accessor (``self.<accessor>()``).

Tests de forma e identidad contra las clases reales. Sin mocks: la
red fija el contrato estructural, y el comportamiento observable de
los 67 metodos ya esta cubierto por la red existente de WI-56 y H9.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from skillgraph.platform.storage import Storage
from skillgraph.platform.storage_delegations import (
    EventStoreDelegations,
    KnowledgeDelegations,
    PolicyDelegations,
    PromotionDelegations,
    RunDelegations,
)

MIXINS: tuple[type, ...] = (
    RunDelegations,
    KnowledgeDelegations,
    PromotionDelegations,
    EventStoreDelegations,
    PolicyDelegations,
)

# Metodos con SQL vivo: deben SEGUIR definidos en el cuerpo de Storage.
# Derivado por AST del archivo original (1807 LoC, 80 metodos: 72
# publicos + 8 privados). No ampliar a mano: el test falla si el
# conjunto se desincroniza del archivo real.
LIVE_SQL_METHODS: frozenset[str] = frozenset(
    {
        "__init__",
        "close",
        "event_store",
        "_migrate",
        "_tx",
        "_atomic",
        "_insert_event_in_tx",
        "_atomic_state_and_event",
    }
)

ACCESSOR_BY_MIXIN: dict[str, str] = {
    "RunDelegations": "run_repository",
    "KnowledgeDelegations": "knowledge_repository",
    "PromotionDelegations": "promotion_repository",
    "EventStoreDelegations": "event_store",
    "PolicyDelegations": "policy_store",
}


def _public_methods(cls: type) -> tuple[str, ...]:
    """Nombres publicos definidos en el cuerpo de la clase.

    Cuenta tambien `@property`: ``inspect.isfunction`` devuelve False
    para un property, y excluirlos daria 73 en vez de los 74 reales
    (``uow`` es el unico property del facade).
    """
    return tuple(
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, property))
    )


def _mixin_methods(cls: type) -> tuple[str, ...]:
    return _public_methods(cls)


class TestDelegationsAreInherited:
    """REQ-WI65-1/I1: los metodos se heredan, no se redefinen."""

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_mixin_is_in_storage_mro(self, mixin: type) -> None:
        assert mixin in Storage.__mro__, (
            f"{mixin.__name__} no esta en el MRO de Storage: las "
            f"delegaciones no se han extraido todavia"
        )

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_mixin_methods_not_redefined_on_storage(self, mixin: type) -> None:
        redefined = [name for name in _mixin_methods(mixin) if name in vars(Storage)]
        assert not redefined, (
            f"{mixin.__name__} expone {redefined} que Storage vuelve a "
            f"definir: la delegacion esta duplicada, no heredada"
        )

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_storage_method_is_the_mixin_function(self, mixin: type) -> None:
        """Identidad de funcion: detecta copias divergentes."""
        for name in _mixin_methods(mixin):
            assert getattr(Storage, name) is getattr(mixin, name), (
                f"Storage.{name} no es identica a {mixin.__name__}.{name}"
            )

    @pytest.mark.parametrize("mixin", MIXINS, ids=lambda m: m.__name__)
    def test_storage_resolves_to_the_mixin_implementation(self, mixin: type) -> None:
        for name in _mixin_methods(mixin):
            resolved = getattr(Storage, name).__qualname__.split(".")[0]
            assert resolved == mixin.__name__, (
                f"Storage.{name} resuelve a {resolved}, no a {mixin.__name__}"
            )


class TestMixinsAreDisjoint:
    """REQ-WI65-2: cada metodo pertenece a un unico mixin."""

    def test_no_method_in_two_mixins(self) -> None:
        seen: dict[str, str] = {}
        for mixin in MIXINS:
            for name in _mixin_methods(mixin):
                assert name not in seen, f"{name} aparece en {seen.get(name)} y {mixin.__name__}"
                seen[name] = mixin.__name__
        # 65 -> 67 en B4, y el motivo vive aqui y no en el modulo: los dos
        # metodos que hacen alcanzable la mitad observada de un recurso
        # (`get_resource_status`, `update_resource_status`) se delegan
        # desde `KnowledgeDelegations` como cualquier otro. La
        # disyuncion es la propiedad; la cifra es la consequence, y sube
        # solo cuando un nombre nuevo entra en la red.
        assert len(seen) == 67, f"esperados 67 metodos, hay {len(seen)}"

    def test_each_mixin_delegates_to_exactly_one_accessor(self) -> None:
        """AST, no grep: los `return self.x(...)` multilinea no se leen
        con una comprehension de lineas."""
        from skillgraph.platform import storage_delegations

        tree = ast.parse(Path(storage_delegations.__file__).read_text())
        accessors = set(ACCESSOR_BY_MIXIN.values())
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            expected = ACCESSOR_BY_MIXIN[node.name]
            for fn in node.body:
                if not isinstance(fn, ast.FunctionDef) or fn.name.startswith("_"):
                    continue
                called = {
                    a.attr
                    for a in ast.walk(fn)
                    if isinstance(a, ast.Attribute)
                    and isinstance(a.value, ast.Name)
                    and a.value.id == "self"
                    and a.attr in accessors
                }
                assert called == {expected}, (
                    f"{node.name}.{fn.name} reenvia a {called or 'nada'}, "
                    f"esperado exactamente {{{expected!r}}}"
                )


class TestPublicSurfacePreserved:
    """REQ-WI65-3: la API publica de Storage no se pierde."""

    #: 72 -> 74 en B4, y el cambio es INTENCIONAL y esta nombrado: se
    #: anaden `update_resource_status` y `get_resource_status`, los dos
    #: unicos que hacen alcanzable la mitad observada de un recurso. La
    #: columna `status_json` estaba declarada `NOT NULL DEFAULT '{}'` y no
    #: habia ni un `UPDATE` en el repo, luego la superficie faltaba
    #: exactamente ahi. Sube +2 y no mas: si sube mas, es otro cambio.
    #:
    #: LO QUE ESTA GUARDA NO MIDE, medido el 2026-10-03: una cuenta ve
    #: CUANTOS metodos hay, no CUALES. Renombrar `get_resource_status` a
    #: `get_resource_status_renombrado` deja la cuenta en 74 y las tres
    #: guardas de superficie de este fichero en verde; se comprobo. La
    #: propiedad "el metodo correcto es el que esta ahi" la cubren los
    #: tests que lo LLAMAN por nombre (`tests/test_b4_observed_state.py`:
    #: 4 fallos bajo esa misma mutacion), no esta red. Por eso aqui no
    #: se deriva un conjunto de nombres: la cuenta es la property que
    #: esta red afirma, y afirmar mas seria mentira.
    EXPECTED_PUBLIC = 74
    # Solo los privados no-dunder: `__init__`/`__enter__`/`__exit__`
    # estan cubiertos por LIVE_SQL_METHODS y por `close`/`uow`.
    EXPECTED_PRIVATE = 5

    def test_el_numero_de_metodos_publicos_es_el_esperado(self) -> None:
        """El numero no va en el NOMBRE del test, y antes si iba.

        Se llamaba `test_storage_still_exposes_seventy_two_public_methods`.
        Al subir la superficie a 74, ese nombre mentia: un test cuyo nombre
        afirma un numero que ya no comprueba es la forma mas barata de
        perder el unico dato que el test tiene. El numero vive ahora en
        `EXPECTED_PUBLIC`, con el motivo del cambio al lado, y el nombre
        dice lo que el test hace.
        """
        inherited: set[str] = set()
        for mixin in MIXINS:
            inherited.update(_mixin_methods(mixin))
        own = set(_public_methods(Storage))
        public = own | inherited
        private = {
            n
            for n, v in vars(Storage).items()
            if n.startswith("_") and not n.startswith("__") and inspect.isfunction(v)
        }
        assert len(public) == self.EXPECTED_PUBLIC, (
            f"superficie publica cambio: {len(public)} metodos "
            f"(esperados {self.EXPECTED_PUBLIC}); own={len(own)}, "
            f"heredados={len(inherited)}"
        )
        assert len(private) == self.EXPECTED_PRIVATE, (
            f"metodos privados cambiados: {sorted(private)}"
        )

    def test_live_sql_methods_stay_on_storage(self) -> None:
        """REQ-WI65-4: los mixin anaden nombres, nunca los pisan."""
        for name in sorted(LIVE_SQL_METHODS):
            assert name in vars(Storage), f"{name} usa SQL vivo y debe seguir definido en Storage"

    def test_no_delegation_references_private_connection(self) -> None:
        """Los mixin no tocan ``_conn``: SQL vivo se queda en Storage."""
        for mixin in MIXINS:
            for name in _mixin_methods(mixin):
                body = inspect.getsource(getattr(mixin, name))
                assert "self._conn" not in body, (
                    f"{mixin.__name__}.{name} accede a self._conn: "
                    f"eso es SQL vivo y no pertenece a un mixin de delegacion"
                )
                assert "_tx()" not in body, f"{mixin.__name__}.{name} usa _tx()"
                assert "_atomic()" not in body, f"{mixin.__name__}.{name} usa _atomic()"


class TestReExportsArePreserved:
    """REQ-WI65-5: los DTO re-exportados por `storage` no desaparecen.

    Regresion real de este corte: al mover los 67 metodos, `Storage`
    dejo de usar internamente `StoredClaim`/`StoredEvidence`/
    `StoredRelation`/`StoredResource`, y `ruff --fix` los borro por
    F401. Siete modulos los importan **desde** `skillgraph.platform.
    storage` (el shim de compatibilidad del corte 1 de WI-56), asi que
    el borrado reventaba 61 tests de golpe sin tocar el facade.

    Esta clase fija la superficie de re-export para que un F401
    futuro falle aqui y no como un ImportError en otro modulo.
    """

    REEXPORTED_DTOS: tuple[str, ...] = (
        "StoredClaim",
        "StoredEvidence",
        "StoredRelation",
        "StoredResource",
    )

    @pytest.mark.parametrize("name", REEXPORTED_DTOS)
    def test_dto_is_importable_from_storage(self, name: str) -> None:
        module = __import__("skillgraph.platform.storage", fromlist=[name])
        assert hasattr(module, name), (
            f"{name} ya no se puede importar desde skillgraph.platform.storage; "
            f"los componentes de WI-56 dependen de este shim"
        )

    def test_reexported_dtos_are_declared_in_dunder_all(self) -> None:
        from skillgraph.platform import storage

        declared = set(storage.__all__)
        missing = set(self.REEXPORTED_DTOS) - declared
        assert not missing, (
            f"{sorted(missing)} se usan pero no estan en __all__: ruff los "
            f"borrara por F401 en cuanto Storage deje de referenciarlos"
        )

    def test_reexport_is_the_same_object_as_ports(self) -> None:
        """El shim no duplica: reexporta el MISMO objeto de `ports`."""
        from skillgraph.platform import ports, storage

        for name in self.REEXPORTED_DTOS:
            assert getattr(storage, name) is getattr(ports, name), (
                f"{name} diverge entre storage y ports"
            )

    def test_known_downstream_importers_resolve(self) -> None:
        """Los modulos que dependen del shim deben importar sin error."""
        import importlib

        for module_name in (
            "skillgraph.platform.knowledge_mappers",
            "skillgraph.platform.knowledge_claims",
            "skillgraph.platform.event_store",
            "skillgraph.platform.policy_store",
            "skillgraph.platform.run_repository",
            "skillgraph.platform.promotion_repository",
            "skillgraph.platform.knowledge_repository",
        ):
            importlib.import_module(module_name)


class TestExtractionIsVerifiable:
    """El corte debe reducir el archivo de forma medible y honesta."""

    def test_storage_module_shrank_below_its_pre_cut_size(self) -> None:
        module = Path(Storage.__module__.replace(".", "/") + ".py")
        path = Path(__file__).resolve().parent.parent / "src" / module
        loc = len(path.read_text().splitlines())
        assert loc < 1807, f"storage.py sigue en {loc} LoC: el corte no ocurrio"

    def test_delegation_module_defines_no_surprising_top_level_state(self) -> None:
        """WI-65 metio los cinco mixin en un modulo; WI-68 los desdoblo en
        uno por componente y dejo este como indice de re-export. Lo que
        se sigue exigiendo aqui es que **no** vuelva a definirse una
        clase aqui: el indice reexporta, no reproduce. El resto del
        contrato de WI-68 esta en `test_wi68_storage_delegations_split`.
        """
        from skillgraph.platform import storage_delegations

        path = Path(storage_delegations.__file__)
        tree = ast.parse(path.read_text())
        assert not [n for n in tree.body if isinstance(n, ast.ClassDef)], (
            "el indice de WI-68 no debe definir ninguna clase: reexporta"
        )
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pytest.fail(f"funcion libre no prevista: {node.name}")
