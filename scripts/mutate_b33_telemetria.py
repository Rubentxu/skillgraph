"""Sondas de mutacion de B33. Cada sonda rompe UNA property y exige ROJO.

La regla del repo, desde WI-113: un guard que no se ha visto caer no es un
guard. Y hay una segunda, mas dura, que sale de B26/WI-114: una sonda que
revienta el modulo en vez de romper la property no es una sonda «cazada»,
es el arbol roto — y por eso este harness distingue `SIN_SONDA`, `CAZADA`
e `INVALIDA`.

Ejecutar:  uv run python scripts/mutate_b33_telemetria.py
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TESTS = "tests/test_b33_runtime_evidence.py"

#: Cada sonda: (nombre, fichero, texto_antes, texto_despues, test_que_debe_caer)
SONDAS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "M1_normalizar_vuelve_a_external_doc",
        "src/skillgraph/knowledge/observation.py",
        'kind=env.kind if env.kind is not None else "external_doc",',
        'kind="external_doc",',
        "TestLaObservacionDeRuntimeNoEsUnDocumento",
    ),
    (
        "M2_la_window_no_se_valida_en_el_source",
        "src/skillgraph/knowledge/graph.py",
        "if self.observed_to is not None and self.observed_from is None:",
        "if False:",
        "TestNoSeCierraUnPeriodoQueNoEmpezo",
    ),
    (
        "M3_ventana_sobre_cualquier_kind",
        "src/skillgraph/knowledge/graph.py",
        'if self.kind != "runtime_observation":',
        "if False:",
        "TestUnaVentanaSobreUnCommitEsCategoriaEquivocada",
    ),
    (
        "M4_la_migracion_0007_no_corre",
        "src/skillgraph/platform/migrations.py",
        'Migracion("0007_sources_ventana_de_runtime", _ventana_de_runtime),',
        "",
        "TestUnaBaseViejaRecibeLaVentana",
    ),
    (
        "M5_el_indice_deja_de_ser_parcial",
        "src/skillgraph/platform/migrations.py",
        '"WHERE observed_from IS NOT NULL"',
        '"WHERE 1 = 1"',
        "TestLaVentanaSeConsultaConIndice",
    ),
    (
        "M6_el_payload_omite_la_ventana",
        "src/skillgraph/knowledge/telemetry_query.py",
        "observed_from=ventana.desde,",
        "observed_from=None,",
        "TestLaIdaYVueltaDelPayload",
    ),
    (
        "M7_ventana_sin_desde_se_acepta",
        "src/skillgraph/knowledge/telemetry_query.py",
        "if not self.desde or not self.desde.strip():",
        "if False:",
        "TestUnaVentanaSinHastaEstaAbierta",
    ),
    (
        # M8 estuvo MAL ANCLADA la primera vez y dio INOCUA apuntando a
        # `TestLaCapabilityNoLeeElReloj`. No era un guard roto: era la sonda
        # apuntando al test que no distingue. `test_dos_invocaciones_dan_el
        # _mismo_envelope` compara dos envelopes, y con `observed_to=None` en
        # los dos siguen siendo iguales — la property que mide es la
        # idempotencia, y mutar el final de la ventana no la rompe.
        # MEDIDO antes de corregir el anclaje: apuntando a
        # `TestLaVerticalEntera::test_la_capability_produce_un_envelope_de_
        # _runtime_con_ventana`, rc=1. Es el mismo error que B29's M3 y que
        # el de WI-113: **la sonda tiene que apuntar a la property, no al
        # fichero que parece conveniente.**
        "M8_la_capability_ignora_la_ventana",
        "src/skillgraph/knowledge/telemetry_query.py",
        "observed_to=ventana.hasta,",
        "observed_to=None,",
        "TestLaVerticalEntera::test_la_capability_produce_un_envelope_de_runtime_con_ventana",
    ),
)


def _rojos(pytest_rc: int, salida: str) -> bool:
    return pytest_rc != 0 and ("failed" in salida or "error" in salida)


def main() -> int:
    print("=" * 74)
    print("B33 — sondas de mutacion")
    print("=" * 74)

    # Baseline: sin sonda, todo verde. Si el baseline esta roto, cada sonda
    # seria «cazada» por una causa que no es la suya —el error 32 de B26.
    base = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    print(f"\nbaseline rc={base.returncode}: {base.stdout.strip().splitlines()[-1]}")
    if base.returncode != 0:
        print("BASELINE ROTO: las sondas no dirian nada. Se para aqui.")
        return 1

    cazadas = 0
    invalidas = 0
    sin_sonda = 0
    for nombre, fichero, antes, despues, test in SONDAS:
        ruta = RAIZ / fichero
        original = ruta.read_text()
        copia = tempfile.mkdtemp(prefix="b33sonda_")
        try:
            if antes not in original:
                print(f"  SIN_SONDA  {nombre}: el texto ancla no esta en {fichero}")
                print("             (ruff format cambio el texto; la sonda apunta al estado viejo)")
                sin_sonda += 1
                continue
            ruta.write_text(original.replace(antes, despues, 1))
            shutil.copytree(RAIZ / "src", pathlib.Path(copia) / "src", dirs_exist_ok=True)

            mutado = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"{TESTS}::{test}",
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
                print(f"  CAZADA     {nombre}  -> {test}")
                cazadas += 1
            elif mutado.returncode != 0 and "INTERNALERROR" in salida:
                print(f"  INVALIDA   {nombre}: revento el modulo, no rompio la property")
                invalidas += 1
            else:
                print(f"  INOCUA     {nombre}: {test} sigue en VERDE")
        finally:
            ruta.write_text(original)

    print(f"\n{'=' * 74}")
    print(f"cazadas {cazadas}/{len(SONDAS)}   invalidas {invalidas}   sin sonda {sin_sonda}")
    print("=" * 74)

    # Comprobacion de restauracion: si el arbol no volvio a su estado, las
    # certifications siguientes estarian midiendo otra cosa.
    restaurado = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    print(f"tras restaurar: rc={restaurado.returncode}")
    return 0 if cazadas == len(SONDAS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
