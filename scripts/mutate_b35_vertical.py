"""Sondas de mutacion de B35 — de la capability al store.

La regla del repo, desde WI-113: un guard que no se ha visto caer no es un
guard. Y desde B26/WI-114: una sonda que reventa el modulo en vez de romper la
propiedad no es «cazada», es el arbol roto. El harness distingue `SIN_SONDA`,
`CAZADA`, `INOCUA` e `INVALIDA`.

Las sondas de B35 se dividen en TRES familias, y esa division es el bloque:

    V1..V3  el CONTRATO    — que la ida y la vuelta exista y sea identidad
    D1..D3  el DECISOR     — que `conflicto` signifique lo que se decidio
    P1..P2  la PUERTA      — que un operador llegue, y sin falsos avisos

Ejecutar:  uv run python scripts/mutate_b35_vertical.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent

#: La clase de cada sonda es (nombre, fichero, PARES, objetivo), donde PARES
#: es una tupla de (antes, despues). Son tuplas y no un solo par porque
#: MEDIDO que hay sondas que NO se pueden expresar en un solo cambio: la que
#: devuelve la consulta previa a la tupla de `0008` tiene que cambiar el SQL
#: Y la lista de parametros, y con un solo par el SQL queda con mas `?` que
#: valores y la sonda revienta el modulo en vez de medir la propiedad.
#: Que una sonda reventara el arbol no es «cazada»: es ruido. El objetivo es UN `fichero::test`, no una lista: MEDIDO en el
#: harness de B31 que un argumento con espacios no son dos rutas, y aqui el
#: error equivalente seria apuntar la sonda a un fichero donde el test no vive
#: y que pytest lo corra en silencio sin el.
SONDAS: tuple[tuple[str, str, tuple[tuple[str, str], ...], str], ...] = (
    # --- V1: el inverso deja de reconstruir el objeto entero ---------------
    #
    # MEDIDO: sin esto `envelope_de_payload` devolvia un envelope sin
    # `object_entity`. No sale por ningun camino de `ingerir` desde que
    # `imports_module` lleva un LITERAL, luego sin esta sonda el defecto
    # seria invisible —que es lo que paso con la copia de B31 en los tests.
    (
        "V1_el_inverso_no_reconstruye_la_entidad",
        "src/skillgraph/knowledge/observation.py",
        "        object_entity=None if entidad is None else entity_ref(str(entidad)),",
        "        object_entity=None,",
        "tests/test_b35_vertical.py::TestElContratoTieneLasDosDirecciones"
        "::test_la_ida_y_la_vuelta_es_identidad",
    ),
    # --- V2: la AUSENCIA se confunde con un `None` --------------------------
    #
    # `or` en vez de `.get(k, POR_DEFECTO)`: `None` significa «metodo externo»
    # pero no es la misma cadena, luego la ida y la vuelta dejaba de ser
    # identidad sin que nada fallara en el camino feliz.
    (
        "V2_la_ausencia_se_confunde_con_un_None",
        "src/skillgraph/knowledge/observation.py",
        '    metodo = dato.get("extraction_method", METODO_EXTERNO)',
        '    metodo = dato.get("extraction_method") or METODO_EXTERNO',
        "tests/test_b35_vertical.py::TestElContratoTieneLasDosDirecciones"
        "::test_una_clave_ausente_no_es_un_None",
    ),
    # --- V3: la `version` del producer se pierde ----------------------------
    #
    # `CapabilitySpec` tiene TRES campos y el `UNIQUE` de
    # `CapabilityRegistry` es `(type_name, version)`.
    (
        "V3_el_producer_pierde_la_version",
        "src/skillgraph/knowledge/observation.py",
        '            "version": envelope.producer.version,',
        '            "version": "v1",',
        "tests/test_b35_vertical.py::TestElContratoTieneLasDosDirecciones"
        "::test_el_producer_no_pierde_la_version",
    ),
    # --- D1: la fila previa vuelve a la tupla ANTERIOR a `0008` ------------
    #
    # **ESTA SONDA ESTUVO INOCUA LA PRIMERA VEZ, Y EL MOTIVO ES EL INTERESANTE.**
    # Apuntaba a la COMPARACION (`previo_valor != intento_valor`) y el arbol
    # seguia en verde. MEDIDO, y el motivo importa mas que el arreglo: con la
    # consulta ya correcta —que busca por `claim_id` y por la tupla natural
    # COMPLETA, que desde `0008` incluye el objeto— `previo` para
    # `imports_module='sys'` es `None` o es la fila de `'sys'`, luego
    # `previo_valor != intento_valor` da `False` IGUAL que la version
    # correcta. Se estaba midiendo un cambio que ya no cambia nada.
    #
    # La version honesta ataca la CAUSA, que era la consulta: es lo que
    # hacia que `fetchone()` devolviera la fila de `'os'` y el aviso saliera
    # falso. Y esa es exactamente la forma que tenia el defecto.
    (
        "D1_la_fila_previa_vuelve_a_la_tupla_vieja",
        "src/skillgraph/platform/knowledge_claims.py",
        (
            (
                "                  AND (\n"
                "                        claim_id = ?\n"
                "                     OR (subject_entity_id = ? AND predicate = ?\n"
                "                         AND object_literal_json = ? AND object_entity_id = ?\n"
                "                         AND source_id = ? AND checked_at_revision = ?)\n"
                "                  )\n"
                "                ORDER BY (claim_id = ?) DESC",
                "                  AND subject_entity_id = ? AND predicate = ?\n"
                "                  AND source_id = ? AND checked_at_revision = ?",
            ),
            (
                "                    claim.claim_id,\n"
                "                    claim.subject_entity_id,\n"
                "                    claim.predicate,\n"
                "                    obj_json,\n"
                "                    ref,\n"
                "                    claim.source_id,\n"
                "                    claim.checked_at_revision,\n"
                "                    claim.claim_id,",
                "                    claim.subject_entity_id,\n"
                "                    claim.predicate,\n"
                "                    claim.source_id,\n"
                "                    claim.checked_at_revision,",
            ),
        ),
        None,
        "tests/test_b35_vertical.py::TestElAvisoHablaDelClaimQueSeReEscribe"
        "::test_el_valor_previo_es_el_suyo_y_no_el_de_otro",
    ),
    # --- D2: se queda solo con UNA de las dos condiciones -------------------
    #
    # MEDIDO: `solo not insertado` hace que el estado 2 —reingerir lo MISMO—
    # de conflicto=True, y con eso B26 deja de ser idempotente.
    (
        "D2_se_queda_solo_con_una_condicion",
        "src/skillgraph/platform/claim_conflicts.py",
        "        conflicto=(not insertado) and previo_valor != intento_valor,",
        "        conflicto=not insertado,",
        "tests/test_b27_conflictos.py::TestElOverwriteAvisa::test_escribir_lo_mismo_no_avisa",
    ),
    # --- D3: la fila previa deja de distinguir por `claim_id` --------------
    #
    # MEDIDO: sin el `OR claim_id = ?`, la colision de clave primaria —la
    # unica que significa «no se escribio lo que dijiste»— no encuentra fila
    # previa y el aviso se pierde. La senal queda MUERTA, que es peor que
    # una falsa: la falsa molesta y la muerta no avisa.
    (
        "D3_la_fila_previa_no_distingue_por_claim_id",
        "src/skillgraph/platform/knowledge_claims.py",
        "                        claim_id = ?",
        "                        claim_id = ''",
        "tests/test_b27_conflictos.py::TestElOverwriteAvisa::test_escribir_lo_distinto_si_avisa",
    ),
    # --- P1: la CLI deja de resolver por nombre ----------------------------
    #
    # **ESTA ESTUVO INOCUA LA PRIMERA VEZ, Y EL MOTIVO DICE ALGO DE B34.**
    # Apuntaba a cambiar `registro.resolve(CODE_ANALYSIS)` por la clase
    # directa, y el arbol seguia en verde: las dos cosas producen la MISMA
    # capability, luego la sonda medía un cambio que no es un cambio.
    #
    # La version honesta ataca la DEPENDENCIA de verdad: que el ensamblado
    # deje de declarar `sg.code.analysis`. Entonces la CLI, que no sabe QUE
    # capability hay sino que pide UNA por nombre, falla — y con ella se
    # ve que el registro es lo que la sostiene, y no una clase importada.
    (
        "P1_el_ensamblado_no_declara_la_capability",
        "src/skillgraph/knowledge/assembly.py",
        "            CodeAnalysisCapability(source_id=source_id, revision=revision),",
        "            KnowledgeQueryCapability(knowledge, tenant_id=tenant_id, project_id=project_id),",
        "tests/test_b35_vertical.py::TestLaPuertaExiste::test_la_vertical_entera_por_la_cli",
    ),
    # --- P2: el ensamblado promete lo que no puede -------------------------
    #
    # MEDIDO: `LectorTelemetria` es un `Protocol` con CERO implementaciones en
    # `src/`. Anadir `sg.telemetry.query` seria montar una capability con un
    # lector de carton, que daria respuestas sobre un runtime que no ha visto
    # nunca.
    (
        "P2_el_ensamblado_promete_lo_que_no_puede",
        "src/skillgraph/knowledge/assembly.py",
        "CAPACIDADES_ENSAMBLADAS: Final[tuple[str, ...]] = (CODE_ANALYSIS, KNOWLEDGE_QUERY)",
        "CAPACIDADES_ENSAMBLADAS: Final[tuple[str, ...]] = (\n"
        '    CODE_ANALYSIS,\n    KNOWLEDGE_QUERY,\n    "sg.telemetry.query",\n)',
        "tests/test_b35_vertical.py::TestElDespliegueExiste"
        "::test_no_ensambla_lo_que_no_tiene_lector",
    ),
)

BASELINE: tuple[str, ...] = (
    "tests/test_b35_vertical.py",
    "tests/test_b27_conflictos.py",
    "tests/test_b29_vigencia.py",
)


def _rojos(rc: int, salida: str) -> bool:
    return rc != 0 and ("failed" in salida or "error" in salida)


def _pytest(*objetivos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *objetivos, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )


def main() -> int:
    print("=" * 74)
    print("B35 — sondas de mutacion")
    print("=" * 74)

    base = _pytest(*BASELINE)
    print(f"\nbaseline rc={base.returncode}: {base.stdout.strip().splitlines()[-1]}")
    if base.returncode != 0:
        print("BASELINE ROTO: las sondas no dirian nada. Se para aqui.")
        return 1

    cazadas = invalidas = sin_sonda = 0
    print()
    for nombre, fichero, antes, despues, objetivo in SONDAS:
        ruta = RAIZ / fichero
        original = ruta.read_text(encoding="utf-8")
        # La sonda escribe `antes`/`despues` como dos textos, o `antes` como
        # una tupla de pares y `despues` como `None`. MEDIDO que hay sondas que
        # NO caben en un cambio solo —devolver una consulta a la tupla de
        # `0008` exige tocar el SQL y sus parametros—, y que forzar a que
        # quepan midiendo un cambio que no es el defecto.
        lista = antes if isinstance(antes, tuple) else ((antes, despues),)
        try:
            faltan = [a for a, _ in lista if a not in original]
            if faltan:
                print(f"  SIN_SONDA  {nombre}: el ancla no esta en {fichero}")
                print("             (ruff format cambio el texto; apunta al estado viejo)")
                sin_sonda += 1
                continue
            mutado = original
            for a, d in lista:
                mutado = mutado.replace(a, d, 1)
            ruta.write_text(mutado, encoding="utf-8")
            mutado = _pytest(objetivo)
            salida = mutado.stdout + mutado.stderr
            if _rojos(mutado.returncode, salida):
                print(f"  CAZADA     {nombre}")
                cazadas += 1
            elif "INTERNALERROR" in salida or "SyntaxError" in salida:
                print(f"  INVALIDA   {nombre}: la sonda revienta el modulo")
                invalidas += 1
            else:
                print(f"  INOCUA     {nombre}: el arbol sigue en verde")
        finally:
            ruta.write_text(original, encoding="utf-8")

    print()
    print("=" * 74)
    print(f"cazadas {cazadas}/{len(SONDAS)}   invalidas {invalidas}   sin sonda {sin_sonda}")
    print("=" * 74)

    tras = _pytest(*BASELINE)
    print(f"tras restaurar: rc={tras.returncode}")
    return 0 if cazadas == len(SONDAS) and invalidas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
