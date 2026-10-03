"""B2 — crash REAL: matar el proceso con SIGKILL y mirar el disco.

Este fichero certifica la primera mitad del gate de B2. La segunda mitad
—proveedor real— necesita credenciales y no se puede certificar aqui; se
diga en `evidence/sddk-b2-2026-10-03.md` con la misma honestidad con la
que WI-91 corrigió el addendum de H9.

**QUÉ HACE DIFERENTE A UN FAILPOINT.** Los failpoints del repo
(`SKILLGRAPH_FAILPOINT_PROMOTION` y familia) hacen que el proceso lance o
salga en un punto concreto. Eso prueba que el codigo *entiende* el crash.
No prueba que sobreviva a uno: al lanzar, Python desenrolla la pila,
ejecuta los `finally`, cierra la conexion y SQLite consolida el journal
por rollback. Es un cierre **ordenado**.

Aqui el proceso desaparece. `SIGKILL` no se captura, no se ignora y no se
bloquea: no hay desenrollado, no hay `atexit`, no hay cierre de ficheros.
Es lo que pasa cuando se apaga la maquina o cuando el OOM killer actua, y
es el unico crash del que no se puede decir que el codigo lo «entiende».

**LA PREGUNTA QUE ESTOS TESTS RESPONDEN.** No «¿el codigo sabe que hay
un crash?» sino, tras el `SIGKILL`:

    1. ¿la base sigue siendo un SQLite legible?  → `PRAGMA integrity_check`
    2. ¿el trabajo NO confirmado desaparecio ENTERO?  → ni una fila a medias
    3. ¿el trabajo confirmado SOBREVIVIO?  → no se revierte lo ya commitado

La segunda es la que importa y la que ningun failpoint puede demostrar: un
failpoint que hace `rollback` deja la base tan limpia como un commit. La
garantia que se certifica aqui es la del journal de SQLite, y para eso hay
que **apagar el proceso**.

**POR QUE EL HIJO SE MATE A SI MISMO.** Si el padre hiciera `proc.kill()`,
dependeria del momento: hay una ventana de milisegundos entre «abrió la
transaccion» y «hizo commit» que no se puede golpear de forma fiable. El
hijo se mata justo despues de la escritura que interesa, y el punto del
crash es determinista. Ver `.pipelinek/b2_crash_child.py`.

**Y POR QUE SE COMPRUEBA SIEMPRE DESPUES, NUNCA DURANTE.** Un padre que
mira lo que el hijo dijo esta probando que el hijo sabe contar. Todas las
aserciones de este fichero leen el **disco**, en solo lectura, despues de
que el proceso ya no existe.
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / ".pipelinek"))

from b2_crash_harness import (  # noqa: E402
    ejecutar_hasta_matar,
    filas_de,
    integridad,
    journal_pendiente,
    punto_de_crash,
)

EVENTOS = "SELECT event_id FROM runtime_events ORDER BY event_id"


class TestElCrashEsDelSistema:
    """Lo primero: que el proceso muere de verdad, y no de mentira."""

    def test_el_hijo_muere_por_senal_no_por_excepcion(self, tmp_path: Path) -> None:
        """`returncode` negativo = lo mato una senal.

        En POSIX, `subprocess` devuelve `-signal` cuando el hijo muere por
        senal. Un hijo que sale con `0` —porque el arnes no lo mato, o
        porque alguien cambio `SIGKILL` por `SIGTERM`— daria un test en
        verde sobre un crash que no ocurrio. Esta es la contrasenal de
        que el resto del fichero mida algo.
        """
        proc = ejecutar_hasta_matar(
            proyecto=str(tmp_path / "p"),
            operacion="escribir_y_morir",
        )
        assert proc.returncode == -signal.SIGKILL, (
            f"returncode={proc.returncode}; un crash simulado certificaria "
            "una garantia que no existe"
        )

    def test_el_hijo_alcanzo_el_punto_del_crash(self, tmp_path: Path) -> None:
        """Que murio EN el sitio, y no antes por otra causa.

        Sin esto, un hijo que fallara al importar se contaria como un
        crash del runtime. La distincion importa: una es el comportamiento
        que B2 quiere certificar y la otra es un error del arnes.
        """
        proc = ejecutar_hasta_matar(
            proyecto=str(tmp_path / "p"),
            operacion="transaccion_abierta_y_morir",
        )
        punto = punto_de_crash(proc)
        assert punto["estado"] == "transaccion-abierta", punto
        assert punto["filas"] == 2, (
            f"el hijo dijo haber escrito {punto['filas']} filas dentro de una "
            "transaccion abierta; el test asume dos"
        )


class TestLaBaseSobrevive:
    """Tras el SIGKILL, el fichero tiene que seguir siendo un SQLite."""

    @pytest.mark.parametrize(
        "operacion",
        ["escribir_y_morir", "transaccion_abierta_y_morir", "commit_y_morir"],
    )
    def test_la_base_queda_integra(self, tmp_path: Path, operacion: str) -> None:
        """`integrity_check == ok` en los tres escenarios.

        Es la pregunta mas basica y la que mas doleria fallar: un corte de
        luz a mitad de escritura no puede dejar un fichero que nadie
        pueda abrir.
        """
        proyecto = tmp_path / operacion
        ejecutar_hasta_matar(proyecto=str(proyecto), operacion=operacion)
        veredicto = integridad(proyecto / "project.sqlite")
        assert veredicto == "ok", (
            f"tras el SIGKILL en '{operacion}' la base no esta integra: "
            f"integrity_check devolvio {veredicto!r}"
        )


class TestElTrabajoNoConfirmadoDesaparece:
    """La garantia que ningun failpoint puede demostrar.

    Un failpoint que hace `rollback` deja la base tan limpia como un
    `commit`: los dos caminos se ven iguales desde fuera. Aqui se apaga el
    proceso, y la diferencia se ve.
    """

    def test_lo_escrito_sin_confirmar_no_aparece(self, tmp_path: Path) -> None:
        """`INSERT` ejecutado y `commit` sin llegar: no queda rastro.

        El hijo hizo el INSERT y murio antes de confirmar. Al reabrir no
        debe haber ni una fila: una escritura a medias que sobreviviese
        seria un registro que nadie sabe si es real.
        """
        proyecto = tmp_path / "p"
        proc = ejecutar_hasta_matar(proyecto=str(proyecto), operacion="escribir_y_morir")
        assert punto_de_crash(proc)["event_id"] == "ev-hijo-a-medias"
        filas = filas_de(proyecto / "project.sqlite", EVENTOS)
        assert filas == [], (
            f"una escritura NO confirmada sobrevivio al SIGKILL: {filas}. "
            "O el commit llego a aplicarse, o la garantia de atomicidad no "
            "es la que creemos."
        )

    def test_una_transaccion_abierta_no_deja_la_mitad(self, tmp_path: Path) -> None:
        """`BEGIN IMMEDIATE` + dos filas + `SIGKILL`: ni una sobrevive.

        Este es el caso de corte de luz mas honesto: habia transaccion
        abierta, habia escrituras, y no hubo ni `COMMIT` ni `ROLLBACK`.
        Una transaccion a medias **no puede** dejar la mitad de su trabajo,
        y esto es lo que lo demuestra.
        """
        proyecto = tmp_path / "p"
        ejecutar_hasta_matar(proyecto=str(proyecto), operacion="transaccion_abierta_y_morir")
        filas = filas_de(proyecto / "project.sqlite", EVENTOS)
        assert filas == [], (
            f"la transaccion abierta dejo trabajo a medias: {filas}. "
            "Lo committed y lo no committed tienen que ser "
            "indistinguibles despues de un corte."
        )

    def test_queda_un_journal_que_dice_que_hubo_un_corte(self, tmp_path: Path) -> None:
        """El `-journal` sobrevive al corte: es la prueba, no un defecto.

        Este test existe por inspeccion. Sin el, alguien podria ver un
        `project.sqlite-journal` en `tmp_path` tras un test de crash y
        pensar que hay un defecto. No lo hay: el journal es exactamente el
        mecanismo que hace posible la garantia, y **debe** estar ahi
        cuando el proceso muere sin cerrar.

        Y no se comprueba en `commit_y_morir`, donde el commit si llego y
        SQLite pudo consolidar: ahi el journal no tiene por que estar.
        """
        proyecto = tmp_path / "p"
        ejecutar_hasta_matar(proyecto=str(proyecto), operacion="transaccion_abierta_y_morir")
        assert journal_pendiente(proyecto / "project.sqlite"), (
            "no quedo journal tras cortar una transaccion abierta. Si no lo "
            "hay, el corte no fue real: algo closed la base limpiamente."
        )


class TestElTrabajoConfirmadoSobrevive:
    """La mitad complementaria, y la que se suele olvidar.

    Un motor que «recuperase» tambien esto —revirtiendo lo ya confirmado
    por si acaso— **estaria perdiendo datos**, que es peor que perderlos a
    medias. La recuperacion no puede ser mas agresiva que el crash.
    """

    def test_lo_confirmado_no_se_revierte(self, tmp_path: Path) -> None:
        """`commit` + `SIGKILL` inmediato: la fila sigue ahi.

        El hijo confirma y muere en el acto. Si al reabrir no esta, el
        motor garantiza menos de lo que el `commit` prometia, y cualquier
        consumidor que confiera en el commit esta tomando una promesa que
        el sistema no cumple.
        """
        proyecto = tmp_path / "p"
        ejecutar_hasta_matar(proyecto=str(proyecto), operacion="commit_y_morir")
        filas = filas_de(proyecto / "project.sqlite", EVENTOS)
        assert filas == [("ev-confirmado",)], (
            f"lo ya confirmado desaparecio tras el SIGKILL: {filas}. "
            "Recuperar mas de lo que se cerro es perder datos."
        )

    def test_el_commit_y_el_crash_dan_resultados_distintos(self, tmp_path: Path) -> None:
        """Los dos lados del mismo corte, en un solo test.

        Dos bases, dos operaciones que se diferencian **solo** en si el
        `commit` llego. Si dieran el mismo resultado, uno de los dos
        caminos estaria mal y este fichero no se estaria enterando: un
        guard que prueba un caso no nota cuando el otro cambia.
        """
        con_commit = tmp_path / "con"
        sin_commit = tmp_path / "sin"
        ejecutar_hasta_matar(proyecto=str(con_commit), operacion="commit_y_morir")
        ejecutar_hasta_matar(proyecto=str(sin_commit), operacion="transaccion_abierta_y_morir")

        con = filas_de(con_commit / "project.sqlite", EVENTOS)
        sin = filas_de(sin_commit / "project.sqlite", EVENTOS)
        assert con and not sin, (
            f"commit={con} y sin-commit={sin}. Si ambos dieran lo mismo, "
            "o el commit no protege nada, o la transaccion abierta se "
            "consolida sola, y las dos son defectos."
        )
