"""`context_controller.py`: las validaciones que no tienen quien las mire.

**LA MEDIDA QUE ABRE ESTE TRABAJO.** `knowledge/context_controller.py` mide
**89,35 %** sobre el suelo del 90 % que AGENTS 6.3 declara para todo paquete.
El gap es de 0,65 puntos, y ese numero es el que hace que este trabajo sea
distinto de los otros tres de este bloque.

Los otros tres eran modulos con un cuerpo entero sin ejecutar, y la respuesta
fue ejecutar el cuerpo. Aqui casi todo esta ejecutado; lo que falta son las
**validaciones de entrada** de una dataclass, que son cuatro lineas y ninguna
tiene test.

Y esa asimetria es el punto. Un modulo al 89 % parece casi cerrado, y bajando
el suelo un punto se cerraria. Lo que hacen estos tests es lo contrario:
miden las cuatro lineas que faltaban para poder decir que el modulo esta
cerrado, no que esta casi cerrado.

**LO QUE SE COMPRUEBA, Y POR QUE `Omision`.** `Omision` es lo que dice que
un recurso del handoff **no** cupo. Es informacion negativa: lo que el
operador lee para saber que se le esta ocultando algo. Un `Omision` con el
namespace vacio no se puede volver a pedir —es ruido—; con `chars=0` dice que
no se gasto nada y hace que quien lo lea dude de los demas; con el nombre
vacio es un hueco sin direccion.

Los tres son la misma clase de defecto —**una afirmacion negativa que no se
puede usar**— y por eso van en un test parametrizado y no en tres.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skillgraph.knowledge.context_controller import Omision


class TestOmisionEsUsableONoEsNada:
    """Las tres validaciones que un `Omision` incompleto no puede pasar.

    **POR QUE UN TEST PARAMETRIZADO Y NO TRES.** Las tres aserciones son la
    misma: «este campo obligatorio vacio lanza `ValidationError`». Escribirlas
    tres veces son tres sitios donde olvidarse de mirar uno, y el que se
    olvide pasa porque el parametro existe pero nadie mira su resultado.

    Se.parametriza porque la PROPIEDAD es una: ningun `Omision` incompleto se
    puede construir. Un cuarto campo obligatorio nuevo entra en la tabla y
    queda cubierto sin escribir un test.
    """

    @pytest.mark.parametrize(
        ("campo", "valores"),
        [
            ("kind", {"kind": "", "namespace": "ns", "name": "a", "chars": 1}),
            ("name", {"kind": "claim", "namespace": "ns", "name": "", "chars": 1}),
            ("chars", {"kind": "claim", "namespace": "ns", "name": "a", "chars": 0}),
        ],
        ids=["kind-vacio", "name-vacio", "chars-cero"],
    )
    def test_un_campo_que_lo_hace_ireferenciable_no_se_construye(
        self, campo: str, valores: dict[str, object]
    ) -> None:
        """El `namespace` vacio ya lo mide `test_b30_contexto.py`; estos son los otros.

        Se mide que el error sea de DOMINIO y no un `TypeError` o un
        `assert`. `ValidationError` es un `SkillGraphError` con `code`, y sin
        eso el mensaje sale como Traceback — que es el defecto que WI-109
        cerro para la entrada de la CLI, por el otro lado de la misma
        frontera: aqui el que falla es codigo interno, no el usuario, y por
        eso el cierre lo dio el constructor y no el handler.
        """
        from skillgraph.core.errors import SkillGraphError, ValidationError

        with pytest.raises(ValidationError) as exc:
            Omision(**valores)  # type: ignore[arg-type]

        assert isinstance(exc.value, SkillGraphError), (
            "un ValidationError que no cuelga de SkillGraphError no lo traduce "
            "el runner a exit code"
        )
        assert exc.value.code, "sin `code` el error no sabe a exit code"
        assert campo in str(exc.value), f"el error no dice QUE campo fallo ({campo}): {exc.value}"

    def test_chars_negativo_tambien_se_rechaza(self) -> None:
        """`chars` negativo es peor que cero: afirma que se omitio algo que no existe.

        El `__post_init__` usa `<= 0`, luego el caso `0` ya trae el negativo
        dentro. Se mide igual porque un `< 0` en vez de `<= 0` dejaria pasar
        el cero —que es el caso que el comentario del codigo nombra
        explicitamente— y ese test es el que lo distingue.
        """
        from skillgraph.core.errors import ValidationError

        with pytest.raises(ValidationError):
            Omision(kind="claim", namespace="ns", name="a", chars=-5)

    def test_una_omision_completa_es_referenciable(self) -> None:
        """El camino feliz, y con el porque: `como_tupla` es lo que viaja.

        Sin esto, los tres tests anteriores prueban que se rechaza lo malo y
        no prueban que se pueda construir lo bueno. Un `__post_init__` que
        rechazara todo pasa la tabla entera.
        """
        omision = Omision(kind="claim", namespace="ns", name="a", chars=7)

        assert omision.como_tupla() == ("claim", "ns", "a", 7)


class TestLaRamaQueNadieAlcanza:
    """`_resolve_one_selector` acaba en `return []`, y ese `[]` no lo ve nadie.

    **MEDIDO, NO SOSPECHADO.** La ultima linea del dispatcher es
    `return []` para un `kind` que no es `entity`, `predicate` ni `source`. La
    pregunta es si ese `kind` puede existir, y la respuesta esta en
    `core/recipe.py`: `ObligatorySelector.__post_init__` lanza si el `kind`
    no esta en el conjunto, luego el smart constructor no deja construir uno.

    Es el mismo caso que la rama `(sin eventos)` de `cmd_runs_logs` en
    WI-116-runs: defensa pura. La diferencia es que aqui se PUEDE medir la
    propiedad que la vuelve tal, y eso es lo que hace el test de abajo.

    Fabricar un `ObligatorySelector` con un kind imposible (por ejemplo
    saltandose `__post_init__` con `object.__new__`) para cubrir la linea
    seria medir una linea con un test que no puede pasar nada real.
    """

    def test_el_constructor_de_selectores_rechaza_un_kind_imposible(self) -> None:
        """La propiedad que hace inalcanzable el `return []` del dispatcher."""
        from skillgraph.core.errors import ValidationError
        from skillgraph.core.recipe import ObligatorySelector

        with pytest.raises(ValidationError, match="kind"):
            ObligatorySelector(kind="entidad", value="a")

    def test_los_tres_kinds_validos_pasan(self) -> None:
        """Y que la validacion no es «rechazar todo»: los tres del Literal pasan.

        Sin este, una tabla que rechazara cualquier `kind` cumpliria el test
        anterior y el sistema no resolveria ningun selector.
        """
        from skillgraph.core.recipe import ObligatorySelector

        for kind in ("entity", "predicate", "source"):
            sel = ObligatorySelector(kind=kind, value="v")  # type: ignore[arg-type]
            assert sel.kind == kind


class TestElSueloNoSeRelaja:
    """**POR QUE ESTE FICHERO NO TOCA `check_coverage_floors.py`.**

    `knowledge/` no esta en `SUELOS_ESPECIALES`: hereda el 90 % de AGENTS
    6.3. Un gap de 0,65 puntos es exactamente el tamaño del que se taparia
    subiendo el suelo a 89, y subirlo seria medir otra cosa.

    El contrasalto es que la regla siga PONIENDO: si alguien anade 300 lineas
    sin test, el gate tiene que volver a rojo. Un suelo que baja porque el
    codigo crece no mide cobertura, mide el dia que alguien se rindio.
    """

    def test_knowledge_no_tiene_suelo_especial(self) -> None:
        from scripts.check_coverage_floors import SUELOS_ESPECIALES

        assert "src/skillgraph/knowledge/" not in SUELOS_ESPECIALES, (
            "knowledge/ tiene suelo especial y este modulo medico el 90 % que "
            "hereda del paquete. Si el suelo es otro, el numero de este "
            "trabajo no mide lo que dice medir."
        )

    def test_el_fichero_que_cerro_el_namespace_sigue_aqui(self) -> None:
        """El caso ya cubierto sigue cubierto: este fichero no lo sustituye.

        `test_b30_contexto.py` mide `namespace` vacio. Si ese test se
        borrara, el parametro de este fichero no lo detectaria —esta tabla
        no incluye `namespace` a proposito, para no dar la sensacion de que
        lo cubre todo cuando hay dos ficheros en juego.
        """
        fuente = (Path(__file__).parent / "test_b30_contexto.py").read_text(encoding="utf-8")
        assert "test_la_omision_no_puede_quedar_SIN_NAMESPACE" in fuente, (
            "el test de namespace vacio desaparecio de test_b30_contexto.py y "
            "nadie lo vigila: esta tabla no lo cubre"
        )
