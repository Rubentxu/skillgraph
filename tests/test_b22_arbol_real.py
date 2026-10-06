"""B22: un test que cambia el arbol de trabajo real rompe a quien lo esta leyendo.

La propiedad
------------
**NINGUN TEST CAMBIA EL CONTENIDO DE UN FICHERO QUE GIT VERSIONA**, salvo
los que declaran por que lo hacen.

Y no «ningun test escribe»: un `finally` que restaura los bytes originales
ESCRIBE y NO CAMBIA, y es el mecanismo correcto del que deforma y restaura.
La propiedad es sobre el CONTENIDO, porque el contenido es lo que otro
instrumento lee mientras la suite corre.

Como se rompio, MEDIDO y no supuesto
------------------------------------
`scripts/measure_b9_gate_1_0.py` perdio el informe ENTERO de las veinte
propiedades del gate de 1.0 con `AssertionError: tocar la fecha no puede
cambiar el texto`. La cadena, medida de punta a punta:

1. `tests/test_b14_truth_single_reader.py` deforma `src/skillgraph/__init__.py`
   con `__version__ = "7.7.7"` para forzar una version incoherente.
2. El predicado de reproducibilidad del gate lee el contenido del fichero
   como su linea base, construye el paquete, y exige que el contenido siga
   igual.
3. Con la suite en paralelo, entre la lectura y la comprobacion el fichero
   ya habia vuelto a su contenido real. El aserto saltó, el predicado
   revanto, y `main()` devolvio `Un predicado revanto y el informe NO esta
   completo`: no un OPEN, CERO veredictos sobre las veinte.

La prueba de que el contenido era el inyectado no es una sospecha: durante
la corrida completa ese fichero tuvo dos contenidos distintos —el real, en
195649 lecturas, y `7da24eaaf72e`, en 1214—, y el sha256 de
`__version__ = "7.7.7"\\n` es exactamente `7da24eaaf72e`.

Y no fue solo el gate. El `STATE.yaml` real estuvo un 28 % de una ventana de
40 s con un estado INVENTADO —medido contra `git show HEAD:STATE.yaml`—,
mientras la clase `_inyectado` de B14 lo deformaba. MEDIDO sobre la corrida
completa: **25 escrituras que cambian contenido de un fichero versionado**,
en tres ficheros de test.

Por que el guard esta en conftest y no aqui
-------------------------------------------
Porque la propiedad es sobre TODA la corrida. Un modulo de guard solo ve
los tests que se le negocien al pedir; la instrumentacion esta en
`tests/conftest.py` para que vea la sesion entera, que es la unica ventana
en la que la rotura ocurrio. Este modulo decide QUE se acepta de lo que el
instrumento recogio.

Lo que estos tests hacen, y lo que NO hacen
------------------------------------------
**NO leen el codigo de los tests.** No hay AST que busque `write_text` ni
una lista de ficherosAware: el conjunto de infracciones lo produce la
ejecucion. Un guard que busca la llamada en el texto mide el texto, que es
el fallo de B20 con el heredoc —el texto estaba bien y lo que estaba mal
era lo que el shell PRODUCIA de el—.

Y el predicado se prueba aparte, con casos construidos, porque un guard que
solo sabe pasar no mide. Ver `TestElGuardSabeDarRojo`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.conftest import (
    _ESCRITURAS_AL_ARBOL_REAL,
    _MODULOS_EJECUTADOS,
)

RAIZ = Path(__file__).resolve().parent.parent

# El nodeid del test que decide. `pytest_collection_modifyitems` lo mueve al
# final de la sesion por este nombre: sin eso solo veria las escrituras que
# le preceden, y un escritor colocado despues pasaria en verde.
TEST_DEL_GUARD = (
    f"{Path(__file__).name}::TestElArbolRealNoSeEscribe::"
    "test_ninguna_escritura_al_arbol_real_queda_sin_explicar"
)

# ===========================================================================
# LO QUE SE ACEPTA, Y POR QUE
# ===========================================================================
#
# No es «los sitios que hay», es «los sitios cuya AUSENCIA SERIA UN DEFECTO»:
# si uno de estos dejara de deformar el arbol, su razon dejaria de ser cierta
# y la declaracion tendria que borrarse. Se vigila en las DOS direcciones —
# igual que `SKIPS_PLATAFORMA` en WI-108, y por el mismo motivo.
#
# La clave es el FICHERO de test, no el numero de linea: las lineas se mueven
# con cada edicion y una declaracion que hay que actualizar cada vez es una
# declaracion que se va a quedar vieja en silencio.
EXCEPCIONES_DECLARADAS: dict[str, str] = {
    "test_wi82_evidence_write_idempotence.py": (
        "La propiedad que prueba ES la idempotencia del emisor al escribir la "
        "evidencia VERSIONADA: `test_emitter_does_not_dirty_tracked_evidence` "
        "siembra un payload con otro `revision` y exige que el emisor no lo "
        "reescriba, y su contradictorio exige que si escriba cuando el "
        "contenido cambia de verdad. Medir eso exige deformar el fichero que "
        "es el objeto de la medicion. Se restaura en `finally` y el propio "
        "modulo trae `test_suite_run_leaves_tree_clean` para que el estado "
        "no se propague."
    ),
    # `test_b14_truth_single_reader.py` ESTUVO AQUI hasta B23, y su entrada
    # ahora es un BITACORA, no una excepcion. Se puede leer porque el motivo
    # por el que se concedio la excepcion —«no hay ningun sandbox que de una
    # respuesta de verdad, y por eso hay que deformar el arbol real»— es el
    # hallazgo que B23 mids y cerro. MEDIDO entonces: con solo los cuatro
    # ficheros que el script lee, la colecta sale rc=5 y el verificador
    # responde `ilegible` POR EL MOTIVO EQUIVOCADO; copiando los 722 ficheros
    # versionados sale rc=3 porque la copia no es un repositorio.
    #
    # B23 le dio a `project_truth.py` una raiz por parametro, y con ella un
    # sandbox que responde de verdad: su `.git` con un tag, su estado, su
    # ventana y un test propio. Las tres deformaciones apuntan alla. MEDIDO
    # con sha256 de los cuatro ficheros del arbol real antes y despues de la
    # corrida: IDENTICOS.
}


def sitio_de(violacion: str) -> str:
    """El fichero de test que hizo la escritura, tal cual lo nombra el marco.

    `violacion` tiene la forma ``superficie relativo <- fichero.py:N nombre``.
    Se parte por la ultima flecha, porque `relativo` puede contener `<-` y
    partir por la primera daria un nombre de fichero que no existe.
    """
    return violacion.rsplit("<-", 1)[-1].strip().split(":", 1)[0].strip()


def no_declaradas(violaciones: list[str], declaradas: dict[str, str]) -> tuple[str, ...]:
    """Las infracciones que NADIE ha declarado, con su fichero y su linea.

    **La predicado, separado del acumulador.** MEDIDO, por que: si el
    veredicto leyera directamente la lista global, el contrasalto de abajo
    tendria que contaminar la sesion real para probarlo, y una prueba que
    necesita ensuciar el mundo para medir deja residuo. Con el predicado
    como funcion, el contrasalto construye sus casos y no toca nada.
    """
    return tuple(v for v in violaciones if sitio_de(v) not in declaradas)


def declaradas_sin_uso(
    violaciones: list[str], declaradas: dict[str, str], ejecutados: set[str]
) -> tuple[str, ...]:
    """Las declaraciones que ya no corresponden a nada, y su motivo escrito.

     Una excepcion que no aplica es una afirmacion sobre el repo que ha
     dejado de ser cierta, y el repo entero esta lleno de esas. Borrarla es
     parte del arreglo, no limpieza opcional.

     **Y POR QUE NECESITA `ejecutados`.** MEDIDO: sin ese parametro, el test
    .reportaba como muerta la excepcion de `test_wi82` siempre que se
     ejecutara el fichero del guard SOLO —porque ahi ese modulo no llega a
     correr—, y eso obliga a que el guard solo pueda decir la verdad en la
     suite completa. Un guard que necesita que se le ejecute todo el mundo
     para no mentir es un guard que nadie puede usar en local. Un modulo que
     no se ejecuto no juzga su propia declaracion.
    """
    en_uso = {sitio_de(v) for v in violaciones}
    return tuple(
        f"{nombre}: declara «{motivo[:60]}...» y no hubo ninguna escritura suya"
        for nombre, motivo in declaradas.items()
        if nombre not in en_uso and nombre in ejecutados
    )


class TestElArbolRealNoSeEscribe:
    """Lo UNICO que mide: que lo que el instrumento recogido este explicado."""

    def test_el_instrumento_registra_una_escritura_que_el_mismo_hace(self) -> None:
        """CONTRASALTO, y se autocomprueba en vez de confiar en la sesion.

        MEDIDO, por que no vale «hubo escrituras durante la sesion»: esa
        forma daba un guard que solo podia pasar corriendo la suite COMPLETA
        —`pytest tests/test_b22_arbol_real.py` solo se ponia en rojo porque
        no habia escrituras— y un guard que necesita que se le ejecute todo
        el mundo para no mentir no lo ejecuta nadie en local.

        Aqui el guard escribe el mismo, mira que el envoltorio lo haya
        recogido, y se borra la traza. Es la unica forma de que la prueba de
        que el instrumento funciona no dependa de que otro test haya hecho
        algo antes.
        """
        from tests import conftest as instrumentador

        objetivo = RAIZ / "STATE.yaml"
        original = objetivo.read_bytes()
        marca = len(instrumentador._ESCRITURAS_OBSERVADAS)
        infracciones = len(instrumentador._ESCRITURAS_AL_ARBOL_REAL)
        try:
            objetivo.write_text(original.decode("utf-8") + "\n# sonda de B22\n", "utf-8")
            crecio = len(instrumentador._ESCRITURAS_OBSERVADAS) > marca
            cambio = len(instrumentador._ESCRITURAS_AL_ARBOL_REAL) > infracciones
        finally:
            objetivo.write_bytes(original)
            # La sonda deja su propia traza fuera: es instrumentacion
            # comprobandose, no un escritor real del arbol.
            del instrumentador._ESCRITURAS_OBSERVADAS[marca:]
            del instrumentador._ESCRITURAS_AL_ARBOL_REAL[infracciones:]
        assert crecio, (
            "el envoltorio de tests/conftest.py NO registro una escritura que "
            "este test acaba de hacer sobre un fichero versionado. El "
            "instrumento de B22 no esta mirando, y sus tests de veredicto "
            "estarian dando verde sobre una lista vacia."
        )
        assert cambio, (
            "el envoltorio vio la escritura pero no la clasifico como cambio "
            "de contenido. Con la comparacion de sha antes/despues rota, todo "
            "`finally` que restaura pareceria una infraccion, que es como se "
            "rompe la propiedad por el lado contrario."
        )
        assert objetivo.read_bytes() == original, "la sonda no devolvio el fichero"

    def test_ninguna_escritura_al_arbol_real_queda_sin_explicar(self) -> None:
        """La propiedad. Y nombra el fichero que hay que arreglar."""
        sin_explicar = no_declaradas(_ESCRITURAS_AL_ARBOL_REAL, EXCEPCIONES_DECLARADAS)
        assert not sin_explicar, (
            f"{len(sin_explicar)} escritura(s) al arbol de trabajo real cambiaron "
            "el contenido de un fichero que git versiona, y ninguna esta "
            "declarada en EXCEPCIONES_DECLARADAS:\n  "
            + "\n  ".join(sin_explicar)
            + "\n\nUn instrumento que este leyendo el arbol en ese instante "
            "(project_truth.py, el gate de 1.0, derive_semver) esta midiendo "
            "un arbol que no es el del repositorio. MEDIDO: asi se perdio el "
            "informe entero del gate de 1.0.\n\nEl arreglo es mover la "
            "deformacion a un sandbox, no añadir la excepcion."
        )

    def test_ninguna_declaracion_ha_quedado_sin_uso(self) -> None:
        """La otra direccion. Una excepcion muerta es una afirmacion falsa."""
        muertas = declaradas_sin_uso(
            _ESCRITURAS_AL_ARBOL_REAL, EXCEPCIONES_DECLARADAS, _MODULOS_EJECUTADOS
        )
        assert not muertas, (
            "hay declaraciones en EXCEPCIONES_DECLARADAS que ya no "
            "corresponden a ninguna escritura:\n  "
            + "\n  ".join(muertas)
            + "\n\nSu motivo ha dejado de ser cierto. Borrala de "
            "EXCEPCIONES_DECLARADAS: una lista de excepciones es «los sitios "
            "que hay», y esa es la clase de fuente de verdad que se queda "
            "vieja en silencio."
        )

    def test_las_excepciones_que_declaran_exigen_que_se_toque_el_arbol(self) -> None:
        """Que la lista de excepciones no este vacia por descuido.

        Una lista vacia haria que el test anterior pasara sin mirar nada y
        el de las infracciones pasara sin tener nada que explicar: los dos
        en verde, sin haber medido. MEDIDO: es exactamente lo que paso con
        la derivacion de B20 cuando la implicacion invertida dejo la lista
        vacia, y por eso el techo se nombra en vez de contarse.
        """
        assert EXCEPCIONES_DECLARADAS, (
            "EXCEPCIONES_DECLARADAS esta vacia. Si de verdad no hay ninguna "
            "escritura al arbol real, esto no es una excepcion: es una "
            "afirmacion que habria que poder comprobar, y el unico modo de "
            "comprobarla es que el instrumento registre alguna."
        )


class TestElGuardSabeDarRojo:
    """Un guard que solo sabe pasar no mide. Este comprueba que sepa fallar.

    MEDIDO, por que hace falta: los tres casos de aqui se construyen a mano
    y NO dependen de la sesion real. Un guard que solo se probara «en el
    repo, que hoy esta bien» no tendria ninguna prueba de que caeria si el
    arbol sedirtyara, y su unico requisito seria que el repo este bien.
    """

    def test_una_escritura_no_declarada_se_reporta(self) -> None:
        """El caso base del guard, con un nombre que NADIE puede declarar.

        MEDIDO, por que el nombre es inventado y no el de un escritor real:
        la primera version uso `test_b14_truth_single_reader.py` como ejemplo
        de escritor no declarado, y en cuanto ese fichero entro en
        EXCEPCIONES_DECLARADAS —que es lo que pasó al registrar su deuda— el
        contrasalto dejo de comprobar nada. Un contrasalto atado a un valor
        vivo se vuelve no-op en cuanto el valor se mueve, y un no-op en un
        contrasalto es peor que no escribirlo: el guard sigue verde y ya no
        mide su propia via de manifestacion. El ejemplo tiene que ser un
        nombre que nadie pueda declarar.
        """
        violacion = "write_text STATE.yaml <- test_que_no_existe.py:1 test_que_no_existe"
        assert no_declaradas([violacion], EXCEPCIONES_DECLARADAS) == (violacion,), (
            "una escritura de un fichero de test NO declarado tiene que "
            "aparecer en el veredicto. Si esto falla, el guard pasa en verde "
            "con un escritor desconocido, que es justo el defecto."
        )

    def test_una_escritura_declarada_no_se_reporta(self) -> None:
        declaradas = {"test_algo.py": "porque si"}
        Violacion = "write_text STATE.yaml <- test_algo.py:1 test_x"
        assert no_declaradas([Violacion], declaradas) == (), (
            "una escritura declarada tiene que quedar fuera del veredicto, o "
            "la excepcion no serviria para nada."
        )

    def test_el_fichero_se_saca_del_marco_y_no_de_la_ruta(self) -> None:
        """El marco manda, no la ruta del fichero de datos.

        `STATE.yaml` no lleva nombre de test: si se partiese por la ruta,
        toda infraccion del estado cairia en un «fichero» llamado
        `STATE.yaml` que no esta en el mapa y el veredicto seria
        indistinguible del caso sin declaracion.
        """
        assert sitio_de("write_text STATE.yaml <- test_x.py:9 test_y") == "test_x.py"
        assert sitio_de("write_text a/b/c.json <- test_z.py:3 test_w") == "test_z.py"

    def test_una_declaracion_muerta_se_reporta(self) -> None:
        declaradas = {"test_que_no_escribe.py": "motivo"}
        assert declaradas_sin_uso([], declaradas, {"test_que_no_escribe.py"}), (
            "una declaracion que no corresponde a ninguna escritura tiene que "
            "aparecer, o el mapa se queda lleno de motivos que ya no son "
            "ciertos y nadie se entera."
        )

    def test_una_declaracion_viva_no_se_reporta(self) -> None:
        declaradas = {"test_algo.py": "motivo"}
        assert (
            declaradas_sin_uso(["write_text X <- test_algo.py:1 t"], declaradas, {"test_algo.py"})
            == ()
        )


# ===========================================================================
# R2 — un predicado que revienta NO borra el informe de los otros
# ===========================================================================
#
# MEDIDO, el incidente: `scripts/measure_b9_gate_1_0.py` envolvia el bucle de
# predicados en un `except Exception` que imprimia «el informe NO esta
# completo» y salia con 2. Una sola excepcion —la de
# `_distribution_reproducible`, que comparaba el contenido de
# `src/skillgraph/__init__.py` mientras un test lo deformaba— borro los
# veredictos de las otras diecinueve propiedades y `listo_para_1_0` dejo de
# calcularse. No fue un OPEN: fue CERO informacion sobre el gate de 1.0.
#
# Por que NO_MEASURABLE y no OPEN
# -------------------------------
# `OPEN` es una afirmacion sobre el PROYECTO. Un predicado que revienta no ha
# medido, luego no puede afirmar nada del proyecto: lo que sabe es que no pudo
# mirar. Y `listo_para_1_0` exige las veinte en `PASS`, asi que el 1.0 sigue
# sin poder declararse — que es lo correcto y no un castigo.


def _carga_el_gate() -> object:
    """El gate como modulo, con la identidad que `dataclass` exige.

    MEDIDO, y es una trampa de la casa: sin `sys.modules[...] = modulo` ANTES
    de `exec_module`, un `@dataclass(frozen=True, slots=True)` revienta con
    `AttributeError: 'NoneType' object has no attribute '__dict__'`, porque
    `_is_type` busca el modulo de la clase y no lo encuentra. El sintoma —
    un `AttributeError` en la importacion— no dice nada de la causa.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gate_b22_en_prueba", RAIZ / "scripts" / GATE)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b22_en_prueba"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


