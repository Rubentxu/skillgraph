"""Sondas de mutacion de B34.

El gate de B34 —«las mismas query models alimentan CLI y agent handoff;
ninguna superficie reconstruye autoridad o retrieval por su cuenta»— es una
afirmacion sobre la FORMA del codigo, y las afirmaciones sobre la forma se
miden rompiendola. Eso es lo que hacen estas ocho sondas.

La regla del repo, desde WI-113: un guard que no se ha visto caer no es un
guard. Y desde B26/WI-114: una sonda que revienta el modulo en vez de
romper la property no es «cazada», es el arbol roto. El harness distingue
`SIN_SONDA`, `CAZADA`, `INOCUA` e `INVALIDA`.

Ejecutar:  uv run python scripts/mutate_b34_superficie.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TESTS = "tests/test_b34_superficie.py"

SONDAS: tuple[tuple[str, str, str, str, str], ...] = (
    # M1: la CLI vuelve a hablar con el repositorio. ES EL GATE.
    (
        "M1_la_cli_llama_al_retrieval",
        "src/skillgraph/cli/commands/knowledge.py",
        "        respuesta = _superficie(storage, tenant_id, project_id).responder(_pregunta(args, nombre))",
        "        respuesta = storage.list_claims_for_subject(\n"
        "            tenant_id=tenant_id, project_id=project_id, subject_entity_id=args.subject\n"
        "        )",
        "TestUnaSolaSuperficieParaTodas::test_la_cli_no_llama_al_retrieval",
    ),
    (
        # M2 estuvo MAL DISEÑADA dos veces, y las dos dio INOCUA.
        #
        # Version 1 y 2: hardcodar `Consulta(pregunta='conflicts')` dentro
        # de la capability. No puede caer: el guard que se le pointed cuenta
        # METODOS `_responde_*`, y hardcodar una pregunta no cambia ninguno.
        # Y el otro guard, el que si habla de la capability, mide si llama
        # al retrieval — y eso la sonda no lo cambia.
        #
        # Version 3, la honesta: que la capability TOME LA AUTORIDAD POR SU
        # CUENTA. Y con `as _r` a proposito, porque el guard solo miraba
        # `ast.Attribute` y despues `ast.Name`: en el arbol el nombre seria
        # `_r`, no `resolver`. MEDIDO antes de arreglarlo: con el guard
        # como estaba, la sonda PASABA. El guard mira ahora tambien las
        # IMPORTACIONES, y entonces el alias deja de servir —si el modulo
        # importa `resolver`, toma la autoridad por su cuenta diga luego
        # como la llame—.
        #
        # Es el error de WI-113 y de la M3 de B29 por tercera vez: **la
        # sonda tiene que medir la property, no el fichero que parece
        # conveniente.**
        "M2_la_capability_toma_la_autoridad_por_su_cuenta",
        "src/skillgraph/knowledge/knowledge_query.py",
        "        respuesta = self._superficie.responder(self._consulta_b34(request, consulta))",
        "        from skillgraph.knowledge.authority import resolver as _r\n"
        "        from skillgraph.knowledge.graph import Conflicto as _C\n"
        "        _r(_C(subject_entity_id=request.subject, predicate='p',\n"
        "             afirmaciones=()), intencion='actual_behavior')",
        "TestUnaSolaSuperficieParaTodas::test_la_capability_no_llama_al_retrieval_de_la_superficie",
    ),
    (
        "M3_impact_deja_de_ser_la_arista_inversa",
        "src/skillgraph/knowledge/superficie.py",
        "            self._knowledge.list_claims_by_object_entity(\n",
        "            self._knowledge.list_claims_for_subject(\n",
        "TestImpactEsLaAristaInversa::test_impact_no_es_lo_mismo_que_what",
    ),
    (
        "M4_what_pasa_a_resolver",
        "src/skillgraph/knowledge/superficie.py",
        "        return Respuesta(consulta=c, claims=claims)\n\n    # -- why ---",
        "        return Respuesta(consulta=c, claims=claims, resolucion=resolver(Conflicto(\n"
        '            subject_entity_id=c.subject, predicate="p", afirmaciones=claims)))\n\n    # -- why ---',
        "TestWhatNoResuelveNiSeResuelve::test_what_no_devuelve_resolucion",
    ),
    (
        "M5_conflicts_resuelve_sin_intencion",
        "src/skillgraph/knowledge/superficie.py",
        "        if intencion is None:",
        "        if False:",
        "TestConflictosSinIntencionNoResuelven::test_sin_intencion_devuelve_el_conflicto_sin_resolver",
    ),
    (
        "M6_procedencia_inventa_causa",
        "src/skillgraph/knowledge/superficie.py",
        "    source_kind: str | None",
        "    source_kind: str | None\n    causa: str | None",
        "TestWhyRespondeProcedencia::test_why_no_inventa_causa",
    ),
    (
        "M7_commit_se_acepta_en_cualquier_pregunta",
        "src/skillgraph/knowledge/superficie.py",
        '        if self.commit is not None and self.pregunta != "changed":',
        "        if False:",
        "TestLosDosRelojesNoSeTraducen::test_commit_solo_es_de_changed",
    ),
    (
        "M8_el_render_deja_de_pintar_la_entidad",
        "src/skillgraph/cli/commands/knowledge.py",
        '    entidad = getattr(claim, "object_entity_id", "")\n    if entidad:',
        '    entidad = getattr(claim, "object_entity_id", "")\n    if False:',
        "TestLaSuperficiePorLaCli::test_impact_pinta_la_entidad_no_un_vacio",
    ),
    (
        # M9 y M10 NO PODIAN EXISTIR ANTES DE LA CERTIFICACION, y esa es la
        # medida del defecto: las ocho anteriores miran la FORMA (el AST de
        # la CLI y de la capability, los metodos `_responde_*`), y el puente
        # `invoke -> responder` no lo exercise ninguna. Su property es de
        # COMPORTAMIENTO, y una property de comportamiento solo se mide
        # cambiando el comportamiento.
        #
        # M10 es la mas dura de las dos y la que mas importa: el guard por
        # AST que ya existe (`TestUnaSolaSuperficieParaTodas`) sigue en
        # VERDE con esta sonda puesta. MEDIDO, no supuesto —con M10 puesta:
        #
        #     TestUnaSolaSuperficieParaTodas  3 passed
        #
        # porque hardcodar `"what"` no cambia ningun metodo, no importa
        # `resolver` y no llama al retrieval. El guard mide que la
        # capability DELEGA; esta mide que delega EN LA PREGUNTA QUE LE
        # PIDIERON. Son dos cosas, y solo la segunda hacia el puente bueno.
        "M10_el_puente_pide_siempre_la_misma",
        "src/skillgraph/knowledge/knowledge_query.py",
        "            pregunta=pregunta(consulta),",
        '            pregunta=pregunta("what"),',
        "TestLaCapabilityEjecutaLaDelegacion::test_las_seis_se_preguntan_por_la_capability",
    ),
    (
        # M9: el puente responde, pero NO es transparente. Reconstruye el
        # payload en vez de delegar en `respuesta_a_payload`. El resultado
        # sigue siendo un `CapabilityResult` bien formado y el guard de
        # forma sigue verde; lo unico que se rompe es que la capability diga
        # exactamente lo que dice la superficie.
        "M9_el_puente_reescribe_el_payload",
        "src/skillgraph/knowledge/knowledge_query.py",
        '                "superficie": respuesta_a_payload(respuesta),',
        '                "superficie": {\n'
        '                    "consulta": {"pregunta": consulta},\n'
        '                    "claims": [c.claim_id for c in respuesta.claims],\n'
        "                },",
        "TestLaCapabilityEjecutaLaDelegacion::test_lo_que_responde_es_lo_que_responde_la_superficie",
    ),
)


def _rojos(rc: int, salida: str) -> bool:
    return rc != 0 and ("failed" in salida or "error" in salida)


def main() -> int:
    print("=" * 74)
    print("B34 — sondas de mutacion")
    print("=" * 74)

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

    cazadas = invalidas = sin_sonda = 0
    for nombre, fichero, antes, despues, test in SONDAS:
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
        [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider", "--no-cov"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    print(f"tras restaurar: rc={restaurado.returncode}")
    return 0 if cazadas == len(SONDAS) and invalidas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
