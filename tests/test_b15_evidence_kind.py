"""B15: un predicado que se declara leyendo codigo no sabe cuando deja de medir.

El hallazgo
-----------
El gate de 1.0 declara veinte propiedades, y hasta B15 sus veinte PASS salian
en la misma lista y con la misma tipografia. No habia manera de saber cuales
estaban respaldados por algo que se EJECUTA y cuales por una lectura del arbol.
MEDIDO, derivado del AST del propio modulo:

    ejecutada  13    derivada  7

La clase importa porque responde a una pregunta que se puede responder: **puede
esta propiedad volverse falsa sin que nadie vuelva a mirarla?** El veredicto de
una ``ejecutada`` se cae solo cuando el objeto cambia. El de una ``derivada``
solo se cae si alguien vuelve a medirlo, y no hay nadie que lo haga porque
nadie sabe que estaba midiendo.

Ademas, ``distribution reproducible`` decia PASS con la evidencia *«el wheel y
el sdist se construyen y llevan lo que declaran»*. Eso prueba que SE CONSTRUYEN.
Un unico build no puede distinguir «reproducible» de «esta vez salio bien».

Y el fallo que este bloque encontro en su propia casa en su propia casa, y que es lo que le da
sentido: la primera version de la derivacion devolvio **veinte de veinte
``derivada``**, con la autoridad de un `print` y sin una sola advertencia. Los
predicados se registran en `PREDICADOS` como `_` + slug, la funcion buscaba el
slug a secas, no lo encontraba, y devolvia un valor POR DEFECTO. Seis de esos
predicados si lanzan subproceso. Un fallo de busqueda que devuelve un valor en
vez de decir «no lo se» es el mismo defecto que este bloque persigue.

Los cuatro conjuntos son disjuntos y cada uno declara en su docstring que es lo
UNICO que mide, para que ninguno tape a otro.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import fields
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GATE = RAIZ / "scripts" / "measure_b9_gate_1_0.py"


def _carga() -> object:
    """El gate de verdad, cargado como modulo.

    Se importa en vez de leerse como texto porque la clase se deriva de SU
    AST, y un texto con una coma de mas no es el modulo que ejecuta el gate.
    """
    spec = importlib.util.spec_from_file_location("gate_b15", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b15"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# =====================================================================
class TestLaClaseSeDerivaYNoSeDeclara:
    """Lo UNICO que mide: que la clase no se pueda escribir a mano."""

    def test_el_campo_de_clase_no_se_puede_pasar_al_constructor(self) -> None:
        """`clase_evidencia` es `init=False`: no hay forma de declararlo.

        Un campo derivable que ademas acepta un valor es una puerta: basta con
        que un constructor futuro pase ``"ejecutada"`` para tener veinte
        veredictos de clase escrita a mano, y la segunda fuente de verdad
        —WI-106, WI-99— vuelve a existir sin que nadie lo note.
        """
        modulo = _carga()
        por_nombre = {f.name: f for f in fields(modulo.Propiedad)}
        assert "clase_evidencia" in por_nombre, (
            f"Propiedad no declara la clase: {[f.name for f in fields(modulo.Propiedad)]}"
        )
        assert por_nombre["clase_evidencia"].init is False, (
            "clase_evidencia acepta un valor en el constructor, luego alguien puede "
            "declararla. Se deriva, no se escribe."
        )

    def test_construir_una_propiedad_deriva_la_clase_sola(self) -> None:
        """El `__post_init__` la calcula, y no se puede pasar por alto."""
        modulo = _carga()
        nombres = modulo.propiedades_del_roadmap(modulo._lee("ROADMAP.md"))
        slug = modulo._slug(nombres[0])
        p = modulo.Propiedad(nombres[0], "PASS", "una evidencia cualquiera")
        esperada = modulo.clase_de_evidencia(slug)
        assert p.clase_evidencia == esperada, (
            f"la propiedad dice {p.clase_evidencia!r} y su predicado es {esperada!r}. "
            f"La clase tiene que venir del codigo del predicado, no del sitio desde "
            f"el que se llame."
        )

    def test_ninguna_propiedad_del_roadmap_queda_sin_clase(self) -> None:
        """Las veinte clasifican, y ninguna se queda sin clase por defecto.

        El fallo medido de la primera version fue precisamente una busqueda que
        no encontraba y devolvia `derivada`. Este test obliga a que las veinte
        se resuelvan de verdad: si un slug dejara de corresponder a su funcion,
        `_funcion_del_predicado` levanta y aqui se ve.
        """
        modulo = _carga()
        nombres = modulo.propiedades_del_roadmap(modulo._lee("ROADMAP.md"))
        sin_clase: list[str] = []
        for nombre in nombres:
            try:
                clase = modulo.clase_de_evidencia(modulo._slug(nombre))
            except LookupError as exc:
                sin_clase.append(f"{nombre}: {exc}")
                continue
            if clase not in ("ejecutada", "derivada"):
                sin_clase.append(f"{nombre}: clase inesperada {clase!r}")
        assert not sin_clase, "propiedades del gate que no se clasifican:\n  " + "\n  ".join(
            sin_clase
        )


# =====================================================================
class TestLaClaseSigueAlCodigo:
    """Lo UNICO que mide: que la clase se DERIVE y no lea una lista.

    Este conjunto es el contrasalto del anterior, y va en la direccion
    contraria: no prueba que la clase NO se pueda escribir, sino que **cambia
    sola cuando el codigo cambia**. Un guard que midiese «la lista de clases no
    se puede editar a mano» estaria vigilando la_statement, no el codigo: el
    dia que un predicado anadiera un subproceso, la lista seguiria diciendo
    `derivada` y el guard pasaria en verde con la respuesta equivocada.
    """

    #: Un predicado que HOY es `derivada`: solo lee el arbol. Si哪天 dejara de
    #: leer y empezara a ejecutar, la clase tiene que girar sola.
    UN_DERIVADA = "capabilities_deterministas"

    def test_anadir_un_subproceso_gira_la_clase_a_ejecutada(self) -> None:
        """CONTRA-SALTO: la derivacion responde al codigo, no a una lista.

        Se alimenta la derivacion con el MISMO modulo y una linea anadida al
        predicado. No se toca el fichero real: la funcion recibe el texto como
        parametro precisamente para poder hacer esto.
        """
        modulo = _carga()
        texto = GATE.read_text(encoding="utf-8")
        antes = modulo.clase_de_evidencia(self.UN_DERIVADA, texto)
        assert antes == "derivada", (
            f"{self.UN_DERIVADA} es `ejecutada` hoy, y este contrasalto mide que un "
            f"predicado QUE NO EJECUTA se declare `derivada`. Si el cambio de clase "
            f"esta roto en la direccion contraria, este test no mide lo que dice."
        )
        deformado = texto.replace(
            f"def _{self.UN_DERIVADA}() -> tuple[Veredicto, str]:",
            f"def _{self.UN_DERIVADA}() -> tuple[Veredicto, str]:\n"
            '    subprocess.run(["ls"], capture_output=True)',
            1,
        )
        assert deformado != texto, "el ancla no existe: el contrasalto no deformaria nada"
        despues = modulo.clase_de_evidencia(self.UN_DERIVADA, deformado)
        assert despues == "ejecutada", (
            f"el predicado ahora lanza un subproceso y la clase sigue siendo {despues!r}. "
            f"La clase no esta siguiendo al codigo: alguien la escribio a mano, o la "
            f"derivacion no llega a la llamada."
        )

    def test_cortar_el_subproceso_gira_todas_las_clases_a_derivada(self) -> None:
        """CONTRA-SALTO del anterior por su otra via de manifestacion.

        El test anterior prueba que AÑADIR un proceso gira la clase a
        `ejecutada`. Este prueba lo contrario: si la derivacion declarara
        `ejecutada` por un motivo que no sea el codigo —una lista, una constante,
        un caso especial— quitarle el proceso a TODO el modulo la dejaria
        intacta, y el guard anterior seguiria verde.

        Se sustituyen TODAS las appearances de `subprocess.` por un modulo que
        no existe. La primera version de este contrasalto sustituia solo la
        primera, que puede estar en un helper que ningun predicado usa, y el
        grafo del predicado elegido no cambiaba: el test caia por un motivo que
        no era el suyo. Una deformacion que a veces no deforma no es una
        deformacion.
        """
        modulo = _carga()
        texto = GATE.read_text(encoding="utf-8")
        grafo = modulo._grafo_del_modulo(texto)
        # Se pregunta por la clase con la FUNCION PUBLICA y no mirando el
        # grafo, y se itera por `PREDICADOS` y no por el grafo. MEDIDO: la
        # primera version filtraba con `slug in grafo`, y el grafo indexa por
        # nombre de funcion —con su `_`— luego la lista salia VACIA y el
        # contrasalto se quejaba de que no hay nada que comprobar, en vez de
        # comprobar las trece. Es la cuarta vez en este bloque que una busqueda
        # que no encuentra devuelve una lista vacia en lugar de levantar: el
        # fallo de B14 en su propia casa, en la forma mas silenciosa que tiene,
        # porque una lista vacia no se parece a un error.
        ejecutadas = [
            slug
            for slug in sorted(modulo.PREDICADOS)
            if modulo.clase_de_evidencia(slug, texto) == "ejecutada"
        ]
        assert ejecutadas, (
            "no hay ni una propiedad `ejecutada` hoy, luego este contrasalto no mediria "
            "nada: comprobaria que una lista vacia sigue vacia."
        )

        deformado = texto.replace("subprocess.", "modulo_que_no_existe.")
        grafo_deformado = modulo._grafo_del_modulo(deformado)
        assert grafo_deformado != grafo, (
            "quitar `subprocess` del modulo no cambio el grafo, luego la senal que la "
            "derivacion mira no es el subproceso y este contrasalto no mide lo que dice."
        )
        siguen_ejecutadas = [
            slug for slug in ejecutadas if modulo.clase_de_evidencia(slug, deformado) == "ejecutada"
        ]
        assert not siguen_ejecutadas, (
            f"con el modulo sin `subprocess` nadie puede lanzar un proceso, y aun asi "
            f"{siguen_ejecutadas} siguen declaradas `ejecutada`. La clase no sale del codigo."
        )


# =====================================================================
class TestUnaBusquedaQueNoEncuentraNoInventaUnaRespuesta:
    """Lo UNICO que mide: el fallo de busqueda LEVANTA en vez de devolver.

    MEDIDO en la primera version de este bloque: las veinte propiedades
    salieron `derivada` porque la funcion buscaba el slug sin el `_` con el que
    se registran, no lo encontraba, y **devolvia `derivada` por defecto**. Seis
    de esos predicados si lanzan subproceso. El numero salia con la autoridad de
    un `print` y no habia nada que lo contradijera.
    """

    def test_un_slug_inexistente_no_devuelve_una_clase(self) -> None:
        modulo = _carga()
        try:
            clase = modulo.clase_de_evidencia("este_predicado_no_existe")
        except LookupError as exc:
            assert "no lo se" in str(exc) or "no corresponde" in str(exc), (
                f"el mensaje no dice que es un fallo de busqueda: {exc}"
            )
            return
        raise AssertionError(
            f"un slug que no existe devolvio {clase!r} en vez de levantar. Un fallo de "
            f"busqueda que devuelve un valor es como se produjo el veinte de veinte "
            f"`derivada` que este bloque vino a cerrar."
        )

    def test_el_mensaje_dice_las_dos_mitades_del_fallo(self) -> None:
        """El mensaje nombra el slug Y la convencion de registro.

        Un verificador que dice «falso» sin decir donde deja a quien corrige
        haciendo la cuenta a mano. Este dice: como se busca, que se busco, y
        que el resultado de la primera version fue el equivocado.
        """
        modulo = _carga()
        try:
            modulo.clase_de_evidencia("este_predicado_no_existe")
        except LookupError as exc:
            texto = str(exc)
        else:
            raise AssertionError("no levanto")
        assert "este_predicado_no_existe" in texto, "el mensaje no nombra lo que no encontro"
        assert "PREDICADOS" in texto, "el mensaje no dice donde se registran los predicados"
        assert "veinte" in texto, "el mensaje no dice que paso la primera vez"


# =====================================================================
class TestLaReproducibilidadSeMideYNoSeAfirma:
    """Lo UNICO que medir: que `distribution reproducible` compruebe algo.

    El predicado anterior ejecutaba `check_package_build.py`, que construye el
    paquete, y devolvia PASS con la evidencia *«se construyen y llevan lo que
    declaran»*. Eso no es reproducibilidad: un unico build no puede distinguir
    «reproducible» de «esta vez salio bien».
    """

    def test_la_evidencia_nombra_la_medida_y_los_dos_sha(self) -> None:
        """La evidencia tiene que decir QUE se comparó, no que se construyó.

        Si vuelve la frase antigua, el test cae. Es un guard sobre el TEXTO de
        la evidencia, y eso es legitimo aqui: lo que se vigila es precisamente
        que el verificador **diga** lo que midio, porque una evidencia que no
        nombra su medida no permite distinguirla de una afirmacion.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._distribution_reproducible()
        assert veredicto in ("PASS", "OPEN"), veredicto
        assert "construyen" not in evidencia, (
            f"la evidencia vuelve a la frase que solo dice que se construye: {evidencia!r}"
        )
        assert "REPRODUCIBLE" in evidencia or "reproducible" in evidencia, (
            f"la evidencia no dice que se comprobo la reproducibilidad: {evidencia!r}"
        )
        assert "sha256" in evidencia, f"la evidencia no nombra la magnitud comparada: {evidencia!r}"

    def test_construir_dos_veces_con_distinta_fecha_da_los_mismos_bytes(self) -> None:
        """La prueba de verdad, y la unica que significa algo.

        Construir dos veces seguidas no prueba nada: si el reloj no tick entre
        las dos, los timestamps coinciden aunque el build sea irreproducible.
        Por eso se toca la FECHA de un fuente con el contenido IDENTICO, y se
        comprueba que los bytes no cambian.
        """
        modulo = _carga()
        import tempfile
        import time

        fuente = modulo.RAIZ / modulo._FICHERO_DE_FECHA
        contenido = fuente.read_bytes()
        mtime = fuente.stat().st_mtime
        try:
            with tempfile.TemporaryDirectory(prefix="b15_t1_") as da:
                primera = modulo._construye_en(Path(da))
                time.sleep(2.1)
                futuro = time.time() + 5
                import os

                os.utime(fuente, (futuro, futuro))
                assert fuente.read_bytes() == contenido, "tocar la fecha toco el texto"
                with tempfile.TemporaryDirectory(prefix="b15_t2_") as db:
                    segunda = modulo._construye_en(Path(db))
        finally:
            import os

            os.utime(fuente, (mtime, mtime))
            fuente.write_bytes(contenido)

        assert primera, "la primera construccion no produjo artefactos"
        assert set(primera) == set(segunda), (
            f"las dos construcciones producen distinto conjunto: {sorted(primera)} vs "
            f"{sorted(segunda)}"
        )
        distintos = {n: (primera[n], segunda[n]) for n in primera if primera[n] != segunda[n]}
        assert not distintos, (
            "la distribucion NO es reproducible con el contenido identico y la fecha "
            f"distinta, y el gate lo declara PASS: {distintos}"
        )
        for nombre, digest in primera.items():
            assert len(digest) == 64, f"{nombre}: un sha256 mide 64 hex, y esto mide {len(digest)}"
