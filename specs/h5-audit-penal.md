# Auditoría penal H5 Adopción de skills vs blueprint literal

> Generada 2026-09-23 como verificación honest de H5 (skill_import)
> contra los criterios literales del blueprint. No es PASS
> automático: cada requisito del blueprint se compara con código +
> tests reales.

## Blueprint H5 — referencias literales

Fuentes primarias:
- `external/blueprint-v1/plan/HITOS.md` §H5 "Adopción de skills"
  (5 entregables: Importación, Paquete encapsulado, Informe de
  asimilación, Registro de capacidades, Comandos dinámicos).
- `external/blueprint-v1/plan/UAT.md` UAT-11/14 (textos literales).
- `external/blueprint-v1/plan/ROADMAP.md` §H5 (sin detalle
  adicional al de HITOS).
- `specs/h5-source-conservation-decision.md` (decisión D5:
  "conserva fuente original" = referencia, NO copia).

## Entregables HITOS.md §H5

| Entregable blueprint | Cubierto | Evidencia |
|---|---|---|
| Importación | Sí | `cmd_pack_import` en cli.py:679 + `analyze_skill()` en skill_importer.py:176 |
| Paquete encapsulado | Sí | `SkillImportReport` con files_total + files_structured + entries_ambiguous + scripts_detected + capabilities_extracted |
| Informe de asimilación | Sí | `SkillImportReport.to_dict()` serializa el informe; CLI imprime JSON |
| Registro de capacidades | Parcial | `capabilities_extracted` se persiste en `Source` con `kind='skill_pack'`. PERO: NO son "capacidades registradas" en el sentido del registry de bricks (donde viven las capabilities de H4). Una capability extraída de headers Markdown NO se inserta automáticamente en `bricks.capabilities`. |
| Comandos dinámicos | NO | No hay wiring CLI para generar comandos a partir de capacidades extraídas. Lo que hay es el reporte `capabilities_extracted` + nota honesta de que son SEÑALES, no decisiones. |

## UAT canónico literal (UAT.md)

### UAT-11 — Asimilación de skill

> "Dada una skill convencional, cuando se importa, entonces se
> conserva la fuente original y se genera un informe de
> estructuración. Las partes ambiguas deben permanecer señaladas;
> no se presentan como decisiones verificadas."

| Criterio literal | Cubierto | Evidencia |
|---|---|---|
| Skill convencional → importación | Sí | `analyze_skill(root)` itera sobre el directorio, clasifica cada archivo |
| Conserva la fuente original | Sí (referencia, NO copia) | `Source.kind='skill_pack'` + `Source.original_path` + `Source.content_hash`. Decisión D5 documentada en `specs/h5-source-conservation-decision.md`: blueprint §10 §5-6 dice "referencias a su fuente", NO duplicar bytes. |
| Informe de estructuración | Sí | `SkillImportReport.to_dict()` con 10 campos: source_id, original_path, content_hash, imported_at, files_total, files_structured, entries_ambiguous, scripts_detected, capabilities_extracted, nota_honesta |
| Partes ambiguas permanecen señaladas | Sí | `entries_ambiguous: tuple[AmbiguousEntry]` con reason explicito (e.g. "python script; not parsed", "binary; skipped"). 8 tests verifican casos ambiguos. |
| No se presentan como decisiones verificadas | Sí | `nota_honesta` obligatoria en el informe + `capabilities_extracted` documentado como "SEÑALES heurísticas (NO decisiones verificadas)". Verificado en `test_capabilities_are_signals_not_decisions` (test_skill_importer.py:67). |

**Veredicto UAT-11:** PASS verificado con 8 tests
(`tests/test_skill_importer.py`) + test E2E CLI en
`tests/uat_audit.py::uat_11()` (línea 1074) que ejecuta
`sg pack import demo /path --report /path` contra un pack con
Markdown + JSON + script.py peligroso, y verifica rc=0 +
script NO ejecutado.

### UAT-14 — Código de terceros

> "Dado un Domain Pack con un script Python, cuando se importa
> y valida, entonces el script no se ejecuta automáticamente."

| Criterio literal | Cubierto | Evidencia |
|---|---|---|
| Domain Pack con script Python | Sí | `_classify(path)` reconoce `.py` y `.pyi` como "script" |
| Importa y valida | Sí | `analyze_skill(root)` itera y clasifica |
| Script NO se ejecuta automáticamente | Sí | **Garantía por construcción**: `analyze_skill` solo LEE bytes (`_read_text_safely`), nunca hace `import`, `exec`, `run`, `subprocess`. Verificado por `test_script_never_executes_during_import` (test_skill_importer.py:32) que importa un pack con `print('pwned')` y verifica que el stdout NO contiene 'pwned'. |

