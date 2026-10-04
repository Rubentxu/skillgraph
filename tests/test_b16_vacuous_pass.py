"""B16: dos propiedades del gate de 1.0 dan PASS sin nada que comparar.

El hallazgo
-----------
B15 dejo escrito que siete de las veinte propiedades del gate se deciden leyendo
el arbol. Esta es la primera de esas siete, y no es una cuestion de forma: dos de
ellas **dan verde sin mirar nada**.

MEDIDO sobre copias del arbol, con el repo real intacto:

    MEDIDO A · se renombra la constante a _CAPABILITY_VERSION en todo src/
      veredicto : PASS
      evidencia : CAPABILITY_VERSION se declara en un solo sitio: []

    MEDIDO B · core/ importa DomainPack de verdad
      veredicto : PASS
      evidencia : core/ no nombra ningun tipo de recurso: se anaden sin tocarlo

La primera es un PASS con la evidencia `[]`: un veredicto cuyo texto dice una
lista vacia no es un veredicto sobre el proyecto, es sobre su propia capacidad
de contar. Y la propiedad es cierta hoy **por suerte del caso** —la constante
existe en un sitio— no por lo que el gate midio.

La segunda es la fuga de B13 con el signo cambiado. Alli el guard leia literales
en vez de la consulta ensamblada y daba verde CON LA FUGA PRESENTE; aqui leia
cadenas en vez de los imports y daba verde CON LA DEPENDENCIA PRESENTE. Y lo que
se declara es una FRONTERA arquitectonica —el nucleo no depende de los recursos,
asi que anadir un recurso no obliga a tocarlo— que nada vigilaba.

Los tres conjuntos son disjuntos y cada uno declara en su docstring que es lo
UNICO que mide.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"


def _carga() -> object:
    spec = importlib.util.spec_from_file_location("gate_b16", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b16"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _ArbolCopiado:
    """Una copia de `src/` con `RAIZ` apuntando a ella, y restaura al salir.

    MEDIDO: en B14 se midio mutando el arbol REAL y restaurando por sha256, que
    funciona pero deja el repo en un estado que existio de verdad. Una copia no
    deja rastro ni necesita red de seguridad, y para estas deformaciones —que
    no tocan `src/` sino solo lo que el gate VE— es exactamente lo que hace
    falta: el gate se ejecuta de verdad, sobre un arbol donde la cosa esta
    estropeada.
    """

    def __init__(self) -> None:
        self._raiz_real = RAIZ
        self._destino: Path | None = None

    def __enter__(self) -> _ArbolCopiado:
        self._tmp = tempfile.TemporaryDirectory(prefix="b16_")
        self._destino = Path(self._tmp.name)
        shutil.copytree(self._raiz_real / "src", self._destino / "src", symlinks=True)
        self._modulo = _carga()
        self._modulo.RAIZ = self._destino
        return self

    def __exit__(self, *_exc: object) -> None:
        self._modulo.RAIZ = self._raiz_real
        self._tmp.cleanup()

    def escribe_en_core(self, nombre: str, texto: str) -> None:
        (self._destino / "src" / "skillgraph" / "core" / nombre).write_text(texto, encoding="utf-8")

    def saca_de(self, relativo: str, patron: re.Pattern[str], destino: str) -> str:
        """Mueve de un modulo a otro la PRIMERA linea que casa con `patron`.

        Se busca por FORMA y no por literal porque la forma de la declaracion no
        es el objeto del test: MEDIDO, hoy es
        `CAPABILITY_VERSION: Final[str] = "v1"`, o sea un `AnnAssign`. Un test
        que escribiera `texto.index("CAPABILITY_VERSION =")` pasaria a fallar
        por un cambio de anotacion que no tiene nada que ver con la propiedad
        que vigila, y ese fallo —un `ValueError` sin contexto— es
        indistinguible de un guard roto.

        Y si la forma cambia tanto que el patron ya no casa, `assert` con
        mensaje: es una premisa del test que ha dejado de ser cierta, y hay
        que leerlo como eso y no como un bug del predicado.
        """
        origen = self._destino / relativo
        lineas = origen.read_text(encoding="utf-8").splitlines(keepends=True)
        for indice, linea in enumerate(lineas):
            if patron.match(linea):
                del lineas[indice]
                origen.write_text("".join(lineas), encoding="utf-8")
                (self._destino / destino).write_text(linea, encoding="utf-8")
                return linea.strip()
        raise AssertionError(
            f"ninguna linea de {relativo} casa con {patron.pattern!r}. La forma de "
            f"la declaracion ha cambiado y este test hay que actualizar; lo que "
            f"NO se puede es que la propiedad se quede sin comprobar porque el "
            f"test se rindio: las lineas son {lineas!r}"
        )

    @property
    def modulo(self) -> object:
        return self._modulo


# =====================================================================
class TestUnPassSinNadaQueCompararNoEsUnPass:
    """Lo UNICO que mide: que el vacio no pueda salir verde.

    **Por que este conjunto existe y no es cosmetica.** La logica anterior era
    «si hay mas de uno, OPEN; si no, PASS». Con cero declaraciones —un repo donde
    nadie declara la constante— salia PASS con la evidencia
    «se declara en un solo sitio: []». La propiedad era cierta por suerte del
    caso, y el gate no tenia forma de distinguir «la declare yo solo» de «no la
    declara nadie».
    """

    def test_cero_declaraciones_es_open_y_lo_dice(self) -> None:
        """CONTRA-SALTO del anterior por su otra via: el TEXTO de la evidencia.

        Exigir solo «que no sea PASS» dejaria pasar a un OPEN por un motivo
        equivocado —por ejemplo, si el renombrado provocara un error de
        sintaxis—. Se exige que la evidencia nombre el hecho: NADIE declara.
        """
        with _ArbolCopiado() as arbol:
            for modulo in (arbol._destino / "src" / "skillgraph").rglob("*.py"):
                modulo.write_text(
                    modulo.read_text(encoding="utf-8").replace(
                        "CAPABILITY_VERSION", "_CAPABILITY_VERSION"
                    ),
                    encoding="utf-8",
                )
            veredicto, evidencia = arbol.modulo._capabilities_deterministas()
        assert veredicto == "OPEN", (
            f"sin ninguna declaracion el veredicto es {veredicto!r} y no OPEN. "
            f"Un veredicto cuyo texto dice una lista vacia no dice nada del proyecto."
        )
        assert "NADIE" in evidencia, (
            f"el veredicto es OPEN pero no dice POR QUE: {evidencia!r}. Un "
            f"verificador que dice «falso» sin decir cual era la verdad deja a "
            f"quien corrige haciendo la cuenta a mano."
        )

    def test_una_declaracion_fuera_del_puerto_es_open(self) -> None:
        """La propiedad dice «EL PUERTO, y solo el». MEDIDO: no se comprobaba.

        Antes bastaba con que no hubiera dos declarantes: una constante que todo
        el mundo importa desde un fichero que no es el puerto sigue siendo una
        segunda fuente de verdad, solo que con una palabra menos. Y nadie lo
        vigila, porque contar no es lo mismo que contar Y comprobar donde.
        """
        with _ArbolCopiado() as arbol:
            # Se saca la declaracion del puerto y se pone en un modulo de
            # runtime: la sigue habiendo, y no es el puerto.
            movida = arbol.saca_de(
                "src/skillgraph/platform/ports/capabilities.py",
                re.compile(r"^CAPABILITY_VERSION\b"),
                "src/skillgraph/runtime/version_fuera_del_puerto.py",
            )
            veredicto, evidencia = arbol.modulo._capabilities_deterministas()
        assert veredicto == "OPEN", (
            f"la version se declara fuera del puerto y el veredicto es {veredicto!r}. "
            f"La propiedad dice «el puerto, y solo el»: la segunda mitad de esa "
            f"frase no estaba medida."
        )
        assert "version_fuera_del_puerto" in evidencia, (
            f"el veredicto es OPEN pero no nombra donde se declara: {evidencia!r}. "
            f"La declarante real es {movida!r}"
        )

    def test_una_sola_declaracion_en_el_puerto_es_pass(self) -> None:
        """CONTRA-SALTO de la direccion contraria: que el arreglo no rompa nada.

        Un guard que solo sabe decir que no, aplicado a un predicado que se ha
        endurecido, es indistinguible de uno que lo ha roto. Y este estado es el
        que hay hoy, luego es el caso que importa no romper.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._capabilities_deterministas()
        assert veredicto == "PASS", f"el estado real dejo de ser PASS: {evidencia!r}"
        assert modulo.PUERTO_DE_CAPABILITIES in evidencia, (
            f"la evidencia no dice DONDE se declara: {evidencia!r}"
        )


