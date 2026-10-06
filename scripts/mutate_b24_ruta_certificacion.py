#!/usr/bin/env python3
"""B24 — el harness de la ruta de certificacion.

Que tiene que demostrar
-----------------------
Que los guards de B24 vigilan lo que dicen vigilar, y en particular que el
recorrido se ejecuta CONTRA EL ADAPTER DE VERDAD.

Porque ese es el fallo que este bloque evita. Si el recorrido se certificara
con un doble del adapter —un `def invoke(): return AgentResult(...)`— las ocho
fronteras darian verde sin que ninguna hubiera salido a la red, y el bloque
habria repetido justo lo que B2 vino a cerrar.

Cada sonda deshace UNA PROPIEDAD y exige el test DIAGNOSTICO de esa una. La
causa de una sonda es su conjunto de tests diagnosticos, no todo lo que se
puso rojo: sondas que heredan el fallo de otra se contarian como propias y el
numero seria falso.

Las sondas
----------
  M1  el recorrido llega al cable    -> el servidor deja de REGISTRAR lo que
                                         llego. El recorrido sigue terminando
                                         bien; solo se pierde la prueba de que
                                         hubo una llamada real.
  M2  la respuesta entra por el       -> se sustituye el contenido por otro y
     dominio                             lo persistido deja de ser lo devuelto.
  M3  el estado sobrevive a cerrar    -> se lee con la misma conexion que
     la conexion                          escribio, que no demuestra memoria.
  M4  reconciliar no reejecuta       -> se deshace el camino entero hasta el
                                         guard de nodo. MEDIDO: son cinco capas.
  M5  las instrucciones existen       -> la correccion vuelve a citar un path
                                         inexistente. ESA LA CAZO EL PRIMER
                                         INTENTO, contra su propia correccion.

DOS COSAS QUE ESTE HARNESS APRENDIO midiendo, no leyendo
--------------------------------------------------------
**1. `git checkout --` NO restaura sin commit debajo, y el fallo se acumula.**
La primera version de este harness restauraba con `git checkout --`, que saca
los bytes DEL INDICE. Los tres ficheros de B24 eran untracked: restaurar era un
no-op y cada sonda se sumo sobre la anterior. Al terminar, las CINCO estaban
mutadas a la vez y la «suite verde tras restaurar» se midio sobre un arbol roto
por el propio harness. Por eso ahora el snapshot es de BYTES PROPIOS, tomado al
arrancar, y el veredicto exige que los bytes vuelvan a ser esos. Un guard que
comprueba la suite NO esta comprobando que el arbol volvio.

**2. La idempotencia de reconciliar tiene CINCO capas, y ninguna sola la rompe.**
MEDIDO, en este orden, usando el test 6 como unico criterio:
    quitar solo la guarda de terminal (`runcontroller`)      -> rc=0, 0 caidos
    quitar solo la de frontier (`run_observability_*`)       -> rc=0, 0 caidos
    quitar las dos anteriores                                 -> rc=0, 0 caidos
    + que el run no se cierre + frontier no filtre            -> rc=0, 0 caidos
Y el estado real tras una pasada, medido:
    state='COMPLETED'  current_node=None  llamadas=1

La quinta capa no es una guarda de reconciliar, es el GUARD DE NODO
(`node_execution_delegations.py`): si ya hay SUCCEEDED y el plan no declara
self-loop, devuelve veredicto y no ejecuta. Las cuatro anteriores son
cortocircuitos que evitan LLEGAR hasta ahi. Por eso M4 toca tres ficheros: no
es una sonda descuidada, es la property measured. Y sale de ahi una conclusion
sobre el producto: la idempotencia es defensa en profundidad de cinco niveles, y
el test 6 mide el efecto conjunto sin nombrar ninguno.

El harness se comprueba a si mismo
----------------------------------
Antes de mutar: cada `antes` tiene que existir EXACTAMENTE una vez, cada
`despues` CERO, y cada test diagnostico tiene que estar en la suite. Una sonda
con un nombre mal escrito se contaria como cazada con menos causa, y una sonda
con un ancla repetida deshaceria el texto equivocado sin que se note.

RIESGO DECLARADO: este harness muta `src/`. Si lo matan a mitad, el arbol queda
con codigo mutado. Por eso la restauracion es por bytes y el veredicto final no
se emite si el arbol no vuelve a su estado de arranque.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _int() -> str:
    """El Python con `skillgraph` importable.

    No es cosmetico: lanzado con el interprete del sistema, `pytest` no
    encuentra el paquete, el collect sale con `rc=4` y TODA sonda parece
    cazada — o parece invalida — sin que ninguna haya midido nada.
    """
    return str(RAIZ / ".venv" / "bin" / "python")


PY = _int()

MUTABLES = (
    RAIZ / "tests" / "test_b24_recorrido_certificacion.py",
    RAIZ / "tests" / "_proveedor_local.py",
    RAIZ / "tests" / "test_uat_real_provider.py",
    RAIZ / "src" / "skillgraph" / "runtime" / "runcontroller.py",
    RAIZ / "src" / "skillgraph" / "runtime" / "run_observability_delegations.py",
    RAIZ / "src" / "skillgraph" / "runtime" / "node_execution_delegations.py",
)

SUITES = ("tests/test_b24_recorrido_certificacion.py",)


@dataclass(frozen=True, slots=True)
class Cambio:
    fichero: str
    antes: str
    despues: str


@dataclass(frozen=True, slots=True)
class Sonda:
    nombre: str
    cambios: tuple[Cambio, ...]
    esperados: tuple[str, ...]
    porque: str


SONDAS: tuple[Sonda, ...] = (
    Sonda(
        nombre="M1_el_recorrido_llega_al_cable",
        cambios=(
            Cambio(
                fichero="tests/_proveedor_local.py",
                # El servidor deja de REGISTRAR. No se muta `estado` —eso lo
                # pisa el setup de `proveedor_local()` y era un no-op—: se
                # muta la UNICA cosa del camino que el setup no toca.
                antes="        type(self).peticiones.append((self.path, body))\n",
                despues=("        pass  # sonda B24 M1: sin registro de la llamada real\n"),
            ),
        ),
        esperados=(
            "test_2_el_handoff_llega_al_adapter_con_una_llamada_real",
            # Tambien cuenta llamadas: es el mismo registro. Declarar solo uno
            # de los dos seria contar la sonda como mas simple de lo que es.
            "test_6_reconciliar_de_nuevo_no_reejecuta_el_nodo",
        ),
        porque="el recorrido tiene que LEGAR al otro extremo, no solo terminar bien",
    ),
    Sonda(
        nombre="M2_lo_persistido_es_lo_devuelto",
        cambios=(
            Cambio(
                fichero="tests/_proveedor_local.py",
                antes='"text": json.dumps({"outcome": "ok", "result": {"local": True}})',
                despues='"text": json.dumps({"outcome": "ok", "result": {"local": False}})',
            ),
        ),
        esperados=("test_3_el_resultado_vuelve_como_agentresult_del_dominio",),
        porque="lo que se persiste tiene que ser lo que devolvio el proveedor",
    ),
    Sonda(
        nombre="M3_el_estado_sobrevive_a_la_conexion",
        cambios=(
            Cambio(
                fichero="tests/test_b24_recorrido_certificacion.py",
                antes="        otra = Storage(ruta)\n        estado, error, _ = _nodo(otra, run_id)",
                despues="        otra = storage\n        estado, error, _ = _nodo(otra, run_id)",
            ),
        ),
        esperados=("test_5_el_estado_se_puede_releer_tras_reconciliar",),
        porque="lo persistido tiene que sobrevivir a cerrar la conexion",
    ),
    Sonda(
        nombre="M4_reconciliar_no_reejecuta",
        cambios=(
            # Tres capas hasta el guard. Ver el docstring: MEDIDO que ninguna
            # sola, ni dos, rompen la propiedad.
            Cambio(
                fichero="src/skillgraph/runtime/runcontroller.py",
                antes="        if new_frontier:\n            return\n",
                despues="        if new_frontier:\n            return\n        return\n",
            ),
            Cambio(
                fichero="src/skillgraph/runtime/run_observability_delegations.py",
                antes="            if not has_self_loop(plan, current):",
                despues="            if False:",
            ),
            Cambio(
                fichero="src/skillgraph/runtime/node_execution_delegations.py",
                antes=(
                    '        if existing and existing[-1].state == "SUCCEEDED" '
                    "and not has_self_loop(plan, node_name):"
                ),
                despues="        if False:",
            ),
        ),
        esperados=("test_6_reconciliar_de_nuevo_no_reejecuta_el_nodo",),
        porque="reconciliar un run ya resuelto no puede volver a llamar al proveedor",
    ),
    Sonda(
        nombre="M5_las_instrucciones_apuntan_a_un_fichero_que_existe",
        cambios=(
            Cambio(
                fichero="tests/test_uat_real_provider.py",
                # Las instrucciones vuelven a citar el nombre sin `test_`.
                # Esta sonda CAZO la primera correccion de B24, que explicaba
                # el fallo citando el path roto: un guard que solo mira el
                # fichero de destino no mide la instruccion.
                antes="    SG_UAT_REAL_PROVIDER=1 uv run pytest tests/test_uat_real_provider.py -v",
                despues="    SG_UAT_REAL_PROVIDER=1 uv run pytest tests/uat_real_provider.py -v",
            ),
        ),
        esperados=("test_el_path_del_docstring_existe",),
        porque="una instruccion que apunta a un path inexistente ejecuta nada",
    ),
)


#: Bytes de cada mutable al arrancar. El harness restaura DESDE AQUI, no desde
#: git: ver la nota 1 del docstring.
SNAPSHOT: dict[Path, bytes] = {}


def _corre(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=RAIZ, capture_output=True, text=True, check=False, timeout=timeout
    )


def _toma_snapshot() -> None:
    for m in MUTABLES:
        SNAPSHOT[m] = m.read_bytes()


def _restaura() -> None:
    for m, datos in SNAPSHOT.items():
        if m.read_bytes() != datos:
            m.write_bytes(datos)


def _volvio() -> tuple[bool, list[str]]:
    """(el arbol volvio, que mutables no). Comprueba BYTES, no `git status`.

    `git status` no puede decir nada util aqui: un fichero untracked sale
    siempre como `??`, con o sin mutacion, asi que un guard escrito sobre el
    daria `False` siempre y no distinguiria los dos casos.
    """
    sucios = [str(m.relative_to(RAIZ)) for m, datos in SNAPSHOT.items() if m.read_bytes() != datos]
    return (not sucios, sucios)


def _diagnostico() -> list[str]:
    errores: list[str] = []
    for s in SONDAS:
        for c in s.cambios:
            texto = (RAIZ / c.fichero).read_text(encoding="utf-8")
            if texto.count(c.antes) != 1:
                errores.append(
                    f"{s.nombre}: el ancla aparece {texto.count(c.antes)} veces en "
                    f"{c.fichero} (tiene que ser exactamente 1)"
                )
            if texto.count(c.despues) != 0:
                errores.append(
                    f"{s.nombre}: su 'despues' ya aparece {texto.count(c.despues)} veces "
                    f"en {c.fichero}; el arbol no esta en su estado de partida"
                )
    proc = _corre(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "--collect-only",
            "--no-header",
            "-p",
            "no:cacheprovider",
            *SUITES,
        ]
    )
    colectados = {ln.strip() for ln in proc.stdout.splitlines() if "::" in ln}
    if proc.returncode not in (0, 5):
        errores.append(
            f"la suite no se pudo colectar (rc={proc.returncode}); el diagnostico miente"
        )
        return errores
    for s in SONDAS:
        for esperado in s.esperados:
            if not any(esperado in c for c in colectados):
                errores.append(f"{s.nombre}: el test '{esperado}' no esta en la suite")
    return errores


def _aplica(s: Sonda) -> None:
    for c in s.cambios:
        ruta = RAIZ / c.fichero
        texto = ruta.read_text(encoding="utf-8")
        assert texto.count(c.antes) == 1, f"{s.nombre}/{c.fichero}: ancla no unica"
        ruta.write_text(texto.replace(c.antes, c.despues), encoding="utf-8")


def _corre_suite() -> tuple[int, set[str], bool]:
    proc = _corre([PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *SUITES])
    caidos = {
        ln.split("::", 1)[1].split(" ")[0]
        for ln in proc.stdout.splitlines()
        if ln.startswith(("FAILED ", "ERROR ")) and "::" in ln
    }
    return proc.returncode, caidos, proc.returncode in (2, 3, 4)


def main() -> int:
    print("=" * 78)
    print("B24 — harness de la ruta de certificacion")
    print("=" * 78)

    problemas = _diagnostico()
    if problemas:
        print("ABORTA: el harness no se autocomprueba")
        for p in problemas:
            print(f"  {p}")
        return 2
    cambios = sum(len(s.cambios) for s in SONDAS)
    print(
        f"autocomprobacion: {len(SONDAS)} sondas, {cambios} cambios, anclas unicas, diagnosticos existen"
    )

    _toma_snapshot()
    rc, caidos, no_colecto = _corre_suite()
    if rc != 0 or no_colecto:
        print(f"ABORTA: la suite no esta verde antes de mutar (rc={rc})")
        for c in sorted(caidos):
            print(f"  {c}")
        return 2
    print("suite verde antes de mutar: OK\n")

    cazadas: list[str] = []
    invalidas: list[str] = []

    for s in SONDAS:
        _restaura()
        try:
            _aplica(s)
        except AssertionError as exc:
            invalidas.append(f"{s.nombre}: {exc}")
            print(f"  INVALIDA {s.nombre}: {exc}")
            continue

        rc, caidos, no_colecto = _corre_suite()
        if no_colecto:
            invalidas.append(f"{s.nombre}: la suite no termino (rc={rc}); no mide nada")
            print(f"  INVALIDA {s.nombre}: la suite no termino (rc={rc})")
            _restaura()
            continue

        diagnosticos = {e for e in s.esperados if any(e in c for c in caidos)}
        if diagnosticos == set(s.esperados):
            cazadas.append(s.nombre)
            print(f"  CAZADA  {s.nombre}")
            print(f"          {s.porque}")
        else:
            invalidas.append(
                f"{s.nombre}: no cayeron {sorted(set(s.esperados) - diagnosticos)}; "
                f"cayeron {sorted(caidos)}"
            )
            print(f"  INVALIDA {s.nombre}: no cayeron {sorted(set(s.esperados) - diagnosticos)}")
        _restaura()

    _restaura()
    rc, caidos, no_colecto = _corre_suite()
    verde = rc == 0 and not caidos and not no_colecto
    volvio, sucios = _volvio()

    print()
    print("=" * 78)
    print(f"  cazadas  {len(cazadas)}/{len(SONDAS)}")
    print(f"  invalidas {len(invalidas)}/{len(SONDAS)}")
    print(f"  suite verde tras restaurar:     {verde}")
    print(f"  arbol igual al de arranque:     {volvio}")
    if sucios:
        print(f"    NO VOLVIERON: {sucios}")
    print("=" * 78)
    for i in invalidas:
        print(f"  INVALIDA: {i}")

    return 0 if (len(cazadas) == len(SONDAS) and verde and volvio) else 1


if __name__ == "__main__":
    raise SystemExit(main())
