"""B17: la propiedad «el ciclo de vida existe» se decide EJECUTANDO el ciclo.

El hallazgo
-----------
B15 nombro siete propiedades del gate que se deciden leyendo el arbol, y B16
abrio las dos primeras. Esta es la tercera, y es la mas facil de las que
quedan **por una razon que no es de estilo: el instrumento que hace el
trabajo ya estaba escrito y no se estaba usando.**

    scripts/measure_b11_pack_lifecycle.py  ->  cinco preguntas, cada una
    EJECUTANDO la CLI de verdad en un proyecto temporal, con rc propio.

Y el predicado del gate no lo llamaba. Decia «`sg pack` expone el ciclo
completo: ['import', 'install', 'list', 'load', 'remove', 'update']», y su
unico trabajo era mirar si tres CADENAS estaban en un dict que sale del
parser.

MEDIDO, con la DECISION de `install` rota en una COPIA del arbol —el `if` que
levanta `ValidationError` cuando `motivos_de_incompatibilidad` devuelve
motivos, y no `es_compatible`, que es la verdad del dominio y que no se toca
porque romper las dos no mediria una, mediria otra cosa—:

    antes del arreglo
      gate   : PASS     <- leia NOMBRES
      B11 Q1 : PASS     <- leia NOMBRES, y es LITERALMENTE el predicado del gate
      B11 Q2 : OPEN     <- EJECUTO install con un pack incompatible
      resumen: OPEN: 1 · PASS: 4

    despues
      gate   : OPEN     y la evidencia NOMBRA la pregunta que cae

**El ciclo de vida estaba roto y la propiedad que lo declara estaba en verde.**

Y el hallazgo mas incomodo no es del gate: es que el predicado **era Q1 del
propio instrumento de B11**, y Q1 es la mas debil de las cinco —las otras
cuatro ejecutan—. El gate llevaba tiempo decidiendo «el ciclo de vida
existe» con la unica de las cinco preguntas que no lo prueba. Q1 lo sabe y
lo dice en su docstring; no es que estea equivocado, es que estaba solo.

Los tres conjuntos son disjuntos y cada uno declara en su docstring que es lo
UNICO que mide.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"
REGISTRO = "src/skillgraph/packaging/registry.py"

#: El `if` de la DECISION de `install`. MEDIDO: `if motivos:` aparece DOS
#: veces en el fichero —en `instalar` y en `actualizar`—, y por eso el ancla
#: baja hasta el MENSAJE, que es lo que distingue una decision de la otra. Un
#: ancla que aparece dos veces no mide: deshace el texto equivocado sin que se
#: note, y el numero que sale no corresponde a nada.
ANCLA_DECISION = (
    "    if motivos:\n"
    "        raise ValidationError(\n"
    '            f"el pack {manifiesto.describe()} no se puede instalar: "'
)


def _carga() -> object:
    spec = importlib.util.spec_from_file_location("gate_b17", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b17"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _ArbolCopiado:
    """Una copia de `src/` con `RAIZ` apuntando a ella, y restaura al salir.

    MEDIDO: en B14 se midio mutando el arbol REAL y restaurando por sha256, que
    funciona pero deja el repo en un estado que existio de verdad. Una copia no
    deja rastro ni necesita red de seguridad, y para esta deformacion —que no
    toca el parser sino lo que el gate EJECUTA— es exactamente lo que hace
    falta: el gate corre de verdad, contra un arbol donde la decision esta
    rota.

    La copia lleva `scripts/` tambien porque el gate tiene que CORRER el
    instrumento de B11, y el instrumento se localiza a si mismo desde
    `__file__`. Sin el, el predicado no tendria nada que ejecutar y daria
    `NO_MEASURABLE` —que es la respuesta honesta, y por eso el test de abajo
    la vigila: un `NO_MEASURABLE` aqui significaria que el guard no esta
    mirando lo que dice mirar.
    """

    def __init__(self) -> None:
        self._raiz_real = RAIZ
        self._destino: Path | None = None

    def __enter__(self) -> _ArbolCopiado:
        self._tmp = tempfile.TemporaryDirectory(prefix="b17_")
        self._destino = Path(self._tmp.name)
        shutil.copytree(self._raiz_real / "src", self._destino / "src", symlinks=True)
        (self._destino / "scripts").mkdir()
        for f in ("measure_b9_gate_1_0.py", "measure_b11_pack_lifecycle.py"):
            shutil.copy2(RAIZ / "scripts" / f, self._destino / "scripts" / f)
        self._modulo = _carga()
        self._modulo.RAIZ = self._destino
        return self

    def __exit__(self, *_exc: object) -> None:
        self._modulo.RAIZ = self._raiz_real
        self._tmp.cleanup()

    def rompe_la_decision_de_install(self) -> None:
        """Neutraliza el `if` que hace que `install` rechace lo incompatible.

        Se rompe el `if`, no `es_compatible`: `es_compatible` es la verdad del
        dominio y la segunda mitad del enunciado de B8. Romper las dos no
        mediria una sola cosa, mediria «que pasa si el contrato no existe», que
        es otro bloque.
        """
        ruta = self._destino / REGISTRO
        texto = ruta.read_text(encoding="utf-8")
        if texto.count(ANCLA_DECISION) != 1:
            raise AssertionError(
                f"el ancla de la decision aparece {texto.count(ANCLA_DECISION)} veces en "
                f"{REGISTRO}, y se sustituiria la primera. Si `instalar` o `actualizar` han "
                f"cambiado de forma, la deformacion de este test ya no es la que dice ser y "
                f"pasaria a medir otra cosa."
            )
        ruta.write_text(
            texto.replace(
                ANCLA_DECISION,
                ANCLA_DECISION.replace("    if motivos:", "    if False and motivos:", 1),
                1,
            ),
            encoding="utf-8",
        )

    @property
    def modulo(self) -> object:
        return self._modulo


# =====================================================================
class TestUnNombreDeSubcomandoNoEsUnCicloDeVida:
    """Lo UNICO que mide: que la propiedad CAIGA cuando el ciclo se rompe.

    **Por que este conjunto existe y no es cosmetica.** El predicado viejo
    miraba si tres cadenas estaban en un `dict` que sale del parser, y su
    propia evidencia lo decia: una lista de nombres. Con la decision de
    `install` rota —el pack entra, no se rechaza, y no dice nada— la
    propiedad decia PASS igual. MEDIDO antes de arreglar.
    """

    def test_con_el_ciclo_roto_la_propiedad_es_open(self) -> None:
        """La deformacion de 5.2 del PRE-FLIGHT, aplicada de verdad."""
        with _ArbolCopiado() as arbol:
            arbol.rompe_la_decision_de_install()
            veredicto, evidencia = arbol.modulo._pack_controller_lifecycle()
        assert veredicto == "OPEN", (
            f"install ya no rechaza un pack incompatible y la propiedad que declara "
            f"«el ciclo de vida existe» sigue en {veredicto!r}. El ciclo de vida esta "
            f"ROTO y la propiedad que lo declara esta en verde: es el mismo defecto que "
            f"B13 cerro en el guard de SQL y que B16 cerro en el predicado de la frontera, "
            f"con el signo cambiado —aqui se leian NOMBRES y se daba verde CON EL CICLO "
            f"ROTO—. Evidencia: {evidencia[:300]!r}"
        )

    def test_el_open_nombra_la_pregunta_que_cae(self) -> None:
        """CONTRA-SALTO del anterior por su otra mitad: el TEXTO.

        Exigir solo «que no sea PASS» dejaria pasar a un OPEN por un motivo
        equivocado: si el instrumento no se pudiera ejecutar, el predicado
        daria NO_MEASURABLE, que tambien es «no PASS», y seria verde para el
        gate. Se exige que la evidencia nombre la PREGUNTA que cae, que es lo
        que le dice a quien corrige cual de las cinco cosas esta rota.
        """
        with _ArbolCopiado() as arbol:
            arbol.rompe_la_decision_de_install()
            veredicto, evidencia = arbol.modulo._pack_controller_lifecycle()
        assert veredicto == "OPEN"
        assert "install rechaza un pack incompatible" in evidencia, (
            f"el veredicto es OPEN pero no dice QUE PREGUNTA cayo: {evidencia[:400]!r}. "
            f"Un verificador que dice «falso» sin decir cual era la verdad obliga a "
            f"reabrir el instrumento entero para saber donde mirar."
        )
        assert "NO_MEASURABLE" not in evidencia, (
            "la evidencia dice NO_MEASURABLE con el ciclo roto: el instrumento no se pudo "
            "ejecutar, y eso NO es «el ciclo esta roto». Son dos cosas distintas, y la "
            "segunda se arregla mirando el entorno y la primera mirando el ciclo."
        )


# =====================================================================
class TestLaPropiedadNoVuelveALosNombres:
    """Lo UNICO que mide: que el arreglo no se deshaga en silencio.

    Un arreglo que dependa de que nadie lo toque no es un arreglo. Y este tiene
    un modo de deshacerse muy facil —volver a mirar `_subcomandos_de`— porque
    la forma corta cabe en cuatro lineas y parece mas limpia que correr un
    instrumento entero.
    """

    def test_el_ciclo_real_sigue_sosteniendose(self) -> None:
        """CONTRA-SALTO de la direccion contraria: que el arreglo no rompa nada.

        Un guard que solo sabe decir que no, aplicado a un predicado que se ha
        endurecido, es indistinguible de uno que lo ha roto. Y este estado es
        el que hay hoy, luego es el caso que importa no romper.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._pack_controller_lifecycle()
        assert veredicto == "PASS", (
            f"el ciclo real se sostiene y el gate lo declara roto: {evidencia[:300]!r}. "
            f"O el gate acaba de detectar algo que hay que arreglar, o el instrumento "
            f"de B11 se ha roto y esto no lo mide."
        )

    def test_la_evidencia_dice_que_se_ejecuto(self) -> None:
        """Que el PASS diga EJECUTADO, y no «expone», que es lo de antes.

        La evidencia es lo que queda escrito cuando alguien lee el informe en
        seis meses y no mira el codigo. «`sg pack` expone el ciclo completo» y
        «se ha ejecutado, 5 de 5, una de ellas instalando un pack incompatible»
        no dicen lo mismo, y la segunda es la que se puede auditar.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._pack_controller_lifecycle()
        assert veredicto == "PASS"
        assert "EJECUTADO" in evidencia, (
            f"la evidencia no dice que la propiedad se EJECUTO: {evidencia[:300]!r}. "
            f"Un PASS que no dice como se obtuvo es el mismo PASS de antes con otra "
            f"tipografia."
        )
        assert "expone el ciclo completo" not in evidencia, (
            f"la evidencia ha vuelto a ser la lista de nombres: {evidencia[:300]!r}. "
            f"Esa frase era la del predicado viejo, y era toda su medida."
        )
        assert "measure_b11_pack_lifecycle.py" in evidencia, (
            f"la evidencia no nombra el instrumento que la decidio: {evidencia[:300]!r}. "
            f"Sin el nombre, nadie puede volver a correrla para comprobarlo."
        )


# =====================================================================
class TestElInstrumentoNoSeDeclaraMedibleCuandoNoLoEs:
    """Lo UNICO que mide: que un instrumento que no habla no diga «que no».

    **Por que hay un conjunto para esto, y no es defensivo.** El predicado
    cableado depende de un subproceso. Un subproceso puede no correr: sin
    `scripts/` en la copia, sin permiso, sin el interprete. Y la pregunta de
    ese fallo es *distinta* de la pregunta de la propiedad: «¿el ciclo de vida
    se sostiene?» no es «¿puedo medir si el ciclo de vida se sostiene?».

    Mezclarlas es como el guard que B14 cerro al leer un recuento de una
    colecta que no termino: el numero sale con la autoridad de un dato y no es
    un dato.
    """

    def test_un_instrumento_que_no_devuelve_nada_no_dice_que_no(self) -> None:
        with _ArbolCopiado() as arbol:
            # Se borra el instrumento, que es la forma mas honesta de que un
            # subproceso no conteste: no se rompe, no se tacha, no se finge.
            (arbol._destino / "scripts" / "measure_b11_pack_lifecycle.py").unlink()
            veredicto, evidencia = arbol.modulo._pack_controller_lifecycle()
        assert veredicto != "PASS", (
            f"sin instrumento el gate dice PASS: {evidencia[:300]!r}. Un predicado que "
            f"no puede mirar tiene que decirlo, y decirlo como PASS es la forma peor "
            f"de decirlo."
        )
        assert veredicto in ("NO_MEASURABLE", "OPEN"), (
            f"sin instrumento el veredicto es {veredicto!r}, y solo caben dos respuestas "
            f"honestas: NO_MEASURABLE —no lo se— u OPEN —revisar—. Lo que no cabe es un "
            f"veredicto de propiedad con un instrumento que no ha contestado."
        )
        assert "NO SE HA PODIDO MEDIR" in evidencia, (
            f"el veredicto es {veredicto!r} pero no dice POR QUE: {evidencia[:300]!r}"
        )
