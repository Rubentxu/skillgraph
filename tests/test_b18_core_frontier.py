"""B18: `core/` no puede depender de la implementacion, y hay que mirar de verdad.

El hallazgo
-----------
B15 nombro siete propiedades del gate que se deciden leyendo el arbol, y B16
abrio dos, B17 una. Esta es la cuarta, y su evidencia la delata antes de
mirarla: «core/ solo importa de si mismo y de la estandar (**5 modulos**)».
Y `core/` tiene **cuatro ficheros**. La cifra no son modulos, y no dice cuantos
ficheros se recorrieron, luego no permite saber si el recorrido fue completo.

Son TRES defectos, y se miden por separado porque tienen tres consecuencias
distintas y juntarlos seria un hallazgo que no se puede arreglar.

1. **Los imports RELATIVOS eran invisibles.** `_imports_de` exigia
   `nodo.level == 0`, luego solo contaba los ABSOLUTOS. Y como `core/` esta en
   `src/skillgraph/core/`, un `from ..platform.storage import Storage` tiene
   `level == 2` y **sale de `core/` entero**.

       MEDIDO A · core/ importa Storage con un import RELATIVO de nivel 2
         veredicto : PASS
         evidencia : core/ solo importa de si mismo y de la estandar (5 modulos)

   **La evidencia es la MISMA CADENA, byte a byte, que el caso limpio.** Un
   veredicto que no puede distinguir «el nucleo esta limpio» de «no he mirado la
   mitad de la superficie». Es la misma forma del defecto que B13 cerro en el
   guard de SQL y B16 cerro en la frontera del nucleo: verde con la fuga
   presente.

   Y lo que lo hace mas peligroso: MEDIDO, `core/` **no usa hoy ningun import
   relativo**. La superficie esta vacia, y una superficie vacia no se mira
   porque no hay nada que mirar.

2. **La estandar eran TRECE renglones escritos a mano.** MEDIDO: el interprete
   sabe de 290. `pathlib`, `contextlib`, `abc`, `io`, `warnings` y `copy` son de
   la estandar y **no estaban**, luego un import legitimo de cualquiera de ellos
   en `core/` habria producido un `OPEN` sobre una frontera respetandose. Una
   propiedad que se pone roja por lo contrario es una propiedad que entrena a su
   lector a no creerla, y ese fallo es tan malo como el de dar verde: los dos
   hacen que el veredicto deje de ser informacion.

3. **La evidencia no describia lo que recorrio.** Veintidos caracteres de
   numero sin nombre.

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
RUNTIME_TYPES = "src/skillgraph/core/runtime_types.py"
ANCLA = "from __future__ import annotations\n"


def _carga() -> object:
    spec = importlib.util.spec_from_file_location("gate_b18", GATE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gate_b18"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class _ArbolCopiado:
    """Una copia de `src/` con `RAIZ` apuntando a ella, y restaura al salir.

    MEDIDO: en B14 se midio mutando el arbol REAL y restaurando por sha256, que
    funciona pero deja el repo en un estado que existio de verdad. Una copia no
    deja rastro ni necesita red de seguridad, y para estas deformaciones —que no
    tocan el codigo que se mira sino lo que se COMPRA— es exactamente lo que
    hace falta: el gate se ejecuta de verdad, contra un arbol donde la cosa
    esta estropeada.
    """

    def __init__(self) -> None:
        self._raiz_real = RAIZ
        self._destino: Path | None = None

    def __enter__(self) -> _ArbolCopiado:
        self._tmp = tempfile.TemporaryDirectory(prefix="b18_")
        self._destino = Path(self._tmp.name)
        shutil.copytree(self._raiz_real / "src", self._destino / "src", symlinks=True)
        self._modulo = _carga()
        self._modulo.RAIZ = self._destino
        return self

    def __exit__(self, *_exc: object) -> None:
        self._modulo.RAIZ = self._raiz_real
        self._tmp.cleanup()

    def anade_import_relativo(self, relativo: str, nivel: int, modulo: str) -> None:
        """Mete en `core/` un import RELATIVO que sale del nucleo.

        Se escribe como lo escribiria una persona, con los puntos de verdad: un
        `level` de mas no se puede escribir a mano sin que Python revente al
        importar, y aqui lo que se mide es que el GATE lo note.
        """
        self._anade_import(relativo, f"from {'.' * nivel}{modulo} import ALGO  # noqa: F401")

    def anade_import_absoluto(self, relativo: str, modulo: str) -> None:
        """Mete en `core/` un import ABSOLUTO.

        **POR QUE HACE FALTA, Y NO ES UN EXTRA.** La primera version de este
        fichero solo tenia el metodo relativo, y el test de la estandar lo uso
        para meter `pathlib` —con lo que escribio `from .pathlib import ...`,
        que resuelve a `skillgraph.core.pathlib`, DENTRO del nucleo, y se
        descarta antes de llegar a la comprobacion de la estandar—. El test
        pasaba, y no porque la estandar se derivara del interprete, sino
        porque nunca llego a mirarla.

        MEDIDO al revertir la constante a la lista de trece renglones: el guard
        **no cayo**. Ese es el momento en el que se sabe que un test no esta
        midiendo lo que su nombre dice, y no es leyendo el test: es cambiando
        lo que el test vigila y viendo si se entera. Un test que verifica que
        su deformacion llego al sitio que dice es tan parte del guard como el
        test mismo.
        """
        self._anade_import(relativo, f"import {modulo}  # noqa: F401")

    def _anade_import(self, relativo: str, sentencia: str) -> None:
        ruta = self._destino / relativo
        texto = ruta.read_text(encoding="utf-8")
        if texto.count(ANCLA) != 1:
            raise AssertionError(
                f"el ancla aparece {texto.count(ANCLA)} veces en {relativo}. Si ese modulo "
                f"ha cambiado de forma, la deformacion de este test ya no es la que dice "
                f"ser, y pasaria a medir otra cosa."
            )
        ruta.write_text(
            texto.replace(ANCLA, ANCLA + f"\n{sentencia}\n", 1),
            encoding="utf-8",
        )

    @property
    def modulo(self) -> object:
        return self._modulo


# =====================================================================
class TestUnImportRelativoNoSeEscapa:
    """Lo UNICO que mide: que `core/` no pueda salir de si mismo por la via relativa.

    **Por que este conjunto existe y no es cosmetica.** La version anterior de
    `_imports_de` exigia `nodo.level == 0`. Todo import relativo se le escapaba,
    y como `core/` esta un nivel por debajo de `skillgraph`, `from ..platform
    import x` sale del nucleo entero sin que nadie lo note. MEDIDO, hoy `core/`
    no usa ningun relativo: la superficie esta vacia, y por eso nadie la mira.
    """

    def test_un_relativo_de_nivel_dos_que_sale_del_nucleo_es_open(self) -> None:
        with _ArbolCopiado() as arbol:
            arbol.anade_import_relativo(RUNTIME_TYPES, 2, "platform.storage")
            veredicto, evidencia = arbol.modulo._core_sin_dependencias_de_impl_externa()
        assert veredicto == "OPEN", (
            f"core/ importa skillgraph.platform.storage por la via RELATIVA y el "
            f"veredicto es {veredicto!r}. La frontera que declara esta propiedad es la "
            f"que permite anadir una capacidad sin tocar el nucleo, y una frontera que "
            f"alguien puede cruzar escribiendo dos puntos no es una frontera. "
            f"Evidencia: {evidencia[:250]!r}"
        )
        assert "platform.storage" in evidencia, (
            f"el veredicto es OPEN pero no dice QUE modulo: {evidencia[:250]!r}. Sin eso "
            f"quien corrige tiene que volver a mirar el nucleo entero."
        )

    def test_un_relativo_que_no_sale_no_es_open(self) -> None:
        """CONTRA-SALTO del anterior por su OTRA via, y es la direccion importante.

        Un guard que prohibiera los imports relativos arreglaria MEDIDO A y
        ROMPERIA el nucleo, porque `from .errors import ...` es correcto y es lo
        que hace `core/` hoy. Lo que se mide aqui es que un relativo que se
        QUEDA dentro del nucleo no se confunda con uno que sale: los dos son
        relativos, y solo uno viola la frontera.
        """
        with _ArbolCopiado() as arbol:
            arbol.anade_import_relativo(RUNTIME_TYPES, 1, "errors")
            veredicto, evidencia = arbol.modulo._core_sin_dependencias_de_impl_externa()
        assert veredicto == "PASS", (
            f"un `from .errors import ...` —relativo, pero DENTRO del nucleo— da "
            f"{veredicto!r}: {evidencia[:250]!r}. Prohibir los relativos seria cambiar "
            f"el codigo para que el guard quede bien, y `core/` los usa. Lo que se "
            f"mide es que se RESUELVAN, no que se prohiban."
        )


# =====================================================================
class TestLaEstandarNoEsUnaListaEscritaAMano:
    """Lo UNICO que mide: que «que es de la estandar» venga del interprete.

    **POR QUE ESTE CONJUNTO MIDE LAS DOS DIRECCIONES.** La lista escrita a mano
    de trece renglones fallaba por la via que no se ve: `pathlib`,
    `contextlib`, `abc`, `io`, `warnings` y `copy` son de la estandar y no
    estaban, luego un import legitimo de cualquiera de ellos en `core/` habria
    producido un `OPEN` sobre una frontera respetandose. Un `OPEN` falso no es
    menos defectuoso que un `PASS` falso: los dos hacen que el veredicto deje de
    ser informacion, y el falso se descubre cuando alguien quiere importar
    `pathlib` y no puede.
    """

    def test_un_modulo_de_la_estandar_que_no_figuraba_no_da_open(self) -> None:
        """`pathlib` es el testigo, y MEDIDO que no estaba en los trece."""
        with _ArbolCopiado() as arbol:
            arbol.anade_import_absoluto(RUNTIME_TYPES, "pathlib")
            veredicto, evidencia = arbol.modulo._core_sin_dependencias_de_impl_externa()
        assert veredicto == "PASS", (
            f"`pathlib` es de la estandar y el veredicto es {veredicto!r}: "
            f"{evidencia[:250]!r}. MEDIDO que no estaba en la lista escrita a mano, luego "
            f"este es el falso OPEN que la lista producia. Un guard que se pone rojo "
            f"por lo contrario entrena a su lector a no creerlo."
        )

    def test_la_evidencia_dice_de_donde_sale_la_estandar(self) -> None:
        """Que el PASS diga de donde salio su verdad, y no solo cual es.

        Un PASS que no dice como se obtuvo es el mismo PASS de antes con otra
        tipografia —y el de antes se apoyaba en una lista escrita a mano—. La
        evidencia nueva nombra el hecho del que sale y la cifra de ficheros que
        se recorrieron, que es la que faltaba para saber si el recorrido fue
        completo.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._core_sin_dependencias_de_impl_externa()
        assert veredicto == "PASS"
        assert "sys.stdlib_module_names" in evidencia, (
            f"la evidencia no dice de donde sale la verdad de «que es la estandar»: "
            f"{evidencia[:250]!r}"
        )
        assert re.search(r"MEDIDO sobre \d+ ficheros", evidencia), (
            f"la evidencia no dice cuantos ficheros se recorrieron: {evidencia[:250]!r}. "
            f"Sin esa cifra, el numero que la acompaña no permite saber si el recorrido "
            f"estaba completo —que es el defecto que B16 cerro en su otra mitad—."
        )


