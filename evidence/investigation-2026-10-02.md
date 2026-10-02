# Investigación retrospectiva — ciclo WI-49..WI-55 (release v0.16.9 + estrangulamiento CLI)

Fecha: 2026-10-02
Alcance: 28 commits (`v0.16.8..HEAD` en el arranque), diff `src/` de
2033+/1804- en 10 ficheros, 6 módulos CLI nuevos, release v0.16.9
(tag `600279a`, push verificado), ADR-0017/0018.

## hallazgos (clasificados)

| # | Tipo | Hallazgo | Evidencia |
|---|---|---|---|
| 1 | **Defecto confirmado (regresión runtime)** | `_open_project_storage` llegó a `support.py` **sin `@contextmanager`** (corte 2 perdió el decorador): `sg policy get/set` y los 5 `sg runs *` rompían con `TypeError` en cada invocación | `test_cli_storage_lifecycle` rojo; barrido AST de decoradores contra v0.16.9: único perdido de 91 símbolos |
| 2 | **Defecto confirmado (regresión de tests)** | 3 módulos de test con ImportError de colección (`_build_adapter`, `_open_known_project`, `_open_project_storage`, `_reconcile_summaries`, `_select_promotion_failpoint` seguían importándose desde runner) — la suite completa estaba en rojo de colección desde el corte 3 | `pytest` completo: `Interrupted: 3 errors during collection` |
| 3 | **Defecto confirmado (infra/gate)** | El hook pre-commit ejecuta `pytest -q 2>&1 | tail -30`: el exit code del pipeline es el de `tail` (0 siempre) → **el gate de tests era decorativo**. Misma trampa PIPESTATUS que documenta `.pipeline.kts` (regla v0.16.5) | `.git/hooks/pre-commit` (antes del parche); commits con suite rota pasaron "OK" |
| 4 | **Deuda (contrato sin test) → corregida** | La correspondencia parser↔dispatch NO tenía test: un typo al mover un handler degradaría a ayuda+EXIT_USAGE sin romper ningún gate (fallback silencioso de `_resolve_handler`) | `grep` de tests: 0 aserciones de resolución |
| 5 | **Deuda (contrato obsoleto) → corregida** | `test_wi52_guard_chain_contracts` fijaba el contrato ANTIGUO de bool-contador ("preservado por comparación") que WI-49 revirtió deliberadamente | 1 FAILED en la suite honesta |
| 6 | **Falsos positivos del análisis inicial (proceso)** | Dos: (a) 5 helpers de promotion y `_open_known_project` marcados "compartidos" — los usos fuera eran docstrings/comentarios; (b) mi reporte anterior dijo "full suite por hook" en los cortes: falso, el hook enmascaraba el resultado | ruff eliminó alias sin uso; contador de usos contaba comentarios |
| 7 | **Hallazgo de proceso** | Colisión de numeración: existe `tests/test_wi52_guard_chain_contracts.py` (WI-52 PREVIO al mío) — mi grep de disponibilidad no cubría nombres de ficheros de test | `git ls-files tests/ | grep wi52` |

Refutados por evidencia: pérdida de código (0 de 91 símbolos), duplicados (0 salvo `__all__` por módulo), imports muertos/vivos (ruff limpio), drift de API pública (`__all__` intacto, redes de identidad 7+5+7+5 verdes).

## causa raíz (de la cadena 1→3)

La extracción mecánica por rangos/AST **perdió un decorador** (los
decoradores no están en `FunctionDef.lineno`) y **no actualizó 3
ficheros de test** que importaban símbolos movidos. Tres capas
defensivas fallaron a la vez: (a) el hook enmascaraba el exit de
pytest tras el pipe; (b) la suite completa no se volvió a ejecutar tras
el corte 1 (mi verificación usaba subconjuntos); (c) los handlers
rotos carecían de test end-to-end directo. El hook es la capa con
arreglo de mayor palanca y se corrigió.

## corregido (mínimo, atómico)

1. `c3444a7` fix(cli): restaura `@contextmanager` (decorador + import).
2. `ff5d246` fix(tests): repara los 3 imports de símbolos movidos.
3. `229c542` fix(tests): actualiza 4 ficheros de contrato estructural
   (wi44/wi41/h9/wi52-guard) a ubicaciones y contratos post-estrangulamiento.
4. `2cbc6c9` fix(ci): hook decide sobre el exit real de pytest (log a
   mktemp, sin pipe-masking), en copia instalada y versionada.
5. `tests/test_wi57_dispatch_coverage.py`: red parser↔dispatch
   bidireccional con los dos estilos de despacho y la excepción
   FLAT-ROUTER documentada (`backup`).

## evidencia

- Suite completa **1822/1822 PASS en 81s** (primera ejecución completa
  honesta desde los cortes; 1759 → 1822 por las redes nuevas).
- 96/96 en los 4 ficheros de contrato actualizados.
- Contabilidad de nombres: 91 símbolos de v0.16.9 → 0 perdidos, 0
  duplicados.
- Barrido AST de decoradores: 1 perdido (corregido), resto intacto.
- `sg policy get` / `sg runs list` funcionales de nuevo (vía suite
  subprocess/lifecycle).

## riesgos pendientes

- La medición de cobertura por subproceso sigue invisible para
  `--cov` en-proceso (deuda de instrumentación, no bloqueante).
- Los god modules restantes (storage 1807, runcontroller 1445,
  knowledge_repository 986, ports 927, graph_expansion 862) requieren
  ADR propia cada uno.
- pipelinek versión sin gobernar (backlog bl-bl-01M3WJ3KCP000387S47TMRXK40).

## sorpresas

- El defecto #1 convivió con todos los gates en verde durante 6
  commits: la "suite completa por hook" de mis reportes anteriores era
  una sobreafirmación (el pipe la convertía en smoke decorativo).
  Corregido en el journal con constancia.
- Un mensaje de commit quedó mutilado por sustitución de comandos
  (backticks en doble comilla): reset --soft inmediato y re-commit
  limpio (local, sin push).

## siguiente

1. Operador: push del acumulado (229c542..HEAD) cuando proceda — NO
   ejecutado por regla de investigación (sin push sin autorización).
2. WI-58 (candidato): red end-to-end mínima para `sg policy`/`sg runs`
   vía subprocess (la clase que quedó sin red) o seguimiento de cortes
   en runcontroller.py (ADR propia).
3. Framework SDDK: los 2 bugs en backlog siguen upstream.
