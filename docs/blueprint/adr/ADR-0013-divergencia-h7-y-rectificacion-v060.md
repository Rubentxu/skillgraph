# ADR-0013 — Divergencia del hito H7 y rectificación de alcance de v0.6.0

Fecha: 2026-09-23.
Estado: aceptada (rectificación de alcance, no cambio de diseño).

## Contexto

El roadmap (`external/blueprint-v1/plan/HITOS.md`, sección H7 "Release
candidate") define H7 con estos entregables:

- Adaptador real.
- Seguridad.
- Recuperación.
- Documentación operativa.
- Suite UAT.

Criterio de salida: "El sistema completa escenarios reales con
trazabilidad, aislamiento y recuperación".

Durante la ejecución de la iniciativa `g-skillgraph-bootstrap`, el
trabajo etiquetado como H7 fue **promoción idempotente entre bases**
(outbox + reconciliación, patrón doc 09 del blueprint), no la
certificación de producto descrita por el roadmap original. El cambio
se produjo sin ADR que lo documentara, lo que hizo que el cierre
v0.6.0 reportara "H7 cerrado" con un alcance distinto al contractual.

Auditoría independiente (2026-09-23, misma fecha) que destapó la
divergencia, con estos hechos verificables en el historial:

- `f2e72eb` — tag v0.6.0: cierre que declara H6+H7 completados.
- `92cff48` — evidencias UAT-12/UAT-13 pasan de BLOCKED a PASS
  verificando las APIs Python (`tests/test_h6_multiproposito.py`,
  `tests/test_h7_promocion.py`), no recorridos públicos.
- `src/skillgraph/governance/promotion.py` + tabla `promotion_outbox`
  en `platform/storage.py`: implementación completa a nivel de
  biblioteca, sin comandos CLI ni caller en la aplicación.
- `src/skillgraph/domain/pack_loader.py` (H6): ídem (ver informe de
  trazado adjunto, ADR-0013-anexo).

## Decisión

1. **El tag v0.6.0 y el cierre `COMPLETED` del goal se conservan como
   hechos históricos.** No se reescriben ni se mueven: certifican el
   estado real que la revisión `fbb5e1c` tenía (405 tests, 16 UAT PASS
   sobre sus rutas ensayadas).

2. **El estado corregido del roadmap es:**

   | Hito | Estado real |
   |---|---|
   | H0–H5 | Cerrados conforme al roadmap. |
   | H6 · Multipropósito | Parcial: biblioteca sin recorrido de usuario. |
   | H7 · Release candidate | **Pendiente, con alcance original intacto.** |
   | Promoción entre bases | Implementada como biblioteca; certificable en H8. |

3. **Se renumera:** el endurecimiento del H7 original se ejecutará como
   **H9 · Release candidate**. El hueco biblioteca→producto se cierra
   en **H8 · Integración y certificación pública** (comandos CLI para
   carga de packs y promoción, UAT-12/13 re-ejecutadas por la interfaz
   pública, pruebas de interrupción con failpoints en límites
   transaccionales).

4. **Las UAT-12 y UAT-13 actuales no se invalidan pero quedan
   subordinadas**: certifican las funciones Python, no el producto.
   H8 no dará por certificadas las capacidades hasta que sus UAT se
   ejecuten contra los comandos públicos.

## Motivos

- Honestidad de trazabilidad: un cambio material de alcance de un hito
  contractual exige registro; el silencio convirtió una divergencia
  legítima en un cierre mal etiquetado.
- Reutilizar trabajo real: la promoción entre bases está bien
  implementada (16 tests, patrón outbox del blueprint); tirarla o
  reetiquetarla retroactivamente como "H7" serían ambos errores.
- Permitir certificación incremental sin diluir el contrato original.

## Consecuencias

- CURRENT.md, STATE.yaml y SESSION-JOURNAL.md quedan anotados con esta
  rectificación (sin alterar el cierre histórico).
- H8 arranca con trazado de autoridad previo (anexo de este ADR) para
  no exponer públicamente una ruta paralela al núcleo.
- H9 hereda los criterios de salida del H7 original (escenario real
  instalado, adaptador real, seguridad, recuperación), sin cierre por
  métricas de cobertura.

## Revisión

Reabrir si el trazado de H8 demuestra que `pack_loader` requiere
rediseño para integrarse con el registro persistente, o si la
promoción entre bases no resulta certificable sin cambios de contrato
en `Storage`.
