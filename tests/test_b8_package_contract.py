"""B8 — el contrato de paquete, y la pregunta de si encaja aqui.

QUE MIDE ESTE FICHERO, y por que ejecuta en vez de leer
-------------------------------------------------------
El gate de B8 pide un contrato para seis tipos de paquete, un aislamiento
progresivo y un formato `requires` explicito. Medido antes de escribir
nada (`scripts/measure_b8_package_contract.py`): **5 de 5 preguntas
abiertas**, y el hallazgo es que no habia manifiesto —solo un `Brick` con
`kind="DomainPack"`, que es el contrato de *tipos*, no el de *paquete*.

Estos tests fijan cuatro cosas, y las cuatro son decisiones:

1. **El manifiesto no puede mentir sobre si encaja.** Un pack que pide
   `>=0.30` y corre en 2.0 tiene que ser incompatible, y el motivo tiene
   que decir cual de las dos clausulas fallo. La comprobacion interesante
   no es «da error», es que el error sea *accionable*.

2. **`PACK_KINDS` se deriva, no se escribe.** Un test que lee el conjunto
   derivado y lo compara con el `Literal` no puede pasar si alguien
   escribe los seis a mano y luego anade un septimo al `Literal`: el
   conjunto derivado y el tipo dejarian de ser lo mismo.

3. **El aislamiento es una comparacion, no un adjetivo.**
   `es_al_menos("sandbox")` es una propiedad que se puede comprobar. El
   roadmap dice «aislamiento progresivo»; esto es lo que hace que
   «progresivo» sea verdad o mentira en vez de una promesa.

4. **El manifiesto no comparte memoria con quien lo lee.** Se construye
   desde un `dict` externo y se comprueba que mutar el `dict` despues no
   cambia el manifiesto — el mismo defecto de alias de WI-113, que en B7
   lo encontre `AgentResult.from_fixture` guardando el dict tal cual.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.packaging import (
    ISOLATION_LEVELS,
    PACK_KINDS,
    CapabilityRequirement,
    IncompatiblePackError,
    PackManifest,
    Requires,
    es_compatible,
    exigir_compatible,
    parse_manifest,
)
from skillgraph.platform.ports.capabilities import CAPABILITY_VERSION

RAIZ = Path(__file__).resolve().parent.parent

#: El manifiesto tal y como lo escribiría un autor, con el formato
#: exacto que declara el roadmap.
MANIFIESTO = {
    "name": "acme.git",
    "version": "1.2.0",
    "kind": "DomainPack",
    "isolation": "subprocess",
    "summary": "Tipos de recurso para repositorios git",
    "requires": {
        "skillgraph": ">=0.30,<1",
        "capabilities": ["code.analysis.v1", "git.read.v1"],
    },
}


def _manifiesto(**cambios) -> PackManifest:
    """Un manifiesto nuevo desde el formato del roadmap.

    Se copia `requires` EN PROFUNDO a proposito. Con un
    `{**MANIFIESTO, **cambios}` a secas, el `requires` es el MISMO dict
    del modulo, y un test que mutase la lista de capabilities estropeaba
    el fixture para todos los que ven despues. Paso por un fallo real:
    seis tests de «deberia encajar» donnant «falta la capability
    hackeado.v1», que es el nombre que habia puesto el test de alias.

    Es el mismo motivo por el que `parse_manifest` copia: un test que
    ensucia la entrada de otro test tiene el mismo defecto que el codigo
    que_aliasa_.
    """
    datos = {
        **MANIFIESTO,
        "requires": {
            **MANIFIESTO["requires"],
            "capabilities": list(MANIFIESTO["requires"]["capabilities"]),
        },
        **cambios,
    }
    return parse_manifest(datos)


# --- El manifiesto existe y es de primera clase ---------------------------


class TestElManifiestoEsDePrimeraClase:
    def test_se_lee_del_formato_que_declara_el_roadmap(self) -> None:
        """El formato del gate, tal cual, produce un manifiesto."""
        m = _manifiesto()
        assert m.name == "acme.git"
        assert m.version == "1.2.0"
        assert m.kind == "DomainPack"
        assert m.requires.skillgraph == ">=0.30,<1"
        assert [c.type_name for c in m.requires.capabilities] == ["code.analysis.v1", "git.read.v1"]

    def test_la_version_de_la_capability_la_mete_el_puerto(self) -> None:
        """`code.analysis.v1` trae la `v1` del puerto, no una de la casa.

        B3 dejo `CAPABILITY_VERSION` en el puerto con un docstring que
        dice que esta ahi para que `requires.capabilities` de B8 tenga
        algo que versionar. Este test es la comprobacion de que eso paso.
        """
        m = _manifiesto()
        assert all(c.version == CAPABILITY_VERSION for c in m.requires.capabilities)

    def test_sin_requires_no_se_puede_leer(self) -> None:
        """Un manifiesto sin `requires` no se puede saber si encaja.

        Por eso `parse_manifest` lo rechaza en vez de devolver un
        manifiesto con un `requires` vacio que «encaja con todo». Un
        `requires` opcional seria un `requires` que no protege de nada.
        """
        datos = {k: v for k, v in MANIFIESTO.items() if k != "requires"}
        with pytest.raises(ValidationError) as exc:
            parse_manifest(datos)
        assert "requires" in str(exc.value)

    def test_pack_kinds_tiene_los_seis_del_roadmap(self) -> None:
        assert (
            frozenset(
                {
                    "SkillPackage",
                    "ControllerPackage",
                    "CapabilityAdapter",
                    "DomainPack",
                    "PolicyPack",
                    "UIWidget",
                }
            )
            == PACK_KINDS
        )

    def test_pack_kinds_esta_derivado_y_no_escrito(self) -> None:
        """El conjunto tiene que SEGUIR al tipo, no coincidir con el hoy.

        Se importa el `PackKind` del modulo y se compara con lo que
        declara `PACK_KINDS`. Si alguien escribe los seis a mano y luego
        anade un septimo valor al `Literal`, este test se pone rojo: el
        conjunto derivado dejaria de contener lo que el tipo acepta, que
        es el error de QW-E («un conjunto literal se queda corto cuando
        el Literal crece y la validacion rechaza el valor nuevo que el
        tipo si acepta»).
        """
        from typing import get_args

        from skillgraph.packaging.manifest import PackKind

        assert frozenset(get_args(PackKind)) == PACK_KINDS


# --- El manifiesto no comparte memoria con quien lo lee -------------------


class TestElManifiestoNoAliasaLaEntrada:
    def test_mutar_el_dict_externo_no_altera_el_manifiesto(self) -> None:
        """El manifiesto no comparte memoria con quien lo lee.

        Se comprueba sobre `name`, que es el campo que un `dict` externo
        podria dejar de compartir.

        **Y no sobre `requires.skillgraph`, aunque se podia.** Esa
        asercion existia, y es un test que NO PUEDE FALLAR: los strings
        son inmutables en Python, luego `Requires` ya tiene su propia
        referencia al valor y reasignar la clave del dict externo no
        cambia nada del dataclass. Se quita porque un test que no puede
        fallar no mide nada: da verde con el codigo roto y ocupa el
        sitio de una comprobacion que si podria fallar.

        Donde el alias SI es posible esta en los dos tests siguientes:
        la lista de capabilities, que es mutable, y `metadatos`, que es
        un mapping.
        """
        externo = {**MANIFIESTO, "requires": {**MANIFIESTO["requires"]}}
        m = parse_manifest(externo)
        externo["name"] = "otro"
        externo["requires"]["skillgraph"] = ">=99.0"
        assert m.name == "acme.git"
        assert m.requires.skillgraph == ">=0.30,<1"

    def test_mutar_el_manifiesto_fuera_no_altera_el_manifiesto(self) -> None:
        """`metadatos` es un mapping y no un dict vivo.

        `frozen=True` congela el ENLACE del atributo, no su valor: con
        `metadatos: dict`, el manifiesto sigue siendo mutable por dentro
        (WI-111). Se comprueba escribiendo, y no leyendo el tipo.
        """
        m = _manifiesto(metadata={"origen": "test"})
        with pytest.raises(TypeError):
            m.metadatos["origen"] = "otro"  # type: ignore[index]
        assert m.metadatos["origen"] == "test"

    def test_la_lista_de_capabilities_del_fuente_no_se_escapa(self) -> None:
        externo = {**MANIFIESTO, "requires": {**MANIFIESTO["requires"]}}
        caps = list(externo["requires"]["capabilities"])
        externo["requires"]["capabilities"] = caps
        m = parse_manifest(externo)
        caps.append("hackeado.v1")
        assert len(m.requires.capabilities) == 2


# --- La pregunta: ¿encaja? -----------------------------------------------


class TestLaPreguntaDeCompatibilidad:
    def test_encaja_cuando_todo_cumple(self) -> None:
        m = _manifiesto()
        motivos = es_compatible(
            m,
            skillgraph_version="0.30.0",
            capacidades_disponibles=(("code.analysis.v1", "v1"), ("git.read.v1", "v1")),
        )
        assert motivos == ()

    def test_la_version_incorrecta_dice_cual_era_la_esperada(self) -> None:
        """El motivo tiene que ser accionable, no un «no encaja».

        Un `bool` obligaba a quien pregunta a volver a mirar el
        manifiesto. El motivo es la mitad del trabajo: `no encaja» no le
        dice al operador si le falta una capability o si su SkillGraph es
        viejo.

        Se pasan las capabilities QUE SÍ están para que la version sea
        la unica variable: si no, el motivo seria «version + dos
        capabilities que faltan» y la asercion no distinguiria un motivo
        bien escrito de uno que solo sale porque hay de mas.
        """
        m = _manifiesto()
        motivos = es_compatible(
            m,
            skillgraph_version="2.0.0",
            capacidades_disponibles=(("code.analysis.v1", "v1"), ("git.read.v1", "v1")),
        )
        assert len(motivos) == 1
        assert ">=0.30,<1" in motivos[0]
        assert "2.0.0" in motivos[0]

    def test_una_capability_que_falta_se_dice_por_su_nombre(self) -> None:
        m = _manifiesto()
        motivos = es_compatible(
            m,
            skillgraph_version="0.30.0",
            capacidades_disponibles=(("code.analysis.v1", "v1"),),
        )
        assert len(motivos) == 1
        assert "git.read.v1" in motivos[0]
        assert "falta" in motivos[0]

    def test_una_capability_con_otra_version_no_cuenta_como_que_este(self) -> None:
        """Tenerla no basta: tiene que ser LA version.

        Si `code.analysis.v1@v2` estuviera instalada y el pack pidiera
        `v1`, aceptar el pack «porque la capability esta» seria el
        fallo mas caro de esta pieza: el pack se instala, y falla mas
        tarde y en un sitio que no es el del pack.
        """
        m = _manifiesto()
        motivos = es_compatible(
            m,
            skillgraph_version="0.30.0",
            capacidades_disponibles=(("code.analysis.v1", "v2"), ("git.read.v1", "v1")),
        )
        assert len(motivos) == 1
        assert "code.analysis.v1" in motivos[0]
        assert "v1" in motivos[0] and "v2" in motivos[0]

    def test_las_clausulas_se_cumplen_todas_y_no_una(self) -> None:
        """`>=0.30,<1` es un AND, no un OR.

        El error clasico de un parser de requisitos: con `or`, 2.0
        cumple `>=0.30` y por tanto cumple el requisito entero. Esta
        asercion falla con un `or` y por eso existe.

        Se pasan las capabilities para aislar la version, que es la
        variable de este test.
        """
        m = _manifiesto()
        caps = (("code.analysis.v1", "v1"), ("git.read.v1", "v1"))
        assert es_compatible(m, skillgraph_version="2.0.0", capacidades_disponibles=caps) != ()
        assert es_compatible(m, skillgraph_version="0.10.0", capacidades_disponibles=caps) != ()
        assert es_compatible(m, skillgraph_version="0.99.9", capacidades_disponibles=caps) == ()
        # Y el limite de la clausula es el que dice, no el del redondeo.
        assert es_compatible(m, skillgraph_version="1.0.0", capacidades_disponibles=caps) != ()

    def test_el_formato_del_gate_se_interpreta_como_lo_que_quiere_decir(self) -> None:
        """`>=0.30,<1` son dos clausulas parciales, y las dos cuentan.

        El enunciado de B8 escribe `">=0.30,<1"`, que MEZCLA `>=0.30` —dos
        componentes— y `<1` —uno solo—. Un parser que exigiera `X.Y` o
        SemVer completo rechazaria una de las dos y haria que NINGUN pack
        encajara contra el formato del gate. Este test se puso rojo por
        eso, seis veces a la vez, y por eso existe.
        """
        m = _manifiesto()
        caps = (("code.analysis.v1", "v1"), ("git.read.v1", "v1"))
        for version in ("0.30.0", "0.30", "0.99.9", "0.31.4"):
            assert es_compatible(m, skillgraph_version=version, capacidades_disponibles=caps) == ()
        for version in ("0.29.9", "1.0.0", "2.0.0"):
            assert es_compatible(m, skillgraph_version=version, capacidades_disponibles=caps) != ()

    def test_un_requisito_ilegible_no_se_cumple(self) -> None:
        """Un requisito que no se puede interpretar NO protege de nada.

        Aceptarlo en silencio seria peor que rechazarlo: el pack se
        instala sobre una base que el autor del requisito no quiso.
        """
        m = _manifiesto(requires={"skillgraph": ">=0.30,~=1"})
        motivos = es_compatible(m, skillgraph_version="0.30.0")
        assert len(motivos) == 1

    def test_la_version_actual_ilegible_no_cumple(self) -> None:
        m = _manifiesto()
        assert es_compatible(m, skillgraph_version="no-es-version") != ()

    def test_los_motivos_son_deterministas(self) -> None:
        """Dos llamadas iguales dan la misma lista, en el mismo orden.

        Un mensaje de error que cambia de orden entre ejecuciones no se
        puede comparar ni copiar en un ticket.
        """
        m = _manifiesto()
        kwargs = {
            "skillgraph_version": "0.1.0",
            "capacidades_disponibles": (("git.read.v1", "v1"),),
        }
        assert es_compatible(m, **kwargs) == es_compatible(m, **kwargs)  # type: ignore[arg-type]

    def test_exigir_compatible_levanta_un_error_de_dominio_con_code(self) -> None:
        """El error es del dominio y con `code` PROPIO.

        Dos errores con el mismo `code` no pueden salir con exit codes
        distintos, y entonces el `code` deja de ser la clave con la que se
        traduce (WI-109).
        """
        m = _manifiesto()
        with pytest.raises(IncompatiblePackError) as exc:
            exigir_compatible(m, skillgraph_version="2.0.0")
        assert isinstance(exc.value, SkillGraphError)
        assert exc.value.code == "sg_incompatible_pack"
        assert IncompatiblePackError.code != ValidationError.code

    def test_exigir_compatible_no_levanta_cuando_encaja(self) -> None:
        m = _manifiesto()
        exigir_compatible(
            m,
            skillgraph_version="0.30.0",
            capacidades_disponibles=(("code.analysis.v1", "v1"), ("git.read.v1", "v1")),
        )

    def test_el_motivo_del_error_es_el_mismo_que_devuelve_la_consulta(self) -> None:
        """La que lanza y la que devuelve se calculan con UNA llamada.

        Dos funciones que dicen «no» y «por que», calculadas por
        separado, son dos medidas del mismo hecho, y dos medidas pueden
        discrepar.
        """
        m = _manifiesto()
        with pytest.raises(IncompatiblePackError) as exc:
            exigir_compatible(m, skillgraph_version="0.1.0")
        esperados = es_compatible(m, skillgraph_version="0.1.0")
        for motivo in esperados:
            assert motivo in str(exc.value)


# --- El aislamiento es una comparacion, no un adjetivo --------------------


class TestElAislamientoEsUnaComparacion:
    def test_los_tres_niveles_estan_en_orden_de_aislamiento_creciente(self) -> None:
        assert ISOLATION_LEVELS == ("declarative", "subprocess", "sandbox")

    def test_un_nivel_mayor_es_al_menos(self) -> None:
        """`progresivo` se vuelve una propiedad que se puede comprobar."""
        alto = _manifiesto(isolation="sandbox")
        assert alto.es_al_menos("declarative")
        assert alto.es_al_menos("sandbox")

    def test_un_nivel_menor_no_cumple_el_mayor(self) -> None:
        bajo = _manifiesto(isolation="declarative")
        assert not bajo.es_al_menos("subprocess")
        assert not bajo.es_al_menos("sandbox")
        assert bajo.es_al_menos("declarative")

    def test_un_nivel_inexistente_no_revienta_con_keyerror(self) -> None:
        """Un vocabulario distinto no puede salir como traza.

        Quien pregunta puede tener una version de SkillGraph cuyo
        vocabulario de aislamiento no es este. Eso es una situacion de
        despliegue, no un error de programacion, y sale como
        `IncompatiblePackError`, no como `KeyError` (WI-109).
        """
        m = _manifiesto()
        assert m.es_al_menos("contenedor") is False  # type: ignore[arg-type]

    def test_aislar_mas_se_puede_comprobar_con_una_expresion(self) -> None:
        """El caso de uso real: «este pack tiene que ir en sandbox».

        Y este test nacio con un `pytest.skip` «si el contrato perdio la
        progresion». Escribir eso es ESCONDER un fallo, que es lo que
        `AGENTS.md` 6.2 prohibe y lo que `test_wi108_zero_skips.py` caza.
        Lo mas grave no era el skip: era que estaba ahi porque la
        asercion de verdad —«un pack declarativo NO llega a sandbox»—
        no se habia escrito, y en su lugar se puso un guard que salta
        justo cuando la propiedad se rompe.

        Ahora son dos aserciones y ninguna se salta.
        """
        declarativo = _manifiesto(isolation="declarative")
        sandbox = _manifiesto(isolation="sandbox")
        assert not declarativo.es_al_menos("sandbox")
        assert sandbox.es_al_menos("sandbox")


# --- El contrato rechaza lo que no encaja, con un motivo ------------------


class TestElContratoRechazaLoMalFormado:
    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("name", "Con Espacios"),
            ("name", ""),
            ("version", "1.2"),
            ("version", "uno.dos.tres"),
            ("kind", "NoEsUnPack"),
            ("isolation", "vm"),
        ],
    )
    def test_campo_invalido_dice_cual_y_que_se_esperaba(self, campo: str, valor: str) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest({**MANIFIESTO, campo: valor})
        mensaje = str(exc.value)
        assert campo in mensaje or valor in mensaje

    def test_requires_que_no_es_mapping_dice_lo_que_esperaba(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest({**MANIFIESTO, "requires": [">=0.30"]})
        assert "requires" in str(exc.value)

    def test_requires_sin_version_dice_que_hace_falta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest({**MANIFIESTO, "requires": {"capabilities": []}})
        assert "skillgraph" in str(exc.value)

    def test_una_capability_no_string_no_pasa(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest(
                {**MANIFIESTO, "requires": {"skillgraph": ">=0.30", "capabilities": [7]}}
            )
        assert "capability" in str(exc.value)

    def test_el_manifiesto_es_comparable_por_valor(self) -> None:
        """Dos manifiestos iguales son el mismo paquete.

        Es lo que permite que un registro detecte que dos packs se
        solapan en vez de aceptarlos en silencio.
        """
        assert _manifiesto() == _manifiesto()
        assert _manifiesto() != _manifiesto(name="otro.git")

    def test_es_inmutable(self) -> None:
        m = _manifiesto()
        with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
            m.name = "otro"  # type: ignore[misc]

    def test_requiere_acepta_una_capability_por_tupla(self) -> None:
        """La lista del YAML llega a memoria como tupla.

        Un `list` dentro de un dataclass `frozen` es mutable por dentro
        (WI-111), y un manifiesto que se puede cambiar desde fuera no es
        un manifiesto.
        """
        r = Requires(skillgraph=">=1", capabilities=(CapabilityRequirement("a.v1"),))
        assert isinstance(r.capabilities, tuple)


# --- Las ramas de validacion que sostienen el contrato --------------------


class TestLasValidacionesDelContrato:
    """Cada rama de `__post_init__` tiene un error con su motivo.

    No es cobertura por cobertura: es que estas ramas son la unica cosa
    que separa «el manifiesto dice la verdad» de «el manifiesto acepta
    cualquier cosa». Una rama de validacion sin test es una rama que
    solo se ejecuta cuando algo ya esta mal.
    """

    def test_una_capability_sin_nombre_no_se_acepta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            CapabilityRequirement(type_name="  ")
        assert "type_name" in str(exc.value)

    def test_una_capability_sin_version_no_se_acepta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            CapabilityRequirement(type_name="a.v1", version="")
        assert "version" in str(exc.value)

    def test_requires_sin_version_de_skillgraph_no_se_acepta(self) -> None:
        with pytest.raises(ValidationError) as exc:
            Requires(skillgraph="   ")
        assert "skillgraph" in str(exc.value)

    def test_requires_no_acepta_una_capability_que_no_lo_es(self) -> None:
        """Una tupla de cosas que NO son `CapabilityRequirement` no vale.

        Sin esta comprobacion, `requires.capabilities: ("texto",)` pasaria
        la construccion y reventaria mas tarde, en `es_compatible`, con
        un `AttributeError` en vez de un error de dominio.
        """
        with pytest.raises(ValidationError) as exc:
            Requires(skillgraph=">=1", capabilities=("code.analysis.v1",))  # type: ignore[arg-type]
        assert "CapabilityRequirement" in str(exc.value)

    def test_requires_sin_capabilities_se_describe_sin_ellas(self) -> None:
        """`describe` no inventa una lista de capabilities vacia con comas.

        El mensaje acaba en la version de skillgraph, sin «y» colgando:
        un mensaje con una cola de una lista vacia parece un error de
        formato en el mensaje.
        """
        assert Requires(skillgraph=">=1").describe() == "skillgraph >=1"

    def test_requires_con_capabilities_las_nombra_todas(self) -> None:
        r = Requires(
            skillgraph=">=1",
            capabilities=(CapabilityRequirement("a.v1"), CapabilityRequirement("b.v1")),
        )
        assert r.describe() == "skillgraph >=1 y a.v1@v1, b.v1@v1"

    def test_manifest_necesita_que_requires_sea_requires(self) -> None:
        with pytest.raises(ValidationError) as exc:
            PackManifest(
                name="a", version="1.0.0", kind="DomainPack", requires={"skillgraph": ">=1"}
            )  # type: ignore[arg-type]
        assert "Requires" in str(exc.value)

    def test_un_manifiesto_que_no_es_mapping_lo_dice(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest(["no", "es", "un", "manifest"])  # type: ignore[arg-type]
        assert "mapping" in str(exc.value)

    def test_to_dict_devuelve_el_manifesto_completo(self) -> None:
        """El round-trip es lo que permite guardarlo y volver a leerlo."""
        m = _manifiesto(metadata={"origen": "test"})
        carga = m.to_dict()
        assert carga["name"] == "acme.git"
        assert carga["kind"] == "DomainPack"
        assert carga["isolation"] == "subprocess"
        assert carga["requires"]["skillgraph"] == ">=0.30,<1"
        assert carga["requires"]["capabilities"] == ["code.analysis.v1@v1", "git.read.v1@v1"]
        assert carga["metadata"] == {"origen": "test"}

    def test_una_capability_se_puede_declarar_como_mapa(self) -> None:
        """`{type_name, version}` es la forma explicita, y tambien vale.

        El formato corto (`a.v1`) es lo que se escribe a mano; el largo
        es lo que se genera. Los dos tienen que entrar por la misma
        puerta, y sobre todo tienen que GUARDAR lo mismo.
        """
        m = parse_manifest(
            {
                **MANIFIESTO,
                "requires": {
                    "skillgraph": ">=0.30",
                    "capabilities": [{"type_name": "a.b.v2", "version": "v2"}],
                },
            }
        )
        assert m.requires.capabilities == (CapabilityRequirement("a.b.v2", "v2"),)

    def test_una_capability_como_mapa_sin_nombre_lo_dice(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest(
                {
                    **MANIFIESTO,
                    "requires": {"skillgraph": ">=0.30", "capabilities": [{"version": "v1"}]},
                }
            )
        assert "type_name" in str(exc.value)

    def test_una_capability_como_mapa_sin_version_valida_lo_dice(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest(
                {
                    **MANIFIESTO,
                    "requires": {
                        "skillgraph": ">=0.30",
                        "capabilities": [{"type_name": "a.b.v1", "version": 7}],
                    },
                }
            )
        assert "version" in str(exc.value)

    def test_la_forma_corta_trae_la_version_del_puerto(self) -> None:
        """`a.b.v1` y `{type_name: a.b.v1}` producen la MISMA requirement.

        Si las dos formas entran por puertas distintas, la comparacion
        contra lo instalado tendria dos formas de fallar.
        """
        corto = parse_manifest(
            {**MANIFIESTO, "requires": {"skillgraph": ">=0.30", "capabilities": ["a.b.v1"]}}
        ).requires.capabilities[0]
        largo = parse_manifest(
            {
                **MANIFIESTO,
                "requires": {
                    "skillgraph": ">=0.30",
                    "capabilities": [{"type_name": "a.b.v1", "version": "v1"}],
                },
            }
        ).requires.capabilities[0]
        assert corto == largo

    def test_una_capability_sin_version_toma_la_del_puerto(self) -> None:
        """`"code.analysis"` sin `@v1` usa la version del puerto.

        Es la forma mas corta que se puede escribir, y tiene que entrar
        por la misma puerta que las otras dos: si no, un pack escrito a
        mano compararia contra una version distinta de la que creeria.
        """
        m = parse_manifest(
            {**MANIFIESTO, "requires": {"skillgraph": ">=0.30", "capabilities": ["code.analysis"]}}
        )
        assert m.requires.capabilities == (CapabilityRequirement("code.analysis"),)
        assert m.requires.capabilities[0].version == CAPABILITY_VERSION

    def test_el_manifiesto_sobrevive_a_su_propio_round_trip(self) -> None:
        """`to_dict()` -> `parse_manifest()` da el MISMO manifiesto.

        Esto no es cosmetico: `to_dict` emite las capabilities como
        `tipo@version` —la forma larga escrita como string—, y si esa
        forma no vuelve por la puerta correcta, un manifiesto que se
        guarda en un registro y se vuelve a leer no es el mismo paquete
        que se quiso guardar. Y el fallo seria SILENCIOSO: compararia
        contra `tipo@version` en vez de contra `tipo`, que no esta
        instalado, y el operador veria «falta la capability» sin entender
        por que.
        """
        original = _manifiesto(metadata={"origen": "test"})
        recargado = parse_manifest(original.to_dict())
        assert recargado == original
        assert recargado.requires.capabilities == original.requires.capabilities

    def test_una_capability_vacia_no_pasa(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse_manifest(
                {**MANIFIESTO, "requires": {"skillgraph": ">=0.30", "capabilities": ["  "]}}
            )
        assert "capability" in str(exc.value)

    @pytest.mark.parametrize(
        "requisito, version, esperado",
        [
            (">=1.0.0", "1.0.0", True),
            (">=1.0.0", "0.9.9", False),
            ("<=1.0.0", "1.0.0", True),
            ("<=1.0.0", "1.0.1", False),
            (">1.0.0", "1.0.1", True),
            (">1.0.0", "1.0.0", False),
            ("<1.0.0", "0.9.9", True),
            ("<1.0.0", "1.0.0", False),
            ("==1.0.0", "1.0.0", True),
            ("==1.0.0", "1.0.1", False),
        ],
    )
    def test_cada_operador_significa_lo_que_dice(
        self, requisito: str, version: str, esperado: bool
    ) -> None:
        """Los cinco operadores, en las dos direcciones.

        Un operador mal implementado no falla nunca de forma ruidosa:
        devuelve `False` para todo, y eso se ve como «este pack no
        encaja», que es una respuesta CREÍBLE. Por eso se comprueban
        los cinco contra un valor que cumple y uno que no.
        """
        m = _manifiesto(requires={"skillgraph": requisito})
        motivos = es_compatible(m, skillgraph_version=version)
        assert (motivos == ()) is esperado, f"{version} contra {requisito}: {motivos}"


# --- El medidor sabe ver rojo --------------------------------------------


class TestElMedidorSabeVerRojo:
    def test_el_medidor_da_verde_en_el_arbol_real(self) -> None:
        proc = subprocess.run(
            [sys.executable, "scripts/measure_b8_package_contract.py"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_el_medidor_ve_rojo_si_se_quita_un_tipo_de_paquete(self, tmp_path: Path) -> None:
        """Sin uno de los seis, P4 tiene que bajar a rojo.

        Se copia SOLO `src/` y `scripts/`, que es lo que el medidor lee.
        Un clon minimo pesa poco y no depende de que `/tmp` tenga sitio:
        un guard que se pone rojo porque se lleno el disco no mide la
        propiedad, mide el almacenamiento (lo que paso en B7).
        """
        import shutil

        clon = tmp_path / "repo"
        for sub in ("src", "scripts"):
            shutil.copytree(
                RAIZ / sub,
                clon / sub,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        manifiesto = clon / "src" / "skillgraph" / "packaging" / "manifest.py"
        texto = manifiesto.read_text(encoding="utf-8")
        # Se quita UN valor del Literal; el conjunto derivado lo sigue.
        assert texto.count('    "PolicyPack",\n') == 1
        manifiesto.write_text(texto.replace('    "PolicyPack",\n', ""), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, "scripts/measure_b8_package_contract.py"],
            cwd=clon,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "P4" in proc.stdout

    def test_el_medidor_ve_rojo_si_desaparece_el_aislamiento(self, tmp_path: Path) -> None:
        """Sin `ISOLATION_LEVELS`, P5 tiene que bajar a rojo."""
        import shutil

        clon = tmp_path / "repo"
        for sub in ("src", "scripts"):
            shutil.copytree(
                RAIZ / sub,
                clon / sub,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        manifiesto = clon / "src" / "skillgraph" / "packaging" / "manifest.py"
        texto = manifiesto.read_text(encoding="utf-8")
        marcador = "ISOLATION_LEVELS: Final[tuple[str, ...]] = get_args(IsolationLevel)"
        assert texto.count(marcador) == 1
        manifiesto.write_text(
            texto.replace(marcador, "ISOLATION_LEVELS = ('declarative',)"), encoding="utf-8"
        )

        proc = subprocess.run(
            [sys.executable, "scripts/measure_b8_package_contract.py"],
            cwd=clon,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "P5" in proc.stdout
