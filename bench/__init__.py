"""SkillGraph benchmark suite.

Utilidades para medir el rendimiento de los nucleos criticos
(`ContextController.compile_handoff`, `refresh_handoff`).

NO es parte de la cobertura de tests: son herramientas de observabilidad
ejecutables desde CLI (``python -m bench.bench_context``) o desde
tests de smoke (``tests/test_bench_smoke.py``).

Conventions:
- Sin efectos colaterales fuera de ``bench/_artifacts/``.
- Mediciones con ``time.perf_counter_ns`` para precision sub-ms.
- Salida en JSON + tabla humana para facil lectura.
"""

__all__: tuple[str, ...] = ()
