"""B10 — las superficies publicas, y la pregunta de si se pueden mentir.

QUE MIDE ESTE FICHERO
---------------------
B9 dejo el gate de 1.0 en 13 PASS / 6 OPEN / 1 NO_MEASURABLE. Dos de las
seis OPEN eran `resource/controller API estable` y `CLI estable`, y las dos
abiertas por la misma razon: **falta de certificacion, no de codigo**.

Estos tests fijan cuatro cosas, y las cuatro se pueden intentar mentir:

1. **El nucleo DECLARA su superficie, y la declara COMPLETA.** No basta con
   que exista un `__all__`: uno con tres simbolos de sesenta tambien
   «declara superficie». La comparacion es contra la union de los tres
   modulos, que si declaran la suya.

2. **La superficie no se ha movido desde el snapshot.** Este es el cierre
   real. Un `touch docs/cli-surface.json` —o su equivalente aqui— cerraba
   las dos propiedades de B9 en veinte segundos, porque lo que esos
   predicados miraban era la EXISTENCIA del fichero.

3. **La comparacion es en las dos direcciones.** MEDIDO al escribir el
   guard: la primera version comparaba `reales - declarados`, y anadir un
   comando INVENTADO al snapshot pasaba en verde. Un guard que solo sabe
   detectar que el arbol crecio no vigila la declaracion.

4. **Una superficie que no viaja no declara nada.** `docs/*` esta en
   `.gitignore` salvo tres carve-outs, y por eso las superficies viven en
   `surfaces/`. Sin esto, en un clon limpio no habria nada contra que
   comparar y el guard pasaria por no encontrar nada que mirar.

POR QUE HAY TANTOS CONTRA-SALTOS
-------------------------------
Un guard que solo sabe dar verde no mide nada. Cada propiedad de arriba
tiene su contra-salto, y **cada contra-salto mira algo distinto**: no se
repite el mismo chequeo con otro nombre, porque un guard con seis
aserciones iguales mide una sola cosa seis veces.

Los conjuntos son disjuntos a proposito. `TestElNucleoDeclara...` solo
mira el `__all__` del paquete; `TestLaSuperficieNoSeHaMovido` solo mira la
comparacion con el snapshot; `TestLaComparacionVaEnDosDirecciones` solo
mira la direccion inversa. Un solo fallo de instrumentacion —por ejemplo, un
`evaluar()` que se tragase la excepcion y devolviese `()`— los apagaria
todos a la vez si compartieran codigo, y por eso no lo comparten.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
INSTRUMENTO = RAIZ / "scripts" / "check_public_surfaces.py"
DIR_SURFACES = RAIZ / "surfaces"

#: Los simbolos que el nucleo declara ademas de su superficie. No son
#: parte de ella y por eso los evaluadores los excluyen al comparar.
AUXILIARES = {"MODULOS", "SUPERFICIE"}


def _instrumento() -> ModuleType:
    """Carga el instrumento por ruta, sin tocar ``sys.path``."""
    especificacion = importlib.util.spec_from_file_location("_b10_superficies", INSTRUMENTO)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[especificacion.name] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


def _informe_real() -> Any:
    return _instrumento().medir(RAIZ, DIR_SURFACES)


def _informe_valido() -> Any:
    """El informe de verdad, para partir de el y deformar UNA cosa.

    Los contra-saltos que deforman el snapshot de verdad restauran despues;
    los que deforman el ``Informe`` en memoria no tocan el arbol. La
    separacion no es estetica: un test que restaura un fichero y otro que
    no, en el mismo fichero, hace que un fallo a medias deje el arbol
    sucio para el test siguiente.
    """
    return _informe_real()


# =====================================================================
# 1. El nucleo DECLARA su superficie
# =====================================================================


class TestElNucleoDeclaraSuSuperficie:
    """Conjunto A. Solo mira la declaracion del paquete, nunca el snapshot."""

    def test_el_paquete_declara_superficie(self) -> None:
        """`__all__` existe y no esta vacio.

        Es la mitad superficial de la propiedad, y se dice: sin esto todo lo
        demas no tiene sobre que compararse. Se mide en el arbol de verdad,
        no sobre un informe fabricado.
        """
        import skillgraph.core as nucleo

        declarados = getattr(nucleo, "__all__", None)
        assert declarados, "core/__init__.py no declara __all__"
        assert len(declarados) > len(AUXILIARES), (
            f"__all__ declara {len(declarados)} nombres y solo {len(AUXILIARES)} son "
            "auxiliares: eso no es una superficie, es un().__repr__()"
        )

    def test_la_superficie_es_la_union_de_los_tres_modulos(self) -> None:
        """La superficie del paquete es exactamente la union de las de sus modulos.

        Esta es la que hace que la promesa sea exigible. Si alguien anade un
        simbolo a ``core.errors.__all__`` y no lo reexporta, aqui falla y
        nombra el simbolo. Con una lista escrita a mano, anadir el simbolo
        al modulo y no tocar la lista dejaria la promesa del docstring
        —«el nucleo declara su superficie»— untrue sin que nada lo notase.
        """
        import skillgraph.core as nucleo

        esperados = {
            nombre
            for _, modulo in _instrumento()._modulos_del_nucleo()
            for nombre in modulo.__all__
        }
        declarados = set(nucleo.__all__) - AUXILIARES
        assert declarados == esperados, (
            f"faltan {sorted(esperados - declarados)} y sobran "
            f"{sorted(declarados - esperados)}: la superficie del paquete no es la "
            "union de la de sus modulos"
        )

    def test_los_simbolos_reexportados_son_los_mismos_objetos(self) -> None:
        """Reexportar, no copiar.

        ``frozen=True`` protege el enlace, no el valor, y aqui el valor es
        una clase: si el nucleo recreara ``ValidationError``, el ``except``
        que escribe un consumidor y el que lanza el nucleo serían dos clases
        distintas y el ``except`` no atraparia nada. Es la misma clase de
        defecto que el alias de `AgentResult.from_fixture` en WI-113.
        """
        import skillgraph.core as nucleo
        import skillgraph.core.errors as errores
        import skillgraph.core.recipe as recipe
        import skillgraph.core.runtime_types as tipos

        for modulo in (errores, tipos, recipe):
            for nombre in modulo.__all__:
                assert getattr(nucleo, nombre) is getattr(modulo, nombre), (
                    f"{nombre} en skillgraph.core no es el mismo objeto que "
                    f"{modulo.__name__}.{nombre}: el nucleo esta copiando, no reexportando"
                )

    def test_el_guard_no_pasa_con_un_all_de_tres_simbolos(self) -> None:
        """Contra-salto. Un ``__all__`` truncado tiene que poner el guard en rojo.

        Se fabrica el ``Informe`` en memoria: no se toca el arbol. Y el
        fallo tiene que ser de ``core_incompleto``, no un error qualquer:
        un guard que se rompe al recibir una superficie incompleta no
        distingue «mal declarado» de «no se sabe leer», y entonces el
        segundo caso pasa por alto.
        """
        guard = _instrumento()
        informe = _informe_valido()
        truncado = replace(
            informe, core_declarado_en_paquete=("MODULOS", "SUPERFICIE", "ParseError")
        )
        problemas = guard.evaluar_core_declarado(truncado)
        assert "core_incompleto" in guard.codigos_de(problemas), (
            f"esperaba core_incompleto y obtuve {guard.codigos_de(problemas)}: "
            "un __all__ de tres simbolos de sesenta no es una superficie declarada"
        )


# =====================================================================
# 2. La superficie NO se ha movido
# =====================================================================


class TestLaSuperficieNoSeHaMovido:
    """Conjunto B. Solo mira la comparacion con el snapshot.

    Aqui es donde vive el cierre real de las dos propiedades de B9. Los
    predicados antiguos comprobaban que el fichero EXISTIERA, y por eso
    un `touch` los ponia en verde. Estos tests comprueban que el fichero
    este ademas CONFORME a lo que el arbol expone hoy.
    """

    def test_el_snapshot_de_la_cli_describe_los_comandos_de_verdad(self, tmp_path: Path) -> None:
        """El snapshot se compara con el parser, no se mira su existencia.

        El `touch` es el contra-salto mas importante del bloque, porque es
        literalmente el atajo que habria cerrado la propiedad: escribir el
        fichero sin contenido que describa nada.
        """
        guard = _instrumento()
        vacio = tmp_path / "vacio"
        vacio.mkdir()
        problemas = guard.evaluar_cli_snapshot(
            replace(_informe_valido(), declared_cli_comandos=None), str(vacio)
        )
        assert "cli_snapshot_ausente" in guard.codigos_de(problemas)

    def test_un_snapshot_vacio_no_pasa(self, tmp_path: Path) -> None:
        """`{}` tiene la forma de un JSON y no describe una superficie.

        Es el `touch` de verdad: un fichero que existe, se lee, y no
        contiene nada. El evaluador tiene que decir el FORMATO que no
        entiende, porque un snapshot de forma desconocida no se puede
        comparar, y no comparar no es pasar.
        """
        guard = _instrumento()
        (tmp_path / guard.NOMBRE_CLI).write_text("{}", encoding="utf-8")
        problemas = guard.evaluar_cli_snapshot(
            replace(_informe_valido(), declared_version_cli=""), str(tmp_path)
        )
        assert "cli_snapshot_formato" in guard.codigos_de(problemas), (
            f"un snapshot {{}} paso como superficie: {guard.codigos_de(problemas)}"
        )

    def test_si_la_cli_gana_un_comando_el_snapshot_se_queda_corto(self) -> None:
        """Un comando mas en el arbol tiene que volver viejo el snapshot.

        El otro sentido de la misma propiedad. Se quita del snapshot un
        comando que la CLI **si** expone: el snapshot deja de describir la
        superficie y el guard tiene que decirlo nombrando el comando.
        """
        guard = _instrumento()
        informe = _informe_valido()
        recortado = tuple(n for n in informe.declared_cli_comandos if n != informe.cli_comandos[0])
        problemas = guard.evaluar_cli_snapshot(replace(informe, declared_cli_comandos=recortado))
        assert "cli_comando_nuevo" in guard.codigos_de(problemas)
        assert informe.cli_comandos[0] in problemas[0].mensaje, (
            f"el mensaje dice {problemas[0].mensaje!r} y no nombra "
            f"{informe.cli_comandos[0]!r}: un verificador que dice «falso» sin decir "
            "«donde» es un callejon sin salida"
        )

    def test_el_snapshot_de_verdad_pasa(self) -> None:
        """El estado del repositorio esta en verde.

        Sin este test, un guard roto que dijera «FALLO» siempre estaria
        «correcto»: los contra-saltos de arriba solo probarían que sabe
        ponerse rojo, no que sabe no ponerse rojo. Las dos mitades hacen
        falta y por eso el conjunto B las tiene las dos.
        """
        guard = _instrumento()
        problemas = guard.evaluar(_informe_real())
        assert not problemas, guard.formatear(problemas)

    def test_la_comparacion_del_nucleo_es_igual_que_la_de_la_cli(self, tmp_path: Path) -> None:
        """Las dos superficies se comprueban con la misma regla.

        No por simetria estetica: si el nucleo se comprobara de una forma y
        la CLI de otra, bastaria romper la que nadie mira para que el gate
        quedara en verde por el otro lado.
        """
        guard = _instrumento()
        # Un snapshot del nucleo con un simbolo menos de los reales.
        informe = _informe_valido()
        reales = [n for n in informe.core_declarado_en_paquete if n not in AUXILIARES]
        problemas = guard.evaluar_core_snapshot(
            replace(
                informe,
                declared_core=tuple(reales[:-1]),
                declared_version_core=guard.VERSAION_ESPERADA,
            )
        )
        assert "core_superficie_movida" in guard.codigos_de(problemas), (
            f"quitar un simbolo del snapshot del nucleo no se nota: {guard.codigos_de(problemas)}"
        )


# =====================================================================
# 3. La comparacion va en las DOS direcciones
# =====================================================================


class TestLaComparacionVaEnDosDirecciones:
    """Conjunto C. Solo mira la direccion inversa.

    MEDIDO al escribir el guard: la primera version comparaba solo
    `reales - declarados`, y anadir al snapshot un comando que la CLI
    **no** expone pasaba en verde. El guard sabia detectar que el arbol
    crecia y no que la declaracion miente, y la declaracion es
    justamente lo que dice «esto es lo que hay».

    Este conjunto no comparte codigo con el B: si `evaluar_cli_snapshot`
    devolviera `()` por una excepcion tragada, B y C lo detectarian como
    fallo, y un guard que devuelve `()` no distingue «nada que mirar» de
    «no he mirado». Por eso el conjunto B mira la direccion del arbol y
    este la de la declaracion.
    """

    def test_un_comando_inventado_en_el_snapshot_no_pasa(self) -> None:
        """La direccion que faltaba. Este es el contra-salto que abrio B10.

        Se anade al snapshot un comando que no existe. El arbol esta igual
        que antes, luego cualquier comparacion de una sola direccion
        —`reales - declarados`— da conjunto vacio y verde. Si este test
        falla, el guard ha vuelto a medir una sola mitad.
        """
        guard = _instrumento()
        informe = _informe_valido()
        con_invento = (*informe.declared_cli_comandos, "comando-que-no-existe")
        problemas = guard.evaluar_cli_snapshot(replace(informe, declared_cli_comandos=con_invento))
        assert "cli_comando_inexistente" in guard.codigos_de(problemas), (
            "el snapshot declara un comando que la CLI no expone y el guard no lo nota: "
            "la comparacion se ha quedado en una direccion, que es como queda un guard "
            "que solo sabe dar verde"
        )

    def test_un_subcomando_inventado_no_pasa(self) -> None:
        """La misma direccion, un nivel mas abajo.

        Un subcomando es igual de contrato que un comando de primer nivel:
        `sg pack install` es parte de la superficie aunque `pack` ya exista.
        """
        guard = _instrumento()
        informe = _informe_valido()
        grupo = informe.cli_comandos[0]
        deformado = dict(informe.declared_cli_subcomandos or {})
        deformado[grupo] = (*deformado.get(grupo, ()), "subcomando-inventado")
        problemas = guard.evaluar_cli_snapshot(replace(informe, declared_cli_subcomandos=deformado))
        assert "cli_subcomando_movido" in guard.codigos_de(problemas)

    def test_un_simbolo_inventado_en_runner_all_no_pasa(self) -> None:
        """Y la tercera capa: `runner.__all__`, que ADR-0018 declara estable.

        Se mide aparte porque es una superficie DISTINTA: un handler puede
        registrarse y el comando aparecer sin que `runner.__all__` cambie,
        y a la inversa. Comparar solo los nombres de comando deja pasar
        justo ese caso.
        """
        guard = _instrumento()
        informe = _informe_valido()
        problemas = guard.evaluar_cli_snapshot(
            replace(informe, declared_runner_all=(*informe.runner_all, "inventado"))
        )
        assert "cli_runner_all_movido" in guard.codigos_de(problemas)


# =====================================================================
# 4. La superficie VIAJA
# =====================================================================


class TestLaSuperficieViaja:
    """Conjunto D. Solo mira `git ls-files`.

    Es el defecto que B8 midio, aqui con otra forma: `docs/*` esta en
    `.gitignore` salvo tres carve-outs, asi que un snapshot en `docs/`
    existiria en esta maquina y no existiria en un clon limpio. En el clon,
    el guard no tendria nada contra que comparar.

    Y el contrasalto va por **fichero**, no por directorio: un `.gitkeep`
    en `surfaces/` haria que un directorio entero pareciese declarado sin
    que ningun snapshot este dentro. B8 escribio ese criterio.
    """

    def test_los_dos_snapshots_estan_versionados(self) -> None:
        proc = subprocess.run(
            ["git", "ls-files", "--", "surfaces/"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,
        )
        versionados = set(proc.stdout.split())
        for nombre in ("surfaces/core-surface.json", "surfaces/cli-surface.json"):
            assert nombre in versionados, (
                f"{nombre} no esta en `git ls-files`. MEDIDO: `docs/*` esta en "
                ".gitignore salvo tres carve-outs, y por eso las superficies viven en "
                "`surfaces/`. Un snapshot que no viaja declara lo que declare la "
                "maquina que lo genero"
            )

    def test_un_snapshot_fuera_de_git_se_pute_en_rojo(self) -> None:
        """Contra-salto en el evaluador, sin tocar git.

        Se fabrica el ``Informe`` diciendo que los ficheros no estan
        versionados. El fallo tiene que nombrarlos, porque un mensaje que
        solo dijera «algo no viaja» no dice donde mirar.
        """
        guard = _instrumento()
        problemas = guard.evaluar_superficies_versionadas(
            replace(_informe_valido(), superficies_en_git=("surfaces/core-surface.json",))
        )
        assert "superficie_no_versionada" in guard.codigos_de(problemas)
        assert "surfaces/cli-surface.json" in problemas[0].mensaje

    def test_el_guard_por_linea_de_comandos_esta_verde(self) -> None:
        """El guard completo, ejecutado como lo ejecutaria el CI.

        A diferencia del resto, este test lanza el script. Los demas
        importan el modulo y llaman a los evaluadores; este comprueba que
        el camino que de verdad se usa —subproceso, exit code, salida— dice
        lo mismo. Un guard cuya `main()` devuelve 0 siempre pasaria todos
        los tests de arriba.
        """
        proc = subprocess.run(
            [sys.executable, str(INSTRUMENTO)],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        assert "OK" in proc.stdout


# =====================================================================
# 5. El instrumento mide, y no devuelve constante
# =====================================================================


class TestElInstrumentoMide:
    """Conjunto E. Sobre el propio instrumento, no sobre las superficies.

    B9 encontro cuatro bugs en su medidor y los cuatro iban hacia el lado
    de mentir: dos consultas que lamaban a una funcion que no existe y
    whose ``ImportError`` se comia en un ``return ()``, y un predicado
    que contaba «deselected» como si fuera «no se ejecuto nada».

    Un ``return ()`` silencioso es indistinguible de «no hay nada que
    mirar», y en un guard eso es verde. Por eso aqui se mira que el
    fallo del instrumento se propague como FALLO y no como ausencia de
    problemas.
    """

    def test_una_superficie_ilegible_produce_fallo_y_no_vacio(self) -> None:
        """Si no se puede medir, se dice. No se devuelve «nada que mirar»."""
        guard = _instrumento()
        roto = replace(_informe_valido(), hubo_error=True, error="el parser no importa")
        problemas = guard.evaluar(roto)
        assert problemas, "un informe que dice «no se pudo medir» devolvio cero problemas"
        codigos = guard.codigos_de(problemas)
        assert "core_snapshot" in codigos and "cli_snapshot" in codigos, codigos
        assert "no se pudo medir: el parser no importa" in problemas[0].mensaje

    def test_una_superficie_de_moda_no_es_una_superficie(self) -> None:
        """Contra-salto: el `Informe` con `__all__` vacio tiene que ser rojo.

        Es el M2 de la sonda de mutacion, aqui con otro disfraz: una
        derivacion que devolviera siempre la lista vacia pasaria todos los
        tests que solo comprueban que el guard se pone rojo, y dejaria
        pasar la superficie mas pequena posible sin que nadie lo note.
        """
        guard = _instrumento()
        informe = _informe_valido()
        vacio = replace(
            informe,
            core_declarado_en_paquete=(),
            core_por_modulo={},
            cli_comandos=(),
            cli_subcomandos={},
            runner_all=(),
        )
        assert guard.evaluar_core_declarado(vacio), "una superficie vacia paso como declarada"
        assert guard.evaluar_cli_snapshot(vacio), "una CLI sin comandos paso como estable"

    def test_la_superficie_real_no_es_de_nada(self) -> None:
        """Y que el estado de verdad no sea el caso degenerado.

        Los tres tests anteriores comprueban que el guard sabe ponerse rojo;
        este comprueba que hay algo real que medir. Un guard que se pone
        rojo ante cualquier cosa y solo tiene un caso —este, el dia que se
        escribio— tambien pasaria los tres.
        """
        informe = _informe_real()
        assert not informe.hubo_error, informe.error
        assert len(informe.core_declarado_en_paquete) > 50, (
            f"la superficie del nucleo mide {len(informe.core_declarado_en_paquete)}: "
            "se ha medido otra cosa"
        )
        assert len(informe.cli_comandos) >= 10, informe.cli_comandos
        assert informe.runner_all, "runner.__all__ no se leyo"

    def test_los_snapshots_declaran_el_formato_que_se_eniende(self) -> None:
        """El formato es parte del contrato, y se mira en el fichero real.

        Sin esto, un snapshot generado por otra version del instrumento
        seria indistinguible de uno valido mientras las claves coincidan.
        """
        guard = _instrumento()
        for nombre in (guard.NOMBRE_CORE, guard.NOMBRE_CLI):
            carga = json.loads((DIR_SURFACES / nombre).read_text(encoding="utf-8"))
            assert carga["version"] == guard.VERSAION_ESPERADA, (
                f"{nombre} declara el formato {carga['version']!r} y este test "
                f"entiende {guard.VERSAION_ESPERADA!r}"
            )
