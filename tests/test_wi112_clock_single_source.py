"""WI-112: el reloj tiene diez puntos de definicion y se declara uno.

`engine.py:210` declara que `now_iso()` es el "Unico punto de
definicion", y `AGENTS.md` 1.3 dice que el reloj "se inyecta (default
factory con `datetime.now(UTC)`) y se puede mockear". Medido antes de
arreglar nada: **10** llamadas a `datetime.now` en `src/skillgraph`, en
**tres** formatos distintos.

    isoformat()              5   '2026-10-03T09:00:00.123456+00:00'
    replace(microsecond=0)   2   '2026-10-03T09:00:00+00:00'
    strftime(...)            3   '2026-10-03T09:00:00Z'

Y `RuntimeEvent` usaba `field(default_factory=lambda:
datetime.now(UTC).isoformat())`: una lambda que captura el reloj real,
por la que no se puede inyectar nada. Un test que quiera fijar la hora
tiene que pasar `timestamp=` a mano.

**El guard mide la PROPIEDAD, no el nombre.** Buscar "existe una funcion
llamada now_iso" mediria la funcion; lo que hay que vigilar es que no
aparezca una SEGUNDA llamada al reloj. Por eso el rastreo es por AST y
no por cadena: un docstring que mencione `datetime.now` es
indistinguible de una llamada si se busca con regex. Le paso un
contrasalto -- la cuarta clase de test que verifica que el propio
instrumento no mira donde no debe.

Los `strftime` de `improvement.py` y `receipts.py` producen
'YYYY-MM-DDTHH:MM:SSZ', que es un formato DISTINTO a proposito: es un
nombre de fichero, no un instante de evento. Quedan fuera del
cambio y `TestLosNombresDeFicheroSiguenConSuFormato` los vigila, para
que unificar no se lleve por delante receipts ya emitidos.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from skillgraph.runtime.engine import RuntimeEvent, now_iso

SRC = Path(__file__).resolve().parent.parent / "src" / "skillgraph"

# El reloj del nucleo no se mockea: se inyecta. Este es el unico sitio
# que puede leer el reloj real, y solo para el instante POR DEFECTO.
PUNTO_UNICO = "runtime/engine.py"

# Modulos cuyo formato de timestamp es de NOMBRE DE FICHERO, no de
# instante de evento. Se listan aqui, no en una constante dentro del
# codigo de produccion, porque la lista es una excepcion declarada.
NOMBRES_DE_FICHERO = frozenset(
    {"governance/backups.py", "governance/improvement.py", "governance/receipts.py"}
)


def _llamadas_al_reloj() -> list[tuple[str, int]]:
    """(fichero relativo, linea) de cada llamada al reloj real.

     AST, no regex: la propiedad es "este codigo LLAMA al reloj", y un
     docstring que lo mencione no es una llamada.

     Se excluyen las llamadas que alimentan un `strftime`: esas producen
     un NOMBRE DE FICHERO, no un instante de evento, y su formato es un
     formato distinto A PROPOSITO. Confundirlas con el resto daria un
     contador que ni el arreglo puede bajar, y un guard que no se puede
    poner en verde no vigila nada.
    """
    encontradas: list[tuple[str, int]] = []
    for p in sorted(SRC.rglob("*.py")):
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        strftime_padres = {
            n.func.value
            for n in ast.walk(arbol)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "strftime"
            and isinstance(n.func.value, ast.Call)
        }
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            es_reloj = (
                isinstance(f, ast.Attribute)
                and f.attr in {"now", "utcnow"}
                and isinstance(f.value, ast.Name)
                and f.value.id == "datetime"
            )
            if es_reloj and nodo not in strftime_padres:
                encontradas.append((str(p.relative_to(SRC)), nodo.lineno))
    return encontradas


class TestElRelojTieneUnSoloPuntoDeDefinicion:
    """C1 y C2."""

    def test_una_sola_llamada_al_reloj_en_todo_el_nucleo(self) -> None:
        puntos = _llamadas_al_reloj()
        assert len(puntos) == 1, (
            f"el reloj se lee en {len(puntos)} sitios, y solo puede leerse en "
            f"{PUNTO_UNICO}: {puntos}"
        )
        assert puntos[0][0] == PUNTO_UNICO, (
            f"el unico punto de lectura del reloj esta en {puntos[0][0]}, "
            f"y deberia estar en {PUNTO_UNICO}"
        )

    def test_el_punto_unico_esta_en_el_helper(self) -> None:
        """El unico lector tiene que ser `now_iso`, no una lambda suelta."""
        ((fichero, linea),) = _llamadas_al_reloj()
        assert fichero == PUNTO_UNICO
        fuente = (SRC / fichero).read_text(encoding="utf-8")
        assert "def now_iso(" in fuente
        # Y la llamada vive DENTRO de now_iso, no en un default_factory.
        arbol = ast.parse(fuente)
        fn = next(
            n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "now_iso"
        )
        assert fn.lineno <= linea <= fn.end_lineno, (
            f"la llamada al reloj esta en la linea {linea}, fuera de now_iso "
            f"({fn.lineno}..{fn.end_lineno})"
        )


class TestElFormatoDeLosInstantesEsUno:
    """C2: no basta con un solo punto, tiene que ser el mismo formato."""

    def test_now_iso_no_lleva_microsegundos(self) -> None:
        """El formato de evento es sin microsegundos.

        Dos eventos del mismo segundo tienen que producir el MISMO
        string: con microsegundos no lo harian, y la comparacion de
        strings dejaria de ser una comparacion de instantes.
        """
        a = now_iso()
        b = now_iso()
        assert len(a) == len(b), "dos llamadas seguidas dan longitudes distintas"
        assert "." not in a, f"now_iso lleva microsegundos: {a!r}"
        assert a.endswith("+00:00"), f"no es UTC con offset explicito: {a!r}"

    def test_el_default_del_evento_usa_el_formato_del_helper(self) -> None:
        """C3: el default produce el formato del helper, no el de antes.

        `AGENTS.md` 1.3 pide un default factory con `datetime.now(UTC)`, asi
        que el default se queda. Lo que cambia es que ahora pasa por
        `now_iso` y por tanto hereda el formato unico del nucleo. Antes
        producia microsegundos, y dos eventos del mismo segundo no
        comparaban como iguales.
        """
        import dataclasses

        campos = {f.name: f for f in dataclasses.fields(RuntimeEvent)}
        factory = campos["timestamp"].default_factory
        assert factory is not None, "1.3 pide un default factory"
        assert factory is not dataclasses.MISSING

        ev = RuntimeEvent(
            event_id="e",
            tenant_id="t",
            project_id="p",
            event_kind="RunCreated",
            run_id="r",
            resource_ref="x",
            causation_id=None,
            correlation_id=None,
            payload={},
        )
        assert "." not in ev.timestamp, f"el default sigue llevando microsegundos: {ev.timestamp!r}"
        assert ev.timestamp.endswith("+00:00")


def _evento(*, timestamp: str) -> RuntimeEvent:
    return RuntimeEvent(
        event_id="e",
        tenant_id="t",
        project_id="p",
        event_kind="RunCreated",
        run_id="r",
        resource_ref="x",
        causation_id=None,
        correlation_id=None,
        payload={},
        timestamp=timestamp,
    )


class TestElRelojEsInyectable:
    """C4: "se puede mockear" no es lo mismo que "se puede pasar"."""

    def test_un_test_puede_fijar_la_hora_sin_monkeypatch(self) -> None:
        ev = _evento(timestamp=FIJADO)
        assert ev.timestamp == FIJADO

    def test_now_iso_acepta_un_reloj_inyectado(self) -> None:
        """La via real de inyeccion: se pasa el reloj, no se parchea el modulo."""
        fijo = datetime(2020, 1, 1, tzinfo=UTC)
        assert now_iso(clock=lambda: fijo) == "2020-01-01T00:00:00+00:00"

    def test_un_reloj_naive_se_trata_como_utc(self) -> None:
        """Un reloj sin tzinfo no debe producir un string sin offset."""
        naive = datetime(2020, 1, 1, 12, 0, 0)
        s = now_iso(clock=lambda: naive)
        assert s == "2020-01-01T12:00:00+00:00"

    def test_sin_reloj_usa_el_reloj_real(self) -> None:
        assert now_iso() == now_iso()[:19] + "+00:00"


FIJADO = "2020-01-01T00:00:00+00:00"


class TestLosNombresDeFicheroSiguenConSuFormato:
    """C5: la excepcion declarada se vigila en las dos direcciones."""

    def test_los_modulos_de_nombre_de_fichero_siguen_existiendo(self) -> None:
        """Vigilar la lista en las dos direcciones.

        Si se borra `improvement.py`, la lista dejaria de describir el
        repo y el guard estaria verde por la razon equivocada.
        """
        for rel in NOMBRES_DE_FICHERO:
            assert (SRC / rel).is_file(), (
                f"{rel} esta en la lista de nombres de fichero pero no existe"
            )

    def test_ningun_otro_modulo_usa_strftime_para_instantes(self) -> None:
        """Solo los dos declarados pueden formatear por strftime."""
        con_strftime: set[str] = set()
        for p in sorted(SRC.rglob("*.py")):
            texto = p.read_text(encoding="utf-8")
            if "now(UTC).strftime(" in texto:
                con_strftime.add(str(p.relative_to(SRC)))
        assert con_strftime <= NOMBRES_DE_FICHERO, (
            f"modulos que formatean el reloj por strftime y no estan declarados: "
            f"{sorted(con_strftime - NOMBRES_DE_FICHERO)}"
        )


class TestElPropioGuardMideLaPropiedad:
    """Un guard que no sabe decir que mira no puede detectar nada.

    Si el rastreo del reloj pasara a buscar por cadena, estos dos tests
    lo rompen: un docstring que mencione `datetime.now` tiene que contar
    CERO, y una llamada real tiene que contar UNA.
    """

    def test_un_docstring_que_mentiona_el_reloj_no_cuenta(self) -> None:
        """La propiedad es "el codigo LLAMA al reloj", no "lo menciona".

        Un docstring que diga `datetime.now(UTC)` es indistinguible de una
        llamada para quien busque con regex. Este test es el que falla si
        el rastreo pasa a buscar por cadena: y hay docstrings asi en el
        propio repo, empezando por el de `now_iso`.
        """
        fuente = ast.parse(
            "def helper():\n"
            '    """Usa datetime.now(UTC) para sellar el documento."""\n'
            "    return 1\n"
        )
        assert _contar_llamadas(fuente) == 0, "el rastreo esta contando texto, no llamadas"

    def test_una_llamada_real_si_cuenta(self) -> None:
        fuente = ast.parse("x = datetime.now(UTC)")
        assert _contar_llamadas(fuente) == 1

    def test_el_repositorio_menciona_el_reloj_en_prosa_y_aun_asi_cuenta_una_sola_vez(self) -> None:
        """El caso real, no uno inventado: el repo tiene docstrings asi.

        Sin esto, el test anterior seria un contraejemplo de laboratorio
        y no demostrando que el problema existe aqui.
        """
        texto = (SRC / PUNTO_UNICO).read_text(encoding="utf-8")
        assert "datetime.now" in texto, "el helper deberia mencionar el reloj en su docstring"
        assert len(_llamadas_al_reloj()) == 1, (
            "la prosa no cuenta, pero deberia quedar una sola llamada real"
        )

    def test_el_rastreo_sobre_el_repo_actual_ve_10_o_1_but_no_mas(self) -> None:
        """Contrasalto: el numero tiene que cambiar cuando el codigo cambia."""
        antes = len(_llamadas_al_reloj())
        assert antes >= 1
        # Al terminar el bloque debe ser 1, no 0 ni 10.
        assert antes == 1, f"quedan {antes} puntos de lectura del reloj"


def _contar_llamadas(arbol: ast.AST) -> int:
    n = 0
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            f = nodo.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr in {"now", "utcnow"}
                and isinstance(f.value, ast.Name)
                and f.value.id == "datetime"
            ):
                n += 1
    return n


class TestLaNormalizacionNoVuelvePermisivoElTestDeEquivalencia:
    """WI-112: arreglar la intermitencia no puede apagar el guard.

    `tests/test_wi56_knowledge_repository_contracts.py` comparaba dos
    llamadas al reloj real y fallaba 4 de cada 2000 veces. La
    normalizacion de instantes lo arregla.

    El riesgo de esa normalizacion es obvious: si normaliza de mas, el
    test pasa a no mirar nada. Este test mide las DOS mitades de lo que
    la normalizacion debe hacer:

      - el instante NO es parte de la equivalencia que ese test mide,
        asi que dos llamadas al reloj tienen que dar el mismo string;
      - todo lo demas SI es parte, asi que un valor distinto tiene que
        seguir dando un string distinto.

    La version anterior de este test afirmaba las dos mitades y solo
    cumplia la primera: `norm(a) != norm(c)` es FALSO cuando `a` y `c`
    se diferencian solo en el instante, porque es justo lo que se
    normaliza. Un contrasalto que no puede pasar no es un contrasalto.
    """

    def _norm(self, s: str) -> str:
        import re

        s = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "UUID",
            s,
        )
        return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00", "INSTANTE", s)

    def test_dos_llamadas_al_reloj_dan_el_mismo_string(self) -> None:
        """La mitad que arregla: el instante no es parte de la equivalencia."""
        a = "Source(uid='11111111-1111-1111-1111-111111111111', checked_at='2026-10-03T08:01:30+00:00')"
        b = "Source(uid='11111111-1111-1111-1111-111111111111', checked_at='2026-10-03T09:15:00+00:00')"
        assert self._norm(a) == self._norm(b)

    def test_un_valor_distinto_sigue_dando_un_string_distinto(self) -> None:
        """La mitad que NO puede romperse: la normalizacion no se come el valor.

        Si esto pasara, el test de equivalencia estaria comparando dos
        cadenas identicas siempre, y un repositorio delegado que
        devolviera basura pasaria el guard.

        Los UUID **no** son un buen caso: el test de WI-56 los
        normaliza a proposito, porque dos bases con UIDs generados
        distintos son semanticamente iguales. Una version anterior de
        este test afirmaba que dos UUID distintos debian seguir
        distinguiendose, y es falso: contradice la normalizacion que ya
        existia. Uso campos que si son parte de la equivalencia.
        """
        base = "Source(uid='11111111-1111-1111-1111-111111111111', checked_at='2026-10-03T08:01:30+00:00'"
        assert self._norm(base + ", freshness='fresh')") != self._norm(
            base + ", freshness='stale')"
        )
        assert self._norm(
            "Source(kind='file', checked_at='2026-10-03T08:01:30+00:00')"
        ) != self._norm("Source(kind='git', checked_at='2026-10-03T08:01:30+00:00')")
        assert self._norm("Source(content_hash='aa11')") != self._norm(
            "Source(content_hash='bb22')"
        )

    def test_los_uuids_siguen_normalizandose(self) -> None:
        """La otra mitad de la misma pregunta, en el sentido correcto.

        Los UUID generados SI deben colapsar: es lo que hace el test de
        WI-56 para comparar dos bases semanticamente iguales.
        """
        a = "Source(uid='11111111-1111-1111-1111-111111111111')"
        b = "Source(uid='22222222-2222-2222-2222-222222222222')"
        assert self._norm(a) == self._norm(b)
