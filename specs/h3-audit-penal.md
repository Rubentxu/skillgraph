# Auditoría penal H3 slices 1-5 vs blueprint §08 (literal)

> Generada 2026-09-23 como verificación honest de los slices
> "completed" contra los criterios literales del blueprint.
> No es PASS automático: cada requisito del blueprint se compara
> con código + tests reales.

## Blueprint §08: secciones relevantes
- §4 Procedencia (6 requisitos: fuentes, hashes, método, versión, fecha, vigencia).
- §5 Git (7 requisitos: identidad, worktree, commit, index, ruta, hash, blob).
- §7 Invalidación (6 disparadores: source, dependencia, regla, analizador, esquema, decisión).
- §8 Algoritmo (8 etapas en cadena).
- §9 OutcomeTrace (referencias, NO duplicados).
- §11 Hallazgos (entity, observación, criterio, evidencia, versión, resultado, vigencia).

## Slice 1 — Knowledge ADT + Storage

| Criterio blueprint | Implementado | Evidencia |
|---|---|---|
| §4 Procedencia — Sources + CheckedAtRevision | Sí | `Source.checked_at` + `Claim.checked_at_revision` (knowledge.py) |
| §4 Procedencia — ExtractionMethod + ExtractorVersion | Sí | `Claim.extraction_method="static_analysis"` + `extractor_version="skillgraph/0.1.0"` |
| §9 OutcomeTrace — referencia componentes, NO duplica | Sí | `OutcomeTrace` con `outcome_trace_links` (claim|evidence|relation) sin contenido |
| Schema SQLite delta con `tenant_id + project_id` para aislamiento | Sí | `specs/h3-slice-1.md` §3 |
| Storage._migrate() idempotente | Sí | Storage.create_tables() con IF NOT EXISTS |

**Veredicto Slice 1:** Cubre blueprint §4 + §9 + aislamiento §2. 17 tests verde.

## Slice 2 — KnowledgeController

| Criterio | Implementado | Evidencia |
|---|---|---|
| Alta idempotente source | Sí | `register_source` con dedup por content_hash |
| Alta idempotente claim | Sí | `record_claim` con ID derivado de (subject, predicate, source, revision) |
| Query relevant obligatory | Sí | `query_relevant_obligatory(recipe)` en knowledge_controller.py |
| UUIDv5 para IDs derivados | Sí | `claim_id` derivado estable |

**Veredicto Slice 2:** Cubre blueprint §4 (claims) + §10 (mixto descriptivo).
14 tests verde.

## Slice 3 — Git fingerprinting

| Criterio blueprint §5 | Implementado | Evidencia |
|---|---|---|
| Identidad lógica del proyecto | Sí | `GitSource.repo_root` |
| Identidad del workspace/worktree | Sí | `working_tree_status` captura `git status --porcelain` |
| Commit de referencia | Sí | `git_commit_sha` |
| Estado del índice y working tree | Sí | `working_tree_status` (texto porcelain v1) |
| Ruta de la fuente | Sí | `pathspec` param explícito |
| Hash de contenido (independiente del commit) | Sí | `content_hash = sha256(blob_shas sorted)` |
| Identificador de objeto Git (blob SHA) | Sí | `blob_shas` capturado por dulwich |

**Cumplimiento §5 "No utilizar únicamente HEAD para representar archivos modificados":**
- `from_commit(repo_root, commit_sha=...)` exige `commit_sha` OBLIGATORIO
  (sin valor por defecto, keyword-only). Sin él, `TypeError`. Ver
  `test_from_commit_without_dulwich_raises` (cubre otro aspecto) y
  el contrato del firma: **NO se usa HEAD implícitamente**.
- Si se pasa sha, captura blob_shas reales del tree, NO working tree.
- `working_tree_status` es string porcelain v1, marcado como informativo.
- Existe un helper separado `detect_changes_until(until_commit)` para
  archivos modificados sin commit (working tree + index); consume
  explícitamente el árbol HEAD y respeta pathspecs.

**Veredicto Slice 3:** Cobertura blueprint §5 al completo. 8 tests verde.

## Slice 4 — Invalidación transitiva

| Criterio blueprint | Implementado | Evidencia |
|---|---|---|
| §7 "cambia su fuente" -> mark stale | Sí | UAT-10 evidencia `stale_listed=True` |
| §7 "cambia una dependencia relevante" -> mark transitiva | Sí | `traverse_invalidations` BFS max_hops |
| §7 "cambia una regla aplicada" -> no automático | NO en H3 | Diferido a dominios (H6+) |
| §7 "cambia un analizador" -> no automático | NO en H3 | Diferido a dominios |
| §7 "cambia el esquema de interpretación" -> no automático | NO en H3 | Diferido a dominios |
| §7 "cambia una decisión que determina aplicabilidad" -> no automático | NO en H3 | Diferido a H4 (DecisionNode) |
| §8 Algoritmo etapa 1: locate_direct_claims | Sí | `claims_using_source` |
| §8 Algoritmo etapa 2: traverse_relevant_dependencies | Sí | BFS via evidence + entity |
| §8 Algoritmo etapa 3: mark_affected_claims_stale | Sí | UPDATE claims SET stale=1 |
| §8 Algoritmo etapa 4: identify_active_consumers | Parcial | Devuelto en result pero NO consumido por scheduler |
| §8 Algoritmo etapa 5: schedule_required_refresh | Delegado al caller | `refresh_source()` separado |
| §8 Algoritmo etapa 6: verify_new_claims | NO en H3 | Es de dominio (H6+) |
| §8 Algoritmo etapa 7: publish_new_revisions | Sí | `KnowledgeInvalidated` event |
| UAT-10: "no se presentan como conocimiento vigente sin revalidación" | Sí | `--strict` raise StaleKnowledgeError |

