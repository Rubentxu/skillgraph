"""B28 — la autoridad se decide POR INTENCION, no hay un ranking global.

**LA MEDIDA QUE DIO NOMBRE AL BLOQUE.** `scripts/measure_b28_autoridad.py` ->
**5/5 ABIERTAS**. La fila del roadmap acusa de un «ranking global», y MEDIDO no
hay ranking: no hay nada. Lo que hay es otra cosa, y es la tentacion:

    AssertionOrigin = observed | derived-deterministically
                    | agent-inferred | human-asserted

Cuatro valores que ya estan en `core/runtime_types.py`, y cuyo docstring dice en
sus propias palabras que **no son un ranking** —son «quien afirma». Ordenarlos
es una linea, y el orden **depende de la pregunta**:

    ¿que devolvio produccion?        observed > derived-deterministically
    ¿que dependencia esta permitida? human-asserted > derived-deterministically

Por eso la propiedad del bloque no es «se elige alguien» sino **«el mismo
conflicto, con dos intenciones, elige afirmaciones DISTINTAS»**. Un resolver
con ranking fijo pasaria cualquier prueba que comprobara que hay ganador.

# QUE HACE ESTE COMPONENTE Y POR QUE NO ESTA EN `knowledge_conflicts.py`

B27 encuentra los conflictos; este los **resuelve para una pregunta**. Son dos
trabajos con dos preguntas distintas: *«¿hay algo que se contradiga?»* no
necesita intencion —o se contradice o no se contradice—, y *«¿cual creo?»* la
necesita siempre.

Ademas la resolucion es **PURA**: no lee disco, no mira el reloj y no conoce la
base. Por eso vive en `knowledge/` y no en `platform/`: el store entra ya
resuelto, en un `Conflicto`, que es lo unico que la politica necesita mirar.

# EL GUARD DEL AGENTE NO ES UNA POSICION EN LA TUPLA

El punto de este modulo que mas trabajo ha costado decidir. La spec (§7) dice
que `agent-inferred` «no puede por defecto cerrar conflicto», y la lectura
tentadora es ponerlo el ultimo de la preferencia. **Eso seria un guard roto**,
y por una razon concreta: se rompe **reordenando una lista**, que es el cambio
mas barato que puede hacer quien no sabe lo que hace, y solo en el perfil
equivocado.

Aqui el guard es un campo explicito (`permitir_inferencia_de_agente`) con
default `False`. MEDIDO en `TestElAgenteNoCierraElConflicto`: un perfil que
pone al agente PRIMERO sigue sin dejarle ganar. El opt-in existe y es
auditable —una linea que dice «en esta politica un agente puede cerrar»— pero
lo concede quien escribe la politica, no el modulo.

# LO QUE ESTE MODULO NO HACE

1. **NO BORRA.** Resolver para una intencion no elimina afirmaciones: las dos
   siguen ahi y siguen siendo consultables. Lo que las borra es B29, con
   ventanas de vigencia.
2. **NO PERSISTE.** La resolucion se calcula y se devuelve. Guardarla es
   trabajo de B29/B34, y hacerlo aqui convertiria una funcion pura en una que
   escribe.
3. **NO ELIGE ENTRE PERFILES.** `resolver` recibe una intencion y usa el perfil
   por defecto; quien quiera su propia politica la pasa. La eleccion de
   «que politica uso para esta pregunta» es de quien pregunta, y es la misma
   linea que dice que no hay un ranking global.
"""

from __future__ import annotations

import typing
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from skillgraph.core.errors import (
    AuthorityProfileInvalido,
    PerfilIncoherenteError,
    UnknownQueryIntentError,
)
from skillgraph.core.runtime_types import ASSERTION_ORIGINS, AssertionOrigin
from skillgraph.knowledge.graph import Claim, Conflicto

__all__ = [
    "MOTIVOS_DESCARTE",
    "PERFILES_POR_DEFECTO",
    "QUERY_INTENTS",
    "AuthorityProfile",
    "Descartada",
    "MotivoDescarte",
    "QueryIntent",
    "Resolution",
    "query_intent",
    "resolver",
]


# ---------------------------------------------------------------------------
# La intencion: un ADT cerrado, no un prompt libre
# ---------------------------------------------------------------------------