# =====================================================================
class TestLoQueNoSeMiraNoSeDeclaraMirado:
    """Lo UNICO que mide: que la cifra de la evidencia sea la del recorrido.

    **POR QUE UN CONJUNTO PARA UN NUMERO.** La evidencia de antes decia «(5
    modulos)» sobre un paquete de **cuatro** ficheros. El numero no era de
    modulos: era de nombres de import **distintos**. Y no decia cuantos ficheros
    se habian recorrido, luego no permitia saber si el recorrido estaba
    completo. Un PASS cuya evidencia no describe lo que recorrio no es un PASS
    sobre el proyecto: es un PASS sobre la capacidad de contar del instrumento.
    """

    def test_la_cifra_de_ficheros_es_la_de_los_ficheros(self) -> None:
        """Que los dos numeros salgan del MISMO sitio, y no de dos perguntas.

        Dos recorridos que cuentan lo mismo no pueden desincronizarse; dos
        preguntas sobre «los ficheros de core» escritas en dos sitios si, y por
        eso la cifra se toma de una funcion y no de un segundo `rglob`.
        """
        modulo = _carga()
        veredicto, evidencia = modulo._core_sin_dependencias_de_impl_externa()
        assert veredicto == "PASS"
        reales = modulo._ficheros_de("core")
        assert str(reales) in evidencia, (
            f"la evidencia no lleva el numero de ficheros que hay ({reales}): {evidencia[:250]!r}"
        )
        disco = len(list((RAIZ / "src" / "skillgraph" / "core").rglob("*.py")))
        assert reales == disco, (
            f"_ficheros_de('core') dice {reales} y en disco hay {disco}. Las dos cifras "
            f"tienen que salir del mismo recorrido, y si no el guard acaba comparando "
            f"el numero que el propio modulo se cuenta con el numero del arbol."
        )

    def test_la_evidencia_no_dice_modulos_cuando_mide_imports(self) -> None:
        """Que no llame «modulos» a los imports. CONTRA-SALTO por el TEXTO.

        La palabra «modulos» es lo que hace que un lector acepte un numero sin
        mirar. Con la cifra de ficheros delante, el numero que queda es de
        imports, y decirlo asi es lo que separa «he mirado cuatro ficheros y no hay
        ninguna dependencia» de «he mirado algo y salio esto».
        """
        modulo = _carga()
        veredicto, evidencia = modulo._core_sin_dependencias_de_impl_externa()
        assert veredicto == "PASS"
        assert re.search(r"\d+ modulos\)", evidencia) is None, (
            f"la evidencia vuelve a cerrar con un numero sin nombre: {evidencia[-200:]!r}. "
            f"«(5 modulos)» es exactamente la frase que hay que quitar: el numero no "
            f"decia que se habia recorrido nada."
        )
        assert "imports" in evidencia, (
            f"la evidencia no dice que lo que cuenta son imports: {evidencia[:250]!r}"
        )