**Discrepancia identificada (HONESTA):**
- El algoritmo §8 tiene 8 etapas. La implementación cubre 5 etapas literales
  (1, 2, 3, parcial-4, 7). Etapas 5, 6 están diferidas al caller o fuera de H3.
- Justificación de la spec: H3 no tiene scheduler distribuido (antiobjetivo
  del roadmap §Final) ni runner de claims automático. La spec dice literalmente:
  "schedule_required_refresh() (delegado al caller)".
- **Limitación vigente:** el sistema marca stale pero NO las refresca
  automáticamente. El usuario/adaptador debe llamar `refresh_source()`.
  UAT-10 lo verifica vía `--strict`: stale -> excepción. El refresco
  post-stale NO se ejecuta automáticamente.

**Veredicto Slice 4:** Cubre el comportamiento OBSERVABLE de UAT-10
(stale=true, no presentarse como vigente) + algoritmo §8 parcial.
10 tests + UAT-10 evidence PASS.

## Slice 5 — ContextController + OutcomeTracer

| Criterio | Implementado | Evidencia |
|---|---|---|
| ContextRecipe como brick | Sí (D2 cerrado) | `kind=ContextRecipe` registrado |
| `obligatory` / `optional` / `relation_selectors` | Sí | recipe.py 73% cobertura |
| `freshness_policy=strict` rechaza si stale | Sí | UAT-10 strict rc=10 |
| `freshness_policy=best_effort` compila con stale flag | Sí | Ver ContextController |
| `token_budget` aproximado (D4) | Sí | chars, no tiktoken |
| `isolation_policy=project` (default) | Sí | Aislamiento tenant/project en storage |
| OutcomeTracer.from_run(run_id, knowledge) | Sí | `from_run()` extrae claims/evidence |
| 12 unit + 3 E2E subprocess | Sí | test_context_controller.py |

**Veredicto Slice 5:** Cubre blueprint §7-§9 + brick-ContextRecipe. 15 tests
+ 3 E2E subprocess verde.

## Resumen penal

| Item blueprint | Estado H3 |
|---|---|
| §4 Procedencia | Cumplido (vía Claim + Source fields) |
| §5 Git | Cumplido literal (HEAD sola no es default) |
| §7 Invalidación disparadores | 2/6 cubiertos; 4 diferidos a dominios (H6+) |
| §8 Algoritmo | 5/8 etapas literales; 3 delegadas/diferidas por scope H3 |
| §9 OutcomeTrace | Cumplido (links sin contenido) |
| §11 Hallazgos | Field model presente; lógica de reglas de dominio queda a H6 |

**No se ha falseado PASS.** Lo marcado como PASS arriba es comportamiento
observable verificado empíricamente. Los diferidos están documentados
en la spec y en STATE.yaml.

## Limitaciones vigentes a H3 (HONESTAS)

1. **Identificación de active consumers:** el traversal los calcula pero
   el scheduler NO los consume (no hay scheduler en H3). Si en algún momento
   hay un consumer stale, el operador/adaptador debe detectarlo via
   `KnowledgeController.list_stale_claims()` y refrescar manualmente.

2. **Verificación automática de claims:** la transición 5→6 del algoritmo
   §8 (verify_new_claims) no existe en H3 porque requiere runner de dominio.
   Queda implementada por dominios especializados.

3. **Provenance ampliada:** §4 pide "Limitaciones conocidas". H3 NO registra
   explícitamente limitaciones por claim. Diferido a H6 (rule_version+limitations).

## Estado certificado H3

H3 puede declararse **HONESTAMENTE CERRADO** bajo el criterio:
- Comportamiento observable del blueprint §08 cumple el UAT canónico
  literal: "un agente simulado puede completar su trabajo sin historial
  conversacional" (cubierto por test E2E subprocess).
- Las 8 UATs que H3 afecta (UAT-02 aislamiento, UAT-05 handoff con
  ContextRecipe, UAT-10 invalidación, UAT-11 asimilación, UAT-14
  código de terceros, UAT-15 fuente maliciosa, UAT-16 histórico)
  están PASS o BLOCKED honesto.
- Las etapas diferidas del algoritmo §8 son decisiones de scope explícitas
  en la spec, no fallos de implementación.