QueryIntent = Literal[
    "actual_behavior",
    "intended_behavior",
    "structural_fact",
    "historical_fact",
    "risk_assessment",
    "change_impact",
    "explanation",
]
"""**PARA QUE SE PREGUNTA**, no **que se pregunta**.

La distincion importa porque es la que separa una regla de una discusion: si
este campo fuera el texto de la pregunta, dos consultas distintas podrian
compartir valor («¿que status devolvio produccion?» y «¿que status devolvio
staging?»), y la policy no podria ni distinguirlas ni decir que se contradicen.

Los siete valores son el «ADT inicial» de `05-SPEC` §3. **Nota de
procedencia:** el ejemplo B de la spec §2 usa `intended_architecture`, que no
esta en esa lista. Se sigue §3 por dos razones: es la lista normativa y
explicitamente cerrada, y `AGENTS.md` 2.1 exige ADR para crecer un `Literal`,
y el ADR que cubre esto (ADR-0028) no lo pide. Crecerlo seria inventar un valor
en el sitio donde mas se lee como verdad.
"""

QUERY_INTENTS: Final[frozenset[str]] = frozenset(typing.get_args(QueryIntent))
"""Derivado del ``Literal`` (regla QW-E de `SOURCE_KINDS`/`ASSERTION_ORIGINS`).

Un conjunto escrito a mano seria una segunda fuente de verdad que se
desincroniza en cuanto alguien anada un valor al ``Literal``, y la validacion
rechazaria el valor nuevo mientras el tipo lo acepta. B25 sufrio exactamente
esa divergencia, y por eso esta regla ya no se negocia.
"""


def query_intent(s: str) -> QueryIntent:
    """Smart constructor: valida y devuelve `QueryIntent` tipado.

    **POR QUE EXISTE Y NO BASTA CON EL `Literal`.** El `Literal` no se
    comprueba en runtime: con `from __future__ import annotations` una
    anotacion no valida nada, y un `Literal` sin comprobacion es decoracion.
    `AGENTS.md` 2.3 pide un constructor por `NewType`, y aqui es `Literal`
    pero el argumento es el mismo: **la frontera de fuera es un `str`**.

    Raises:
        UnknownQueryIntentError: si `s` no esta en el vocabulario.
    """
    if s not in QUERY_INTENTS:
        raise UnknownQueryIntentError(
            f"intencion de consulta {s!r} desconocida. Valores: {sorted(QUERY_INTENTS)}"
        )
    return typing.cast("QueryIntent", s)


# ---------------------------------------------------------------------------
# La politica: un ranking POR INTENCION
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthorityProfile:
    """Como se ordena la autoridad **para UNA pregunta**.

    **POR QUE UN PERFIL Y NO UN RUTA DE CODIGO.** El error que la spec quiere
    evitar es un unico orden global escrito en algun sitio. Un `Literal` de
    origenes ordenado por el modulo seria ese error con otro nombre: cambiarlo
    obligaria a cambiar el nucleo y a todo lo que ya se resolvio con el orden
    viejo.

    Un perfil es el orden **declarado por la politica**, con nombre, y quien
    pregunta puede traer el suyo. Eso es lo que hace que «la respuesta correcta
    depende de para que se pregunta» sea una propiedad del sistema y no una
    costumbre.
    """

    name: str
    intencion: QueryIntent
    #: **Ordenado, y el orden es el rango.** El primero manda. Tupla y no lista
    #: por `AGENTS.md` 1.1, y porque un perfil cuya preferencia se puede mutar
    #: desde fuera cambia de comportamiento sin que nadie lo note.
    preferencia: tuple[AssertionOrigin, ...]
    #: **EL GUARD DEL AGENTE, Y POR QUE ES UN CAMPO Y NO UNA POSICION.**
    #: Ver la nota del modulo: como ultima posicion, el guard se rompe
    #: reordenando una lista. Aqui es una declaracion, y por declaracion se
    #: audita. `False` por defecto = el opt-in es siempre el paso extra.
    permitir_inferencia_de_agente: bool = False

    def __post_init__(self) -> None:
        if not self.preferencia:
            raise AuthorityProfileInvalido(
                f"perfil {self.name!r} con preferencia vacia: no dice quien manda"
            )
        vistos: set[str] = set()
        for origen in self.preferencia:
            if origen not in ASSERTION_ORIGINS:
                raise AuthorityProfileInvalido(
                    f"perfil {self.name!r} declara el origen {origen!r}, "
                    f"que no existe. Valores: {sorted(ASSERTION_ORIGINS)}"
                )
            if origen in vistos:
                raise AuthorityProfileInvalido(
                    f"perfil {self.name!r} declara el origen {origen!r} dos veces: "
                    "una preferencia repetida no dice en que posicion manda"
                )
            vistos.add(origen)

    def rango_de(self, origen: AssertionOrigin) -> int | None:
        """La posicion de `origen` en el ranking, o `None` si no esta.

        `None` y «lo peor» NO son lo mismo, y por eso son dos valores: un
        origen que el perfil no menciona no es «el ultimo», es **una
        declaracion en contra**, y por eso se descarta con su propio motivo.
        """
        try:
            return self.preferencia.index(origen)
        except ValueError:
            return None


