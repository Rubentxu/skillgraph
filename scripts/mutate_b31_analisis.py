"""Sondas de mutacion de B31.

La regla del repo, desde WI-113: un guard que no se ha visto caer no es un
guard. Y desde B26/WI-114: una sonda que reventa el modulo en vez de romper
la property no es «cazada», es el arbol roto. El harness distingue
`SIN_SONDA`, `CAZADA`, `INOCUA` e `INVALIDA`.

Las sondas de B31 se dividen en dos familias y esa division es el bloque:

    S1..S3  la vertical     — queFive observación produce, y de verdad
    N1..N4  `ADR-0035`      — que la identidad del claim siga sosteniendose

Ejecutar:  uv run python scripts/mutate_b31_analisis.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TESTS = "tests/test_b31_analisis.py"
#: Los ficheros de la identidad. Van como LISTA y no como un string con
#: espacios: pytest recibe `sys.argv` tal cual, y un argumento unico que
#: lleva dos rutas dentro no es dos rutas. MEDIDO: el baseline decia
#: `rc=4: no tests ran` y el harness lo conto como «BASELINE ROTO».
TESTS_ID: tuple[str, ...] = (
    "tests/test_r1f_identidad_claim.py",
    "tests/test_knowledge_controller.py",
)

SONDAS: tuple[tuple[str, str, str, str, str, str], ...] = (
    # --- S1: la vertical deja de declarar los cinco ------------------------
    (
        "S1_la_vertical_declara_menos",
        "src/skillgraph/knowledge/code_analysis.py",
        '            predicate="function_count",\n            object_literal=len(defs),',
        '            predicate="file_exists",\n            object_literal=len(defs),',
        TESTS,
        "TestLasCincoObservaciones::test_el_extractor_produce_las_cinco",
    ),
    # --- S2: TODAS las observaciones declaran el mismo metodo ---------------
    #
    # Esta sonda tiene historia: **con M2 de B34**, hardcodar una pregunta no
    # cambia ningun metodo `_responde_*` y el guard no la ve. El error ahi fue
    # medir la convencion en vez de la property.
    #
    # Aqui la property es «cada observacion declara SU metodo». El fallo mas
    # tentador es poner el metodo del envelope para todas, que es justo lo
    # que hace el codigo de B26/B33 y por eso parecia la opcion correcta.
    (
        "S2_todas_declaran_el_mismo_metodo",
        "src/skillgraph/knowledge/observation.py",
        "extraction_method=obs.extraction_method or METODO_EXTERNO,",
        "extraction_method=METODO_EXTERNO,",
        TESTS,
        "TestLaProcedenciaEsVerdadera::test_cada_observacion_declara_el_suyo",
    ),
    # --- S3: el kind vuelve a ser `external_doc` ---------------------------
    #
    # El fallo que B33 ya sufrio una vez: declarar la fuente de un fichero
    # como documento externo. Aqui el kind EXISTE y no usarlo no rompe nada
    # visible —los claims se siguen escribiendo— luego el unico sitio donde
    # se ve es la procedencia que `why` imprime.
    (
        "S3_el_kind_deja_de_ser_local_file",
        "src/skillgraph/knowledge/code_analysis.py",
        "            kind=KIND_FICHERO,",
        "            kind=None,",
        TESTS,
        "TestElKindEsElQueEs::test_declara_local_file_y_no_external_doc",
    ),
    # --- N1: `make_claim_id` deja de llevar el objeto -----------------------
    #
    # ESTA es la sonda que mas importa, y su motivo se mide: con el `UNIQUE`
    # de `0008` ya escrito y `make_claim_id` sin el objeto, los claims del
    # mismo predicado salen con el MISMO `claim_id` y el segundo choca con
    # la PRIMARY KEY. El `UNIQUE` estaba arreglado y seguian perdiendose 2
    # de 7 hechos. **El fallo no se ve leyendo el `UNIQUE`**: se ve contando
    # filas.
    (
        "N1_el_id_no_depende_del_objeto",
        "src/skillgraph/knowledge/knowledge_controller.py",
        '        f"{subject_entity_id}|{predicate}|{_forma_del_objeto(object_literal, object_entity)}"\n'
        '        f"|{source_id}|{checked_at_revision}"',
        '        f"{subject_entity_id}|{predicate}|{source_id}|{checked_at_revision}"',
        "tests/test_knowledge_controller.py",
        "test_record_claim_distinto_objeto_es_otro_claim",
    ),
    # --- N2: la migracion escribe el UNIQUE viejo ---------------------------
    #
    # N2 estuvo **INOCUA** la primera vez, apuntando al `UNIQUE` de
    # `schema.py`, y el motivo importa mas que el arreglo: cambiarlo a pelo
    # no rompe NADA, porque `0008` reconstruye la tabla de una base nueva
    # igual que de una vieja. Ese `UNIQUE` es una redundancia que la
    # migracion siempre repara — y una sonda que mide una propiedad que no
    # se puede romper por ahi es «vigilar una verdad imposible de violar»,
    # la forma que B1 calibra.
    #
    # La version honesta ataca el DDL de la MIGRACION, que es el que decide
    # sobre las bases viejas, y las viejas son justamente las que
    # `schema.py` no alcanza.
    (
        "N2_la_migracion_escribe_el_unique_viejo",
        "src/skillgraph/platform/migrations.py",
        '        "            object_literal_json, object_entity_id, source_id,\\n"\n'
        '        "            checked_at_revision)"',
        '        "            source_id, checked_at_revision)"',
        TESTS,
        "TestLaMigracionEsIdempotente::test_una_base_con_el_universe_viejo_se_reconstruye",
    ),
    # --- N3: `observation` deja de pasar el objeto -------------------------
    #
    # La segunda mitad del mismo defecto que mide N1, y por eso estan
    # separadas: N1 rompe el generador y N3 rompe el que lo llama. Si
    # ambas ocurriesen a la vez, un solo test no podria decir cual de los
    # dos dejo de funcionar —el error de los contrasaltos contados dos
    # veces, de B0.
    (
        "N3_observation_no_pasa_el_objeto",
        "src/skillgraph/knowledge/observation.py",
        "            object_literal=obs.object_literal,\n"
        "            object_entity=obs.object_entity,\n"
        "        ),",
        "        ),",
        TESTS,
        "TestNoSePierdeNingunHecho::test_todas_las_observaciones_llegan_a_la_tabla",
    ),
    # --- N4: la migracion pierde filas al copiar ---------------------------
    #
    # N4 estuvo **INOCUA** la primera vez, y el motivo importa mas que el
    # arreglo. La sonda apagaba el `if` del `COUNT` —`if False:`— y no pasaba
    # nada: en el camino feliz la copia conserva todas las filas, luego ese
    # `if` no se activa nunca. Un guard que solo se dispara en un caso que
    # nadie construye no esta midiendo: esta decorado.
    #
    # La version honesta rompe la **COPIA**, que es lo que haria de verdad una
    # migracion mal escrita, y entonces la comparacion del `COUNT` —que
    # `0005` escribio como «peor que no migrar»— se enciende sola y la
    # migracion levanta. Y no se reimplementa la migracion en el test para
    # provocarlo: eso seria una segunda copia de la regla, que diverge el dia
    # que una se actualice y la otra no. La sonda muta el codigo de verdad.
    (
        "N4_la_copia_descarta_una_fila",
        "src/skillgraph/platform/migrations.py",
        'SELECT {columnas} FROM claims_pre_0008")',
        'SELECT {columnas} FROM claims_pre_0008 LIMIT 1")',
        TESTS,
        "TestLaMigracionEsIdempotente::test_una_migracion_que_pierde_filas_falla_en_vez_de_seguir",
    ),
)


def _rojos(rc: int, salida: str) -> bool:
    return rc != 0 and ("failed" in salida or "error" in salida)


def main() -> int:
    print("=" * 74)
    print("B31 — sondas de mutacion")
    print("=" * 74)

    base = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            TESTS,
            *TESTS_ID,
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    print(f"\nbaseline rc={base.returncode}: {base.stdout.strip().splitlines()[-1]}")
    if base.returncode != 0:
        print("BASELINE ROTO: las sondas no dirian nada. Se para aqui.")
        return 1

    cazadas = invalidas = sin_sonda = 0
    for nombre, fichero, antes, despues, tests, test in SONDAS:
        ruta = RAIZ / fichero
        original = ruta.read_text()
        try:
            if antes not in original:
                print(f"  SIN_SONDA  {nombre}: el ancla no esta en {fichero}")
                print("             (ruff format cambio el texto; apunta al estado viejo)")
                sin_sonda += 1
                continue
            ruta.write_text(original.replace(antes, despues, 1))
            mutado = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"{tests}::{test}",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--no-cov",
                ],
                cwd=RAIZ,
                capture_output=True,
                text=True,
            )
            salida = mutado.stdout + mutado.stderr
            if _rojos(mutado.returncode, salida):
                print(f"  CAZADA     {nombre}")
                cazadas += 1
            elif "INTERNALERROR" in salida or "SyntaxError" in salida:
                print(f"  INVALIDA   {nombre}: revento el modulo, no rompio la property")
                invalidas += 1
            else:
                print(f"  INOCUA     {nombre}")
        finally:
            ruta.write_text(original)

    print(f"\n{'=' * 74}")
    print(f"cazadas {cazadas}/{len(SONDAS)}   invalidas {invalidas}   sin sonda {sin_sonda}")
    print("=" * 74)

    restaurado = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            TESTS,
            *TESTS_ID,
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
        ],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    print(f"tras restaurar: rc={restaurado.returncode}")
    return 0 if cazadas == len(SONDAS) and invalidas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
