# WI-72 — Exploración: candidatas P3 y Elección por medición

> Ciclo `p-b7740b96d79ec013/wi-72-p3-expansion-apply`. Base: `dcc81b5`
> (post-release v0.16.10). Medición reproducible con `audits/audit_debt.py`
> (misma función `cyclomatic` que usa el audit vigente).

## 1. Medición de las candidatas P3 (>80 LoC)

| LoC | cc | construcciones de decisión | Función | Path |
|----:|---:|---:|---------|------|
| 409 | 1 | 0 | `build_parser` | `cli/parser.py` |
| 92 | 7 | 6 | `cmd_expansion_apply` | `cli/commands/expansion.py` |
| 90 | 2 | 1 | `compile_handoff` | `knowledge/context_controller.py` |
| 86 | **8** | 6 | `aggregate_file_signatures` | `knowledge/knowledge_controller.py` |
| 85 | 1 | 0 | `compile_handoff_from_scopes` | `knowledge/file_handoff.py` |
| 84 | 4 | 2 | `promote_candidate` | `governance/improvement.py` |

`construcciones de decisión` cuenta nodos AST `If`, `For`, `While`, `Try`,
`IfExp` y `Match` dentro del cuerpo de la función.

## 2. Descarte por medición, no por opinión

Tres candidatas quedan **fuera** del frente, y por razones distintas:

- **`build_parser` (409 LoC)** es el mayor del repo y tiene **cc 1 y cero
  construcciones de decisión**: es una tabla declarativa de `add_argument`.
  Partirlo sería perseguir el número, no un problema. Es el ejemplo
  canónico de "LoC alto no es deuda".
- **`compile_handoff_from_scopes` (85, cc 1, 0 decisiones)** y
  **`compile_handoff` (90, cc 2, 1 decisión)** son lineales. Una función
  lineal de 90 líneas que hace una cosa se lee bien; partirla produce
  un cuenco de helpers sin nombre que solo reparte el coste de leerla.

## 3. Las dos candidatas reales

### `aggregate_file_signatures` (86, cc 8) — la de mayor cc

Aísla sources de un scope y delega la agregación. El problema real está
en el bucle de aislamiento, que mezcla dos responsabilidades: comprobar
pertenencia y clasificar el fallo (`no existe` vs `existe en otro
proyecto`). El segundo caso lanza `UnknownSourceError` sin revelar el
`source_id` (regla UAT-EVO-08).

**Riesgo**: toca una invariante de corrección (aislamiento entre
proyectos) que ya tiene contrato UAT. El refactor es posible, pero el
beneficio es cc 8 → ~4 sobre un bucle de 18 líneas.

### `cmd_expansion_apply` (92, cc 7) — elegida

El defecto no es la complejidad, es que **el flujo está ahogado en
datos**. Al medir el cuerpo aparecen **30 líneas de literales JSON**
(18 del payload de propuesta + 12 del marker `.applied`) embebidas en un
orquestador, y un hallazgo de duplicación real:

**El payload de 9 claves del proposal se construye DOS veces**, en
`cmd_expansion_propose` (líneas 197-207) y en `cmd_expansion_apply`
(líneas 273-284). Es el mismo contrato de serialización, byte a byte,
salvo por:

| | propose | apply |
|---|---|---|
| sobrescribe | siempre | solo si el fichero no existe |
| `operations` | `str(args.proposal_json)` | `str(args.proposal)` |
| `encoding` en `write_text` | **omitido** (depende del locale) | `"utf-8"` explícito |

Eso es un contrato en disco con **varios lectores** (`cmd_expansion_list`,
`cmd_expansion_show`, `_scan_proposals_dir`, `_infer_proposal_stage`) y
tests que construyen ese fichero a mano
(`tests/test_h9_cli_inproc_promo_pack.py:438`). Si uno de los dos
escritores cambia y el otro no, los payloads divergen en silencio y
ningún test lo detecta: el test solo mira el lado de `apply`.

Además hay un `plan` reasignado con **dos significados distintos**: en
`args.plan_file is not None` se enlaza el plan del fichero (valor
descartado, solo importa el efecto de `_write_plan_to_storage`) y
después se re-enlaza al plan del storage. El segundo enlace pisa el
primero sin que nada lo diga.

## 4. Por qué esta y no la otra

`aggregate_file_signatures` tiene cc 8 contra cc 7: un punto de cc. Pero
su corte partiría 18 líneas y tocaría una invariante de aislamiento ya
contrastada. `cmd_expansion_apply` ofrece, con el mismo esfuerzo y
riesgo menor:

1. **Eliminar una duplicación real** de un contrato de serialización con
   lectores externos (no solo mover código).
2. **Sacar 30 líneas de datos** de un flujo de decisión, dejándolo legible.
3. **Resolver el `plan` de doble significado**, que es un bug de
   legibilidad, no de estilo.
4. **Fijar el `encoding` explícito** en el escritor compartido. En el
   lado de `apply` es byte-idéntico; en el de `propose` elimina una
   dependencia del locale al escribir evidencia en disco. Se reporta
   como cambio deliberado, no se disimula como refactor puro.

## 5. Riesgo y red prevista

- **Oráculo diferencial**: el test reimplementa los dos payloads como
  literales y compara contra lo que los comandos escriben realmente en
  disco. Un test que fija "9 claves con estos valores" no demuestra que
  el escritor no cambió; el oráculo sí.
- **Verificación en ambos sentidos**: mutar el payload compartido (quitar
  una clave, cambiar un valor) debe romper la red.
- **Frontera observable**: exit codes y efectos en disco, ya cubierto por
  `tests/test_h4_expansion_cli_slice3.py:486` (persistencia + marker).
- **Preservación explícita**: la regla "no sobrescribir si el fichero ya
  existe" en `apply` se mantiene literal; es la que preserva la propuesta
  original cuando se re-aplica.

## 6. Veredicto

Exploración suficiente. Un workitem, un fichero, una extracción con
duplicación a eliminar. Sin cambio de contrato observable y sin ADR
previo: no hay frontera de dominio ni superficie pública que mover (los
helpers nuevos son privados al módulo, igual que los siete ya existentes).