#: Los siete perfiles por defecto.
#:
#: **DOS ESTAN JUSTIFICADOS Y CINCO SON DECLARACIONES.** `actual_behavior` e
#: `intended_behavior` salen de los dos ejemplos trabajados de la spec (§2, A y
#: B), y de ahi salen sus ordenes concretas. Los otros cinco **no se derivan de
#: una regla**: son lecturas razonables del nombre de la intencion, escritas
#: aqui a proposito para que se puedan discutir y cambiar. Declararlo es lo que
#: separa una politica de un accident.
#:
#: Y el invariante que si se sostiene en los siete: **los cuatro origenes
#: estan NOMBRADOS**, y `agent-inferred` es el ultimo en todos.
#:
#: **LO QUE MIDO ESTO, Y POR QUE NO SE PUDO DEJAR SIN NOMBRAR.** La primera
#: version de estos siete perfiles listaba solo tres origenes, y la sonda M2 del
#: harness —que pone el flag del agente a `True`— **no fue cazada**. MEDIDO: en
#: P4 el motivo de descarte era `origen_no_preferido`, no el del guard, porque
#: `rango_de` devuelve `None` para un origen no listado y el agente perdia por
#: rango aunque el guard desapareciera.
#:
#: Es decir: **un origen no listado vale por una prohibicion silenciosa**, y
#: entonces P4 —que es el guard del bloque— pasaria aunque el guard se borrara.
#: Nombrar los cuatro convierte cada ranking en una declaracion completa: quien
#: lo lee sabe que el agente esta ultimo a proposito, y no de paso.
#:
#: Ponerlo el ultimo NO es lo que lo prohibe. Lo que lo prohibe es
#: `permitir_inferencia_de_agente=False`, y sigue valiendo aunque el orden
#: cambiara: `TestElAgenteNoCierraElConflicto` lo mide con un perfil que pone
#: al agente el PRIMERO.
PERFILES_POR_DEFECTO: Final[Mapping[QueryIntent, AuthorityProfile]] = MappingProxyType(
    {
        "actual_behavior": AuthorityProfile(
            name="comportamiento-real",
            # Spec §2 ejemplo A: runtime observation > reproducible test >
            # deterministic code analysis > docs.
            intencion="actual_behavior",
            preferencia=(
                "observed",
                "derived-deterministically",
                "human-asserted",
                "agent-inferred",
            ),
        ),
        "intended_behavior": AuthorityProfile(
            name="arquitectura-intencionada",
            # Spec §2 ejemplo B: accepted decision > executable policy >
            # current code observation. **El codigo puede estar violando la
            # arquitectura**, asi que «lo que se ve» no es lo que se decidio.
            intencion="intended_behavior",
            preferencia=(
                "human-asserted",
                "derived-deterministically",
                "observed",
                "agent-inferred",
            ),
        ),
        "structural_fact": AuthorityProfile(
            name="hecho-estructural",
            # Lo que se DEDUJO del codigo es mas estable que lo que alguien
            # vio, y mas estable que una opinion.
            intencion="structural_fact",
            preferencia=(
                "derived-deterministically",
                "observed",
                "human-asserted",
                "agent-inferred",
            ),
        ),
        "historical_fact": AuthorityProfile(
            name="hecho-historico",
            # Declaracion, no derivacion: «historico» no tiene un unico
            # origen winners sin saber que periodo se pregunta.
            intencion="historical_fact",
            preferencia=(
                "derived-deterministically",
                "observed",
                "human-asserted",
                "agent-inferred",
            ),
        ),
        "risk_assessment": AuthorityProfile(
            name="evaluacion-de-riesgo",
            # Declaracion: el riesgo lo evalua quien responde por el, y la
            # maquina aporta el hecho, no el juicio.
            intencion="risk_assessment",
            preferencia=(
                "human-asserted",
                "observed",
                "derived-deterministically",
                "agent-inferred",
            ),
        ),
        "change_impact": AuthorityProfile(
            name="impacto-del-cambio",
            # Declaracion: el impacto lo determina el analisis determinista
            # sobre el grafo, que es donde la maquina no se equivoca.
            intencion="change_impact",
            preferencia=(
                "derived-deterministically",
                "human-asserted",
                "observed",
                "agent-inferred",
            ),
        ),
        "explanation": AuthorityProfile(
            name="explicacion",
            # Declaracion: para explicar «por que», manda lo que se vio,
            # porque la pregunta es por una observacion concreta.
            intencion="explanation",
            preferencia=(
                "observed",
                "human-asserted",
                "derived-deterministically",
                "agent-inferred",
            ),
        ),
    }
)