# =====================================================================
class TestUnaFronteraQueNoSeMideNoEsUnaFrontera:
    """Lo UNICO que mide: que `core/` no pueda depender de un recurso.

    MEDIDO: el predicado buscava `^[A-Z][A-Za-z]+Pack$` dentro de constantes de
    CADENA. Un `from skillgraph.resources.packs import DomainPack` es un `Name`
    del AST, no una cadena; anadido ese import de verdad a un modulo de `core/`,
    el gate decia «core/ no nombra ningun tipo de recurso».
    """

    def test_un_import_de_verdad_es_open_y_nombra_el_modulo(self) -> None:
        with _ArbolCopiado() as arbol:
            arbol.escribe_en_core(
                "dependencia_de_verdad.py",
                '"""Un modulo de core/ que depende de un recurso."""\n'
                "from skillgraph.resources.packs import DomainPack\n"
                "\n"
                "\n"
                "def usa() -> type:\n"
                "    return DomainPack\n",
            )
            veredicto, evidencia = arbol.modulo._ontology_extensible()
        assert veredicto == "OPEN", (
            f"core/ importa DomainPack de verdad y el veredicto es {veredicto!r}. "
            f"La frontera arquitectonica que dice «el nucleo no depende de los "
            f"recursos» no la vigila nadie."
        )
        assert "DomainPack" in evidencia and "dependencia_de_verdad" in evidencia, (
            f"el veredicto es OPEN pero no nombra QUE tipo ni DONDE: {evidencia!r}"
        )

    def test_un_atributo_tambien_es_open(self) -> None:
        """CONTRA-SALTO del anterior por su otra via de manifestacion.

        La forma mas indirecta de meter la dependencia: no se importa el tipo,
        se importa el modulo y se accede al tipo por atributo. Un predicado que
        solo mira `ImportFrom` deja pasar justo esa, que es la que se escribe
        cuando ya se sabe que el nucleo no deberia saber del recurso.
        """
        with _ArbolCopiado() as arbol:
            arbol.escribe_en_core(
                "dependencia_por_atributo.py",
                '"""Depende de un recurso por atributo, sin importar el tipo."""\n'
                "from skillgraph.resources import packs\n"
                "\n"
                "\n"
                "def usa() -> type:\n"
                "    return packs.DomainPack\n",
            )
            veredicto, evidencia = arbol.modulo._ontology_extensible()
        assert veredicto == "OPEN", (
            f"core/ accede a DomainPack por atributo y el veredicto es {veredicto!r}. "
            f"El predicado miraba imports, y esta forma no es un import del tipo."
        )
        assert "DomainPack" in evidencia, f"la evidencia no nombra el tipo: {evidencia!r}"

    def test_el_nucleo_real_sigue_limpio(self) -> None:
        """CONTRA-SALTO de la direccion contraria, sobre el estado de HOY.

        El nucleo de verdad no depende de los recursos, y este test lo dice con
        la boca del gate y no con una cuenta propia. Si el nucleo se ensuciara,
        este test CAE y el mensaje dice quien lo ensucio.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._ontology_extensible()
        assert veredicto == "PASS", (
            f"el nucleo REAL nombra un tipo de recurso y el gate lo declara limpio: "
            f"{evidencia!r}. O el gate acaba de detectar algo que hay que arreglar, "
            f"o el patron de B16 no es el que se cree."
        )
