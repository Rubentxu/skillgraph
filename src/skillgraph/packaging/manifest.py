"""El contrato de un paquete, y la pregunta de si encaja aqui (B8).

Que es esto
-----------
El roadmap de B8 enumera siete frentes: seis tipos de paquete,
aislamiento progresivo, distribucion, upgrade, install/update/remove,
matriz de compatibilidad y un formato `requires` explicito. Siete no es
un bloque, y medirlos juntos daria un veredicto que no dice por donde
empezar.

Este modulo es **la pieza de la que los otros seis dependen**: el
manifiesto. Sin `requires` declarado no hay version que comparar; sin un
contrato versionado no hay `upgrade` que hacer; y sin contrato no hay
`install`/`update`/`remove` que valgan como algo mas que copiar ficheros.

Tres decisiones, y las tres son correcciones de cosas que ya existian
-------

1. **`PACK_KINDS` se DERIVA por `get_args`, nunca se escribe a mano.** Un
   conjunto literal se queda corto en cuanto el `Literal` crece, y
   entonces el validador rechaza el valor nuevo que el propio tipo acepta:
   el codigo dice que el tipo es valido y el dominio dice que no. Es el
   error de QW-E, y ya se pago una vez en B6.

2. **La version de la capability la hereda del puerto, no la escribe el
   adaptador.** `CAPABILITY_VERSION` vive en
   `platform/ports/capabilities.py` desde B3, con un docstring que dice
   literalmente que esta aqui "para que `requires.capabilities` de B8
   tenga algo que versionar". Si la version viviera en cada adaptador,
   cada uno inventaria la suya y no habria nada que comparar.

3. **`ISOLATION_LEVELS` es una tupla ORDENADA, no un conjunto.** El
   orden es el contenido: `declarative` < `subprocess` < `sandbox`
   significa "cada nivel es al menos tan aislado como el anterior", y
   un `frozenset` no puede expresar eso. El roadmap dice "aislamiento
   progresivo segun riesgo", y la progresion es el punto.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal, get_args

from skillgraph.core.errors import SkillGraphError, ValidationError
from skillgraph.platform.ports.capabilities import CAPABILITY_VERSION

#: Los seis tipos de paquete del enunciado de B8. Todos, no solo
#: `DomainPack`: un contrato que solo conoce uno de los seis no es el
#: contrato del ecosistema, es el contrato de un caso.
PackKind = Literal[
    "SkillPackage",
    "ControllerPackage",
    "CapabilityAdapter",
    "DomainPack",
    "PolicyPack",
    "UIWidget",
]

#: Derivado, no escrito. Ver la decision 1 del docstring del modulo.
PACK_KINDS: Final[frozenset[str]] = frozenset(get_args(PackKind))

#: Aislamiento progresivo segun riesgo. El ORDEN es el contenido: ver la
#: decision 3.
IsolationLevel = Literal["declarative", "subprocess", "sandbox"]

ISOLATION_LEVELS: Final[tuple[str, ...]] = get_args(IsolationLevel)

#: Cuanto mas aislado, mas alto el indice. `sandbox` es el maximo y no se
#: puede superar, porque no hay un nivel por encima que siga siendo
#: "aislado" y no sea "otro proceso".
_RANGO_POR_NIVEL: Final[Mapping[str, int]] = MappingProxyType(
    {nivel: i for i, nivel in enumerate(ISOLATION_LEVELS)}
)

#: Un nombre de paquete: minusculas, digitos, `_` y `-`, separados por
#: punto para el namespace (`acme.git`, `acme-git`).
_NOMBRE_PACK: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

#: Un requisito de version de SkillGraph: `>=0.30,<1`, `>=1.0`, `==2.1.0`.
#:
#: Se admiten uno, dos o TRES componentes, y no es pereza. El propio
#: enunciado de B8 escribe `">=0.30,<1"`, que MEZCLA las dos formas
#: parciales: `>=0.30` tiene dos componentes y `<1` tiene uno. Un
#: parser que exigiera `X.Y` rechazaba el segundo, y uno que exigiera
#: SemVer completo rechazaria el primero — que es exactamente lo que
#: paso, y lo cazaron seis tests a la vez—. Lo que falta se completa a
#: `.0`, igual que en cualquier comparacion de versiones parciales:
#: `>=0.30` es `>=0.30.0` y `<1` es `<1.0.0`.
#:
#: `PackManifest.version` SI exige tres, porque la version del propio
#: pack si es completa; lo parcial son los REQUISITOS.
#:
#: Se soporta un subconjunto deliberadamente pequeno de Specifier. Los
#: operadores `!=` y `~=` se rechazan en vez de aceptarse a medias: un
#: requisito que se evalua con una semantica que el autor no conocia es
#: un requisito que se cumple o se incumple por accidente.
_REQUISITO_VERSION: Final[re.Pattern[str]] = re.compile(
    r"^(>=|<=|==|>|<)?(\d+)(?:\.(\d+))?(?:\.(\d+))?$"
)


class IncompatiblePackError(ValidationError):
    """Un pack no encaja en esta instalacion, y el motivo es concreto.

    `code` PROPIO y no compartido, por el motivo de WI-109: dos errores
    con el mismo `code` no pueden salir con exit codes distintos, y
    entonces el `code` deja de ser la clave con la que se traduce.
    """

    code = "sg_incompatible_pack"


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """Una capability que el pack necesita, con la version que espera.

    La `version` por defecto es la del PORTO, no una constante local. Ver
    la decision 2 del docstring del modulo.
    """

    type_name: str
    version: str = CAPABILITY_VERSION

    def __post_init__(self) -> None:
        if not self.type_name or not self.type_name.strip():
            raise ValidationError("CapabilityRequirement.type_name no puede estar vacio")
        if not self.version or not self.version.strip():
            raise ValidationError("CapabilityRequirement.version no puede estar vacia")

    def describe(self) -> str:
        return f"{self.type_name}@{self.version}"


@dataclass(frozen=True, slots=True)
class Requires:
    """Lo que el pack exige de la instalacion que lo va a alojar.

    Es una tupla, no un `dict`: un `dict` anidado dentro de un dataclass
    `frozen` es mutable por dentro, y `frozen=True` solo congela el
    ENLACE del atributo, no su valor. Es el error de WI-111.
    """

    skillgraph: str
    capabilities: tuple[CapabilityRequirement, ...] = ()

    def __post_init__(self) -> None:
        if not self.skillgraph or not self.skillgraph.strip():
            raise ValidationError("Requires.skillgraph no puede estar vacio")
        for cap in self.capabilities:
            if not isinstance(cap, CapabilityRequirement):
                raise ValidationError(
                    f"Requires.capabilities debe contener CapabilityRequirement, "
                    f"recibio {type(cap).__name__}"
                )

    def describe(self) -> str:
        if not self.capabilities:
            return f"skillgraph {self.skillgraph}"
        caps = ", ".join(c.describe() for c in self.capabilities)
        return f"skillgraph {self.skillgraph} y {caps}"


@dataclass(frozen=True, slots=True)
class PackManifest:
    """El manifiesto completo de un paquete.

    Inmutable y comparable por valor: dos manifiestos iguales son el
    mismo paquete, que es lo que permite que un registro detecte que dos
    packs se solapan en vez de aceptarlos en silencio.
    """

    name: str
    version: str
    kind: PackKind
    requires: Requires
    isolation: IsolationLevel = "declarative"
    summary: str = ""
    namespace: str = ""
    metadatos: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _NOMBRE_PACK.match(self.name):
            raise ValidationError(
                f"PackManifest.name invalido: {self.name!r}; se espera algo como "
                "'acme.git' o 'acme-git'"
            )
        if not re.match(r"^\d+\.\d+\.\d+$", self.version):
            raise ValidationError(
                f"PackManifest.version invalido: {self.version!r}; se espera MAJOR.MINOR.PATCH"
            )
        if self.kind not in PACK_KINDS:
            raise ValidationError(
                f"PackManifest.kind {self.kind!r} no es un tipo de paquete; "
                f"los seis son: {', '.join(sorted(PACK_KINDS))}"
            )
        if self.isolation not in _RANGO_POR_NIVEL:
            raise ValidationError(
                f"PackManifest.isolation {self.isolation!r} no es un nivel; "
                f"los tres, en orden de aislamiento creciente: "
                f"{', '.join(ISOLATION_LEVELS)}"
            )
        if not isinstance(self.requires, Requires):
            raise ValidationError(
                f"PackManifest.requires debe ser Requires, recibio {type(self.requires).__name__}"
            )
        object.__setattr__(self, "metadatos", MappingProxyType(dict(self.metadatos)))

    @property
    def nivel_de_aislamiento(self) -> int:
        """Cuanto mas aislado, mas alto. Comparable, no solo imprimible."""
        return _RANGO_POR_NIVEL[self.isolation]

    def es_al_menos(self, nivel: IsolationLevel) -> bool:
        """¿El pack se aisla al menos tanto como `nivel`?

        Comparacion por el indice y no por igualdad de cadena: es lo que
        convierte "progresivo" en una propiedad que se puede comprobar y
        no en un adjetivo.

        Un `nivel` que no exista se dice que NO se cumple, y no revienta
        con `KeyError`. El motivo es concreto: quien llama tiene una
        version de SkillGraph cuyo vocabulario de aislamiento es
        distinto del de este contrato, y eso es una situacion de
        despliegue real, no un error de programacion. Un `KeyError` en
        ese caso sale como traza, que es justo lo que WI-109 cerro para
        el otro lado de la frontera.
        """
        objetivo = _RANGO_POR_NIVEL.get(nivel)
        if objetivo is None:
            return False
        return self.nivel_de_aislamiento >= objetivo

    def describe(self) -> str:
        return f"{self.name}@{self.version} ({self.kind}, {self.isolation})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "isolation": self.isolation,
            "summary": self.summary,
            "namespace": self.namespace,
            "requires": {
                "skillgraph": self.requires.skillgraph,
                "capabilities": [c.describe() for c in self.requires.capabilities],
            },
            "metadata": dict(self.metadatos),
        }


# --- El formato explicito, y su lectura ----------------------------------


def parse_manifest(data: dict[str, Any]) -> PackManifest:
    """Construye un `PackManifest` desde el diccionario del manifiesto.

    Lee exactamente el formato que el roadmap declara:

    ```yaml
    requires:
      skillgraph: ">=0.30,<1"
      capabilities:
        - code.analysis.v1
    ```

    Y hace las dos cosas que un `dict` no puede:

    - **No muta la entrada.** Se copia, porque el llamante puede seguir
      usando su diccionario y un manifiesto que lo compartiera podria
      cambiar debajo (WI-113).
    - **Convierte las capabilities a tupla.** Una `list` de strings es
      valida en el formato —es lo que se escribe a mano— y una tupla en
      memoria, porque el manifiesto ya ha salido del borde del sistema.
    """
    if not isinstance(data, dict):
        raise ValidationError(f"el manifiesto debe ser un mapping, recibio {type(data).__name__}")

    requiere = data.get("requires")
    if not isinstance(requiere, dict):
        raise ValidationError(
            "el manifiesto debe declarar 'requires' con un mapping; sin el no se "
            "puede saber si el pack encaja en esta instalacion"
        )

    version_skillgraph = requiere.get("skillgraph")
    if not isinstance(version_skillgraph, str):
        raise ValidationError(
            "requires.skillgraph debe ser un string con el requisito de version, "
            'por ejemplo ">=0.30,<1"'
        )

    capabilities = tuple(_capability_de(item) for item in requiere.get("capabilities", ()))

    return PackManifest(
        name=_texto(data, "name"),
        version=_texto(data, "version"),
        kind=_texto(data, "kind"),  # type: ignore[arg-type]
        requires=Requires(skillgraph=version_skillgraph, capabilities=capabilities),
        isolation=data.get("isolation", "declarative"),
        summary=data.get("summary", ""),
        namespace=data.get("namespace", ""),
        metadatos=dict(data.get("metadata", {})),
    )


def _texto(data: dict[str, Any], clave: str) -> str:
    valor = data.get(clave)
    if not isinstance(valor, str) or not valor.strip():
        raise ValidationError(f"el manifiesto necesita '{clave}' como string no vacio")
    return valor


def _capability_de(item: Any) -> CapabilityRequirement:
    """De un elemento de `requires.capabilities` saca la requirement.

    Hay dos formas y las dos entran por aqui:

    - **Corta**: `"code.analysis.v1"`, la que se escribe a mano. La `v1`
      final es la VERSION y no parte del nombre.
    - **Larga**: `{"type_name": "code.analysis.v1", "version": "v1"}`, la
      que se genera y la que separa las dos cosas de verdad.

    La version se separa del nombre en AMBAS, y por una razon que un test
    cazo: la forma larga devolvia `"a.b.v2@v2"` como `type_name` y luego
    se construia `CapabilityRequirement(type_name="a.b.v2@v2")`, que
    arrastra la version en el nombre Y se queda con la del PUERTO en el
    campo `version`. Una requirement con la version pegada al nombre no
    se puede comparar con un `CapabilitySpec` instalado, que los tiene
    separados — y por eso el fallo era silencioso: todo lo demas
    parecia funcionar.
    """
    if isinstance(item, dict):
        nombre = item.get("type_name")
        version = item.get("version", CAPABILITY_VERSION)
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValidationError("una capability en 'requires' necesita 'type_name'")
        if not isinstance(version, str) or not version.strip():
            raise ValidationError(
                f"la capability {nombre!r} declara una version no valida: {version!r}"
            )
        return CapabilityRequirement(type_name=nombre, version=version)
    if not isinstance(item, str) or not item.strip():
        raise ValidationError(f"una capability en 'requires' debe ser un string, recibio {item!r}")
    nombre, _, version = item.rpartition("@")
    if not nombre:
        return CapabilityRequirement(type_name=item)
    return CapabilityRequirement(type_name=nombre, version=version)


# --- La pregunta: ¿este pack encaja aqui? --------------------------------


def es_compatible(
    manifest: PackManifest,
    *,
    skillgraph_version: str,
    capacidades_disponibles: tuple[tuple[str, str], ...] = (),
) -> tuple[str, ...]:
    """Devuelve los motivos de incompatibilidad. Vacio significa que encaja.

    `capacidades_disponibles` son pares `(type_name, version)` de lo que
    hay instalado. Se pasa como tupla de tuplas y no como `dict` por el
    mismo motivo que en `Requires`: el valor devuelto por una funcion
    pura no debe ser un mutable que el llamante pueda cambiar.

    **Por que devuelve una tupla de motivos y no un `bool`.** Un `bool`
    obliga a quien pregunta a volver a mirar el manifiesto para saber
    POR QUE. Y en un pack que se esta instalando, el «por que» es la
    mitad del trabajo: `no encaja` no le dice al operador si le falta una
    capability o si la version de SkillGraph es demasiado vieja.

    Los motivos son ordenados y deterministas —version primero,
    capabilities despues, y estas en el orden declarado—, porque un
    mensaje de error que cambia de orden entre ejecuciones es un mensaje
    de error que no se puede comparar ni copiar.
    """
    motivos: list[str] = []
    if not _cumple_requisito(skillgraph_version, manifest.requires.skillgraph):
        motivos.append(
            f"este pack requiere skillgraph {manifest.requires.skillgraph} "
            f"y aqui hay {skillgraph_version}"
        )
    disponibles = dict(capacidades_disponibles)
    for cap in manifest.requires.capabilities:
        instalada = disponibles.get(cap.type_name)
        if instalada is None:
            motivos.append(f"falta la capability {cap.describe()}")
        elif instalada != cap.version:
            motivos.append(
                f"la capability {cap.type_name} pide {cap.version} y aqui hay {instalada}"
            )
    return tuple(motivos)


def exigir_compatible(
    manifest: PackManifest,
    *,
    skillgraph_version: str,
    capacidades_disponibles: tuple[tuple[str, str], ...] = (),
) -> None:
    """Como `es_compatible`, pero levanta `IncompatiblePackError` si no encaja.

    La version que lanza y la que devuelve la misma lista de motivos se
    calculan con UNA sola llamada. Una funcion que dice «no» y otra que
    dice «por que», calculadas por separado, son dos medidas del mismo
    hecho, y dos medidas pueden discrepar.
    """
    motivos = es_compatible(
        manifest,
        skillgraph_version=skillgraph_version,
        capacidades_disponibles=capacidades_disponibles,
    )
    if motivos:
        detalle = "; ".join(motivos)
        raise IncompatiblePackError(
            f"{manifest.describe()} no encaja en esta instalacion: {detalle}"
        )


def _cumple_requisito(actual: str, requisito: str) -> bool:
    """¿La version `actual` satisface el requisito `requisito`?

    El requisito es una lista de clausulas separadas por coma, y TODAS
    tienen que cumplirse —`>=0.30,<1` significa «al menos 0.30 y menos de
    1»—. Un `or` aqui seria el error clasico: `>=0.30,<1` aceptaria 2.0.

    Una clausula que no se puede interpretar hace que el requisito NO se
    cumpla, en vez de que se pase por alto. Un requisito ilegible que se
    acepta en silencio es un requisito que no protege de nada.
    """
    return all(_cumple_clausula(actual, clausula.strip()) for clausula in requisito.split(","))


def _cumple_clausula(actual: str, clausula: str) -> bool:
    coincidencia = _REQUISITO_VERSION.match(clausula)
    if coincidencia is None:
        return False
    operador = coincidencia.group(1) or "=="
    esperado = (
        int(coincidencia.group(2)),
        int(coincidencia.group(3) or "0"),
        int(coincidencia.group(4) or "0"),
    )
    version_actual = _version_actual(actual)
    if version_actual is None:
        return False
    if operador == ">=":
        return version_actual >= esperado
    if operador == "<=":
        return version_actual <= esperado
    if operador == ">":
        return version_actual > esperado
    if operador == "<":
        return version_actual < esperado
    return version_actual == esperado


def _version_actual(version: str) -> tuple[int, int, int] | None:
    """La version de la instalacion, con el patch a 0 si no lo dice.

    Acepta `0.30` y `0.30.1` por la misma razon que el requisito. Se
    DEJA lo que sobra —`0.30.1.2` se lee como `0.30.1`— en vez de
    rechazarlo: la version la pone el empaquetador, y un empaquetador
    que escribe de mas no es un motivo para no poder comparar.
    """
    coincidencia = re.match(r"^\d+\.\d+(?:\.\d+)?", version.strip())
    if coincidencia is None:
        return None
    partes = coincidencia.group(0).split(".")
    if len(partes) == 2:
        partes.append("0")
    return (int(partes[0]), int(partes[1]), int(partes[2]))


__all__: Final[tuple[str, ...]] = (
    "CAPABILITY_VERSION",
    "ISOLATION_LEVELS",
    "PACK_KINDS",
    "CapabilityRequirement",
    "IncompatiblePackError",
    "IsolationLevel",
    "PackKind",
    "PackManifest",
    "Requires",
    "SkillGraphError",
    "es_compatible",
    "exigir_compatible",
    "parse_manifest",
)