# ---------------------------------------------------------------------------
# La resolucion: siempre explicable (spec §8)
# ---------------------------------------------------------------------------

MotivoDescarte = Literal[
    "origen_no_preferido",
    "cerrado_por_agente_no_permitido",
]
"""**POR QUE UNA AFIRMACION NO GANO.**

Es un `Literal` cerrado por la misma razon que `QueryIntent`: un motivo que sea
un string libre obliga a quien lo lee a interpretarlo, y una explicacion que hay
que interpretar no es una explicacion. La spec §8 pide poder contestar «por
que», y «por que» tiene que ser una palabra de un vocabulario cerrado.

**Y TIENE DOS VALORES, NO TRES. UN TERCERO ESTABA DECLARADO Y ERA INALCANZABLE,
MEDIDO POR LA COBERTURA.** Declaraba `empate_en_la_jerarquia`, con su rama en
`_motivo_de`. La cobertura del bloque la marco como linea no cubierta, y no era
un test que faltara: la rama **no se puede alcanzar**.

El razonamiento es corto y no admite excepciones. `_motivo_de` solo se llama
para afirmaciones que NO estan en `elegidas`. Y una afirmacion admisible que no
esta en `elegidas` solo puede estarlo porque su rango es **peor** que
`mejor_rango` — si fuera igual, estaria en `elegidas` por construccion. Luego
`rango > mejor_rango` siempre, y la rama del empate nunca corre.

Un empate NO produce un descarte: produce dos `elegidas` y
`sin_resolver=True`, que es la respuesta honesta — «estas dos son igual de
autoritativas y se contradicen». Declarar un motivo para eso habria producido
un valor que **nadie puede observar**, y un vocabulario cerrado con un valor
imposible es una promesa que el codigo no cumple: quien escriba
`if motivo == "empate_en_la_jerarquia"` tendria una rama muerta y no lo sabria.
"""

MOTIVOS_DESCARTE: Final[frozenset[str]] = frozenset(typing.get_args(MotivoDescarte))


@dataclass(frozen=True, slots=True)
class Descartada:
    """Una afirmacion que no gano, y el motivo por el que no gano.

    **`afirmacion` COMPLETA, no su `claim_id`.** Un id obliga a volver a la
    base para poder explicar nada, y una explicacion que exige una segunda
    consulta no se puede imprimir ni auditar. Cuesta memoria y ahorra una
    ida.
    """

    afirmacion: Claim
    motivo: MotivoDescarte