GATE = "measure_b9_gate_1_0.py"


class TestUnPredicadoQueRientaNoBorraElInforme:
    """Lo UNICO que mide: que los demas veredictos sobrevivan."""

    def test_el_predicado_roto_da_veredicto_y_no_excepcion(self) -> None:
        gate = _carga_el_gate()

        def revienta() -> tuple[str, str]:
            raise AssertionError("tocar la fecha no puede cambiar el texto")

        medidas = gate.evaluar(  # type: ignore[attr-defined]
            ("distribution reproducible",), {"distribution_reproducible": revienta}
        )
        assert len(medidas) == 1, f"una propiedad, un veredicto: {medidas}"
        assert medidas[0].veredicto == "NO_MEASURABLE", (
            f"un predicado que revienta tiene que salir como NO_MEASURABLE, y "
            f"salio {medidas[0].veredicto!r}. OPEN seria afirmar sobre el "
            "proyecto algo que no se ha medido."
        )

    def test_el_veredicto_roto_nombra_la_causa(self) -> None:
        """Un verificador que dice «fallo» sin decir cual deja el trabajo a otro."""
        gate = _carga_el_gate()

        def revienta() -> tuple[str, str]:
            raise AssertionError("tocar la fecha no puede cambiar el texto")

        medidas = gate.evaluar(  # type: ignore[attr-defined]
            ("distribution reproducible",), {"distribution_reproducible": revienta}
        )
        evidencia = medidas[0].evidencia
        assert "AssertionError" in evidencia, (
            f"la evidencia no dice la clase de la excepcion: {evidencia!r}"
        )
        assert "tocar la fecha no puede cambiar el texto" in evidencia, (
            f"la evidencia no dice el mensaje: {evidencia!r}"
        )
        assert "distribution reproducible" in evidencia, (
            f"la evidencia no nombra la propiedad a la que pertenece: {evidencia!r}"
        )

    def test_un_predicado_roto_impide_declarar_1_0(self) -> None:
        gate = _carga_el_gate()

        def revienta() -> tuple[str, str]:
            raise RuntimeError("boom")

        medidas = gate.evaluar(  # type: ignore[attr-defined]
            ("distribution reproducible",), {"distribution_reproducible": revienta}
        )
        assert not gate.listo_para_1_0(medidas), (  # type: ignore[attr-defined]
            "con un predicado sin medir, listo_para_1_0 tiene que ser False. "
            " Declarar 1.0 sobre una pregunta que nadie respondio es "
            "justo lo que el roadmap llama «TODAS»."
        )

    def test_los_demas_predicados_conservan_su_veredicto(self) -> None:
        """La propiedad de verdad: el informe entero sigue existiendo.

        MEDIDO por que hace falta este y no el anterior: los tres de arriba
        comprueban UN predicado roto en aislamiento. Este pone uno roto entre
        varios que responden, que es la forma en que se produjo la perdida,
        y exige que el informe siga teniendo una medida por propiedad.
        """
        gate = _carga_el_gate()
        nombres = (
            "distribution reproducible",
            "concurrencia real certificada",
            "crash/recovery real certificado",
        )

        def revienta() -> tuple[str, str]:
            raise AssertionError("tocar la fecha no puede cambiar el texto")

        medidas = gate.evaluar(  # type: ignore[attr-defined]
            nombres,
            {
                "distribution_reproducible": revienta,
                "concurrencia_real_certificada": lambda: ("PASS", "medido de verdad"),
                "crash_recovery_real_certificado": lambda: ("OPEN", "no se cumple"),
            },
        )
        assert len(medidas) == 3, f"tres propiedades, tres medidas: {medidas}"
        por_nombre = {x.nombre: x.veredicto for x in medidas}
        assert por_nombre["distribution reproducible"] == "NO_MEASURABLE"
        assert por_nombre["concurrencia real certificada"] == "PASS"
        assert por_nombre["crash/recovery real certificado"] == "OPEN"
        resumen = gate.resumir(medidas)  # type: ignore[attr-defined]
        assert resumen["PASS"] == 1 and resumen["OPEN"] == 1, f"el resumen:{resumen}"
        assert resumen["NO_MEASURABLE"] == 1, f"el resumen:{resumen}"