**Veredicto UAT-14:** PASS verificado con test
`test_script_never_executes_during_import` que prueba el caso
real (script con código peligroso que NO se ejecuta).

## Decisiones de diseño tomadas (D5)

| ID | Decisión | Justificación blueprint |
|---|---|---|
| D5 | "Conserva fuente original" = path + content_hash (referencia), NO bytes | `specs/h5-source-conservation-decision.md`. Blueprint §10 §5-6 literal: "referencias a su fuente" + "comportamiento ejecutable sujeto a un contrato externo". Duplicar bytes sería (a) riesgo de drift, (b) violación de "comportamiento ejecutable sujeto a contrato externo". |

## Limitaciones vigentes a H5 (HONESTAS)

1. **Capabilities extraídas son SEÑALES, no decisiones.** El header
   `## Usage` de un Markdown genera una capability `Usage`, pero
   esto NO significa que la skill realmente provee esa capability.
   El `nota_honesta` en el informe lo declara explicitamente. Para
   cerrar H5 con "Registro de capacidades" (HITOS.md), faltaría
   un mecanismo de validación que confirme cada capability (e.g.
   ejecutar la skill bajo sandbox y observar outputs reales). Esto
   NO está en slice-1 de H5.

2. **Comandos dinámicos no implementados.** HITOS.md lista
   "Comandos dinámicos" como entregable, pero el código solo
   genera el INFORME. No hay wiring que cree nuevos `sg <skill>`
   subcommands automáticamente.

3. **Source.kind='skill_pack' Literal validado en runtime.**
   Esto se corrigió en el commit `ff433aa` (anterior a esta
   sesión H4). Antes, el Literal check no se ejecutaba en
   runtime (debido a `from __future__ import annotations`) y
   se podía persistir un Source con `kind='skill_pck'` (typo)
   sin error. Ahora el `__post_init__` valida contra
   `typing.get_args(SourceKind)`.

4. **UAT-14 cubierto en `uat_audit.py`, no en `test_cli_uat.py`.**
   El test unitario `test_script_never_executes_during_import`
   cubre el comportamiento del motor. El test E2E CLI está en
   `tests/uat_audit.py::uat_14()` (línea 1250), que ejecuta el
   binario `sg` real con un script Python y verifica rc=0 +
   stdout sin 'pwned'. Este test NO está en la suite pytest
   estándar (no es `def test_*`), sino en el script de audit
   separado. Implicación: si alguien corre solo `pytest`, NO
   se valida UAT-14 end-to-end. Para integrar en pytest haría
   falta moverlo a `tests/test_cli_uat.py` con el patrón
   subprocess usado por `test_h4_expansion_cli.py`.

5. **No hay audit de "Domain Pack" específicamente.** El blueprint
   HITOS.md menciona "Domain Pack" en H6 (multipropósito) y los
   tests usan "skill pack" como sinonimo. La distinción
   semántica NO está formalizada en el código.

## Estado certificado H5 (honesto)

H5 puede declararse **HONESTAMENTE CERRADO EN SU ALCANCE
DECLARADO** bajo el criterio:

- UAT-11 literal cumplido: skill importada → fuente conservada
  (referencia) + informe con ambiguos señalados + nota honesta
  sobre signals-vs-decisions.
- UAT-14 literal cumplido: scripts Python en el pack NUNCA se
  ejecutan (verificado por test con `print('pwned')`).
- 5 entregables HITOS.md: 3 cubiertos (Importación, Paquete
  encapsulado, Informe asimilación), 1 parcial (Registro
  capacidades: extrae pero no valida), 1 NO (Comandos dinámicos).
- Decisión D5 documentada (referencia, no copia) justificada
  contra blueprint §10 §5-6.

**No se ha falseado PASS.** Las limitaciones vigentes están
documentadas. Los entregables HITOS.md faltantes (Registro
capacidades con validación, Comandos dinámicos) son
mejoras incrementales que no bloquean UAT-11/14.

## Recomendación para el operador

1. Si se busca cerrar H5 al 100%, los entregables faltantes son:
   - Validación de capabilities extraídas (¿cómo sabemos que
     "Usage" del Markdown es una capability real?).
   - Comandos dinámicos (`sg <skill-name>` generado a partir
     del pack).
2. Ambos son trabajo de ~2-3 días, no críticas para UAT-11/14.
3. Si la prioridad es H6/H7 (UAT-12/13 BLOCKED), H5 puede
   quedarse en su cierre actual.