@dataclass(frozen=True, slots=True)
class Resolution:
    """La respuesta a UNA pregunta, con el porque de toda la respuesta.

    **LA ESTRUCTURA ES LA EXIGENCIA DE LA SPEC §8, CAMPO POR CAMPO:**

    | la spec pide            | aqui esta                |
    |-------------------------|--------------------------|
    | que claims compitieron  | `conflicto.afirmaciones` |
    | que policy se uso       | `perfil`                 |
    | que claims se eligieron | `elegidas`               |
    | que se descartaron      | `descartadas`            |
    | por que                 | `Descartada.motivo`      |

    **`elegidas` PUEDE ESTAR VACIA, Y ES LA RESPUESTA HONESTA.** Si todas las
    afirmaciones son del agente y la politica no lo permite, no hay ganador. Un
    resolver que devuelve algo siempre esta inventando autoridad donde no la
    hay, y esa invencion es invisible porque parece una respuesta.
    """

    conflicto: Conflicto
    perfil: str
    intencion: QueryIntent
    elegidas: tuple[Claim, ...]
    descartadas: tuple[Descartada, ...]

    @property
    def ganadora(self) -> Claim | None:
        """La unica que gano, o `None` si no gano ninguna.

        **Por que `None` y no la primera.** Dos afirmaciones del mismo mejor
        origen no se pueden desempatar con una politica que no los distingue:
        elegir una seria arbitrario, y «la primera que salio» es arbitrario con
        apariencia de regla.
        """
        if len(self.elegidas) != 1:
            return None
        return self.elegidas[0]

    @property
    def sin_resolver(self) -> bool:
        """La policy **no pudo** elegir una sola. Un empate es `True`.

        No es «hubo conflicto»: es «hubo conflicto y no supe quien gana», que
        son cosas distintas y se contestan distinto.
        """
        return len(self.elegidas) != 1

    @property
    def firma(self) -> tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]]:
        """**La decision, comparable entre resoluciones.**

        **POR QUE NO COMPARAR LA `Resolution` ENTERA.** La `Resolution` lleva
        `conflicto`, que es la **entrada**: dos consultas del mismo conflicto
        con las afirmaciones en distinto orden son dos `Resolution` distintas
        por `__eq__` aunque decidan lo mismo. Y «deciden lo mismo» es
        justamente la propiedad que hay que medir —es P5 del instrumento—,
        asi que medirla comparando un campo que no es la decision seria
        medirla mal.

        Ademas es lo que ADR-0028 pide que se pueda referenciar: *«toda
        resolucion persistida referencia la policy aplicada»*. Una tupla
        estable que nombra policy, intencion, elegido y descartado-con-motivo
        es lo que se persiste y lo que dos consultas tienen que coincidir.
        """
        return (
            self.perfil,
            self.intencion,
            tuple(c.claim_id for c in self.elegidas),
            tuple((d.afirmacion.claim_id, d.motivo) for d in self.descartadas),
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def _motivo_de(afirmacion: Claim, perfil: AuthorityProfile) -> MotivoDescarte:
    """Por que esta afirmacion no gano. Dos motivos, y la funcion es TOTAL.

    **POR QUE NO HAY UNA TERCERA RAMA, Y POR QUE ESO ES UNA DECISION DE DISENO.**
    Una afirmacion llega aqui solo si NO esta en `elegidas`, y `elegidas` es
    exactamente «lo admisible en el mejor rango». Luego:

    - si **no** es admisible, el motivo es el guard —que es una prohibicion,
      y va primero porque explica mas que una preferencia;
    - si **si** lo es, su rango es peor por construccion, y el motivo es el
      rango.

    Los dos casos cubren todo el dominio, luego no hay rama de empate, no hay
    `else`, y no hay invariante que comprobar. Una version anterior de esta
    funcion comparaba contra `mejor_rango` y **dejaba un `raise` para un caso
    que la cobertura demostro inalcanzable**; dos razones para no volver a
    ella. La primera es que un `raise AssertionError` en un fichero que el
    propio harness somete a mutacion es una forma de pedir que la sonda M5
    reviente el modulo —y una sonda que revienta el modulo no mide la
    propiedad, mide el fallo de la sonda—. La segunda es que el repositorio no
    tira `AssertionError` en ningun sitio, y `AGENTS.md` 1.2 manda errores
    tipados: un camino que no se puede recorrer no es un error de dominio,
    es codigo que no deberia existir.

    Que el motivo del guard vaya primero NO es cosmetico: si el perfil puso al
    agente el primero y aun asi no gana, decir «perdi por rango» seria falso, y
    «no gano por rango» sobre una prohibicion hide la unica razon por la que
    perdio.
    """
    if not _es_admisible(afirmacion, perfil):
        return "cerrado_por_agente_no_permitido"
    return "origen_no_preferido"


def resolver(
    conflicto: Conflicto,
    *,
    intencion: QueryIntent,
    perfil: AuthorityProfile | None = None,
) -> Resolution:
    """Resuelve `conflicto` **para `intencion`**, y dice como.

    **FUNCION PURA Y SIN I/O** (`AGENTS.md` 1.3): no lee disco, no mira el
    reloj y no conoce la base. Todo lo que necesita esta en el `Conflicto` que
    recibe, que es lo que hace que se pueda probar sin abrir un SQLite.

    **POR QUE EL RESULTADO NO DEPENDE DEL ORDEN DE ENTRADA.** El bucle de
    ELECCION no lee la lista: elige por `rango minimo` sobre el conjunto de
    afirmaciones. Y el bucle de `descartadas` ordena por `claim_id`, que es la
    misma clave estable que B27 garantiza en `conflicts_for`. Invertir la
    entrada no cambia nada, y eso se mide en vez de afirmarse.

    Args:
        conflicto: las afirmaciones que se contradicen. Las devuelve el
            detector de B27, y llegan ya ordenadas.
        intencion: la pregunta. Es lo que decide el ranking.
        perfil: la politica. Si se omite, la de `PERFILES_POR_DEFECTO` para
            esta intencion. Es el punto de extension del bloque: quien tiene
            una politica propia la trae.

    Returns:
        Una `Resolution` explicable. Sin ganador si la politica no puede
        elegir, y con el motivo en cada descarte.

    Raises:
        UnknownQueryIntentError: si `intencion` no esta en el vocabulario.
        PerfilIncoherenteError: si `perfil` responde a otra pregunta.
    """
    pregunta = query_intent(intencion)
    politica = perfil if perfil is not None else PERFILES_POR_DEFECTO[pregunta]
    if politica.intencion != pregunta:
        raise PerfilIncoherenteError(
            f"el perfil {politica.name!r} responde a {politica.intencion!r} y se le "
            f"pregunta por {pregunta!r}. Usarlo seria responder a una pregunta con "
            "la politica de otra"
        )

    candidatas = conflicto.afirmaciones
    if not candidatas:
        return Resolution(
            conflicto=conflicto,
            perfil=politica.name,
            intencion=pregunta,
            elegidas=(),
            descartadas=(),
        )

    mejor_rango = _mejor_rango(candidatas, politica)
    if mejor_rango is None:
        # Todo lo que hay esta vedado por el guard del agente: no hay ganador
        # y TODAS las afirmaciones se explican con el motivo del guard. El
        # `origen_no_preferido` seria mentira: no perdieron por rango.
        return Resolution(
            conflicto=conflicto,
            perfil=politica.name,
            intencion=pregunta,
            elegidas=(),
            descartadas=tuple(
                Descartada(afirmacion=c, motivo="cerrado_por_agente_no_permitido")
                for c in sorted(candidatas, key=lambda c: c.claim_id)
            ),
        )

    elegidas = tuple(
        sorted(
            (
                c
                for c in candidatas
                if _es_admisible(c, politica)
                and politica.rango_de(c.assertion_origin) == mejor_rango
            ),
            key=lambda c: c.claim_id,
        )
    )
    ids_elegidas = {c.claim_id for c in elegidas}
    descartadas = tuple(
        Descartada(afirmacion=c, motivo=_motivo_de(c, politica))
        for c in sorted(candidatas, key=lambda c: c.claim_id)
        if c.claim_id not in ids_elegidas
    )
    return Resolution(
        conflicto=conflicto,
        perfil=politica.name,
        intencion=pregunta,
        elegidas=elegidas,
        descartadas=descartadas,
    )


def _es_admisible(afirmacion: Claim, perfil: AuthorityProfile) -> bool:
    """El guard del agente, como **predicado**, separado del rango.

    Vive separado porque son dos reglas distintas con dos consecuencias
    distintas: el rango decide **cual** gana, y el guard decide si **alguien**
    puede ganar. Juntarlos seria hacer que la prohibition dependiera de un
    orden, y una prohibicion que depende de un orden se rompe ordenando.
    """
    return perfil.permitir_inferencia_de_agente or afirmacion.assertion_origin != "agent-inferred"


def _mejor_rango(candidatas: tuple[Claim, ...], perfil: AuthorityProfile) -> int | None:
    """El mejor rango ADMISIBLE, o `None` si no hay ninguna admisible.

    `None` significa «nadie puede ganar»: todas las afirmaciones admitidas por
    el rango estan vedadas por el guard. Es un caso de verdad y no un
    caso imposible — MEDIDO: dos afirmaciones de agente y ninguna mas.
    """
    rangos = [perfil.rango_de(c.assertion_origin) for c in candidatas if _es_admisible(c, perfil)]
    admisibles = [r for r in rangos if r is not None]
    return min(admisibles) if admisibles else None
