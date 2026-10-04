"""B11 — el REGISTRO de packs instalados, y el ciclo de vida sobre el.

Por que este modulo existe
--------------------------
B8 entrego el CONTRATO de paquete: `PackManifest`, `Requires`, los seis
tipos, los tres niveles de aislamiento y `es_compatible` que devuelve
MOTIVOS. Su propio enunciado decia que sin contrato versionado no hay
``install``/``update``/``remove`` «que valga como algo mas de lo que sea
copiar ficheros», y el gate de B9 mide esa frase con un predicado: hoy
``sg pack`` expone ``['import', 'load']``.

Falta la mitad que convierte el contrato en un gestor: saber QUE hay
instalado. Sin eso no hay ciclo de vida, hay carga de ficheros.

El registro: por que NO se borra nada
-------------------------------------
AGENTS.md 8 dice que los eventos son append-only y que la idempotencia va
por constraint, no por codigo. `remove` no borra la fila: la MARCA.

Y no es una distincion de estilo. Si `remove` hiciera `DELETE`, la fila
desapareceria y no habria forma de responder a la pregunta que de verdad
importa —«¿este proyecto ha tenido alguna vez este pack?»— porque el unico
sitio donde vive la respuesta es la fila que se borro. Marcar conserva la
respuesta, y hace que un `install` posterior sea un `install` y no una
reinstalacion silenciosa de algo que el operador creia haber quitado.

Un `DELETE` es reversible guardandolo antes en otro sitio, y ese otro
sitio es exactamente la fila. Marcar es el `DELETE` mas su historia.

Inmutabilidad
-------------
`frozen=True, slots=True` y `MappingProxyType` en los mappings, por el
motivo de WI-113: `frozen=True` congela el enlace, no el valor.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from skillgraph.core.errors import NotFoundError, ValidationError
from skillgraph.packaging.manifest import PackManifest, es_compatible

#: El estado de una fila. Una fila no se borra: se mueve de uno a otro.
ESTADO_INSTALADO: str = "installed"
ESTADO_RETIRADO: str = "retired"


@dataclass(frozen=True, slots=True)
class FilaDePack:
    """Lo que el registro sabe de UN pack en UN proyecto.

    `manifiesto` es el manifiesto de la version que esta VIVA, no el que se
    acaba de entregar. Por eso `actualizar` puede comparar contra lo que
    hay de verdad, en vez de contra lo que el operador cree que hay.
    """

    pack: str
    estado: str
    manifiesto: PackManifest
    uid: str = ""
    metadatos: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadatos", MappingProxyType(dict(self.metadatos)))

    @property
    def instalado(self) -> bool:
        return self.estado == ESTADO_INSTALADO

    def describe(self) -> str:
        """La linea que ve el operador. Version, aislamiento y estado, los tres."""
        return f"{self.pack}@{self.manifiesto.version} [{self.manifiesto.isolation}] {self.estado}"


@dataclass(frozen=True, slots=True)
class RegistroDePacks:
    """Las filas de un proyecto. Inmutable: cada operacion devuelve OTRO registro.

    No se muta en sitio, y no es purismo. Si `instalar` comprobara la
    compatibilidad ANTES de tocar el registro —que es lo que hace—, y
    aun asi se mutara, un fallo a mitad dejaria el registro a medias. Con
    registro inmutable, el registro viejo sigue entero y el que se
    devuelve es el nuevo entero o ninguno.
    """

    filas: tuple[FilaDePack, ...] = ()

    # --- lectura ---------------------------------------------------------

    def __iter__(self) -> Iterator[FilaDePack]:
        return iter(self.filas)

    def __len__(self) -> int:
        return len(self.filas)

    @property
    def instalados(self) -> tuple[FilaDePack, ...]:
        """Solo las filas VIVAS, ordenadas por nombre. Es lo que ve el usuario."""
        return tuple(sorted((f for f in self.filas if f.instalado), key=lambda f: f.pack))

    def buscar(self, pack: str) -> FilaDePack | None:
        """La fila VIVA de ese pack, o `None`. Una retirada NO esta instalada."""
        for fila in self.filas:
            if fila.pack == pack and fila.instalado:
                return fila
        return None

    def con_uid(self, uid: str) -> FilaDePack | None:
        for fila in self.filas:
            if fila.uid == uid and fila.instalado:
                return fila
        return None

    def nombres_instalados(self) -> tuple[str, ...]:
        return tuple(f.pack for f in self.instalados)

    # --- escritura -------------------------------------------------------

    def _con_viva(self, fila: FilaDePack) -> RegistroDePacks:
        """Sustituye la fila de ese pack y la deja viva, conservando su `uid`."""
        anterior = self.buscar(fila.pack)
        uid = fila.uid or (anterior.uid if anterior else "")
        conservadas = tuple(f for f in self.filas if f.pack != fila.pack)
        nueva = FilaDePack(
            pack=fila.pack,
            estado=ESTADO_INSTALADO,
            manifiesto=fila.manifiesto,
            uid=uid,
            metadatos=fila.metadatos,
        )
        return RegistroDePacks((*conservadas, nueva))

    def con_instalado(self, manifiesto: PackManifest, *, uid: str = "") -> RegistroDePacks:
        """Deja `manifiesto` como la version VIVA de su pack."""
        return self._con_viva(
            FilaDePack(
                pack=manifiesto.name, estado=ESTADO_INSTALADO, manifiesto=manifiesto, uid=uid
            )
        )

    def con_retirado(self, pack: str) -> RegistroDePacks:
        """Marca la fila como RETIRADA. No la borra: ver la cabecera del modulo.

        Retirar lo que no esta instalado es un `NotFoundError` Y CON MOTIVO:
        la lista de lo que si hay es la mitad de la respuesta, porque «no
        esta instalado» sin decir que hay deja al operador adivinando si se
        equivoco de nombre.
        """
        fila = self.buscar(pack)
        if fila is None:
            raise NotFoundError(
                f"el pack {pack!r} no esta instalado en este proyecto, luego no hay nada "
                f"que retirar. Lo que hay instalado es {list(self.nombres_instalados()) or '(nada)'}"
            )
        retirada = FilaDePack(
            pack=fila.pack,
            estado=ESTADO_RETIRADO,
            manifiesto=fila.manifiesto,
            uid=fila.uid,
            metadatos=fila.metadatos,
        )
        return RegistroDePacks(tuple(retirada if f.pack == pack else f for f in self.filas))


# --- El ciclo de vida, como funciones PURAS sobre el registro --------------


def motivos_de_incompatibilidad(
    manifiesto: PackManifest,
    *,
    version_skillgraph: str,
    capacidades: Sequence[tuple[str, str]] = (),
) -> tuple[str, ...]:
    """Delega en el predicado de B8. Vacio = encaja.

    Se delega y no se reimplementa: dos definiciones de «este pack encaja»
    son dos verdades, y la que no se ejecuta es la que se queda vieja.
    """
    return es_compatible(
        manifiesto,
        skillgraph_version=version_skillgraph,
        capacidades_disponibles=tuple(capacidades),
    )


def instalar(
    registro: RegistroDePacks,
    manifiesto: PackManifest,
    *,
    version_skillgraph: str,
    uid: str = "",
) -> tuple[RegistroDePacks, str]:
    """Instala un pack, o deja el nuevo como la version viva. Devuelve (registro, delta).

    La compatibilidad se comprueba ANTES de tocar el registro, y el motivo
    que devuelve `es_compatible` sube hasta el operador. Es el argumento
    de B8 —«no encaja» no le dice si falta una capability o si tu
    SkillGraph es viejo— llegando a la linea de comandos.

    Instalar sobre un pack ya instalado NO es un error: la diferencia entre
    `instalar` y `actualizar` no es el efecto —es el mismo— sino la
    EXIGENCIA. `instalar` acepta la primera vez o una reinstalacion;
    `actualizar` exige que la version suba.

    El delta se devuelve porque sin el el operador no puede confirmar lo
    que acaba de pasar: si hacia falta, y desde que.
    """
    motivos = motivos_de_incompatibilidad(manifiesto, version_skillgraph=version_skillgraph)
    if motivos:
        raise ValidationError(
            f"el pack {manifiesto.describe()} no se puede instalar: " + "; ".join(motivos)
        )
    anterior = registro.buscar(manifiesto.name)
    nuevo = registro.con_instalado(manifiesto, uid=uid)
    delta = (
        f"{anterior.manifiesto.version} -> {manifiesto.version}"
        if anterior
        else f"instalado {manifiesto.version}"
    )
    return nuevo, delta


def actualizar(
    registro: RegistroDePacks,
    manifiesto: PackManifest,
    *,
    version_skillgraph: str,
    uid: str = "",
) -> tuple[RegistroDePacks, str]:
    """Actualiza exigiendo que la version SUBE. Exige version Y esta instalado.

    Las dos mitades, y las dos importan. (a) Un `update` sobre algo que no
    esta instalado no es un update: es un `install`, y el operador que lo
    pide quiere una excepcion si se equivoco de nombre. (b) La version
    nueva tiene que SUBIR, y por numero y no por cadena: `0.10.0` es mayor
    que `0.9.0` como numero y menor como texto, y un update que aceptase
    la version menor degradaria el entorno sin avisar.
    """
    instalada = registro.buscar(manifiesto.name)
    if instalada is None:
        raise NotFoundError(
            f"el pack {manifiesto.name!r} no esta instalado, luego no se puede actualizar: "
            "un update es sobre algo que ya esta. Lo que hay instalado es "
            f"{list(registro.nombres_instalados()) or '(nada)'}"
        )
    motivos = motivos_de_incompatibilidad(manifiesto, version_skillgraph=version_skillgraph)
    if motivos:
        raise ValidationError(
            f"el pack {manifiesto.describe()} no se puede actualizar: " + "; ".join(motivos)
        )
    if not _sube(instalada.manifiesto.version, manifiesto.version):
        raise ValidationError(
            f"update de {manifiesto.name}: la version nueva {manifiesto.version} no sube "
            f"respecto a la instalada {instalada.manifiesto.version}. Un update que acepta "
            "una version que no sube degrada el entorno sin avisar, que es peor que no "
            "tener update"
        )
    nuevo = registro.con_instalado(manifiesto, uid=uid)
    return nuevo, f"{instalada.manifiesto.version} -> {manifiesto.version}"


def retirar(registro: RegistroDePacks, pack: str) -> tuple[RegistroDePacks, str]:
    """Retira un pack. Lo que no esta da `NotFoundError` con la lista de lo que si."""
    retirado = registro.con_retirado(pack)
    fila = retirado.buscar(pack)
    version = fila.manifiesto.version if fila else ""
    return retirado, f"retirado {pack}@{version}"


def manifiesto_de(brick: object) -> PackManifest:
    """Lee el manifiesto de B8 de la `spec` de un pack.

    El manifiesto viaja en `spec.manifest` porque `spec` es la unica parte
    del pack que el tipo `DomainPack` acepta sin rechazar: su validador
    exige `version` y admite `capabilities`, y el resto de claves pasan.
    Meterlo ahi unifica los DOS contratos en vez de crear un tercero que
    habria que mantener en paralelo y que nadie mas leeria.
    """
    from skillgraph.packaging.manifest import parse_manifest

    spec = getattr(brick, "spec", None)
    if not isinstance(spec, dict):
        raise ValidationError("el pack no trae spec, luego no hay manifiesto que leer")
    crudo = spec.get("manifest")
    if not isinstance(crudo, dict):
        raise ValidationError(
            "el pack no trae `spec.manifest`: un pack instalable declara ahi su "
            "manifiesto, con los campos de PackManifest (name, version, kind, requires)"
        )
    return parse_manifest(crudo)


# --- Ayudas puras ---------------------------------------------------------


def _sube(actual: str, nueva: str) -> bool:
    """¿La version nueva es estrictamente mayor que la instalada? Por numero.

    La comparacion es por NUMERO y no por cadena porque `0.10.0` > `0.9.0`
    como numero y `<` como texto, y el que decide es el que entiende el
    numero. Una version que no se puede leer NO sube: devolver `True` en
    ese caso haria que un manifiesto con `version: "alfa"` degradase la
    instalada, que es justo lo que esta funcion existe para impedir.
    """

    def partes(version: str) -> tuple[int, ...] | None:
        trozos = version.split(".")
        if len(trozos) != 3 or not all(t.isdigit() for t in trozos):
            return None
        return tuple(int(t) for t in trozos)

    a, b = partes(actual), partes(nueva)
    if a is None or b is None:
        return False
    return b > a


def desde_filas(filas: Iterable[FilaDePack]) -> RegistroDePacks:
    """Construye un registro a partir de filas sueltas. Para tests y para cargar."""
    return RegistroDePacks(tuple(filas))
