# archive-manifest — p-74299cf88f51dab9/wi-56-storage-decomposition

Cycle: `p-74299cf88f51dab9/wi-56-storage-decomposition`
Path: `A-lite`
Work item: `e01ff5ba-754c-4c27-8b60-a73056c9f6d3`
Closed: 2026-09-29

## Cadena de provenance

Este manifiesto está ligado al `release-receipt` de la release
v0.16.8, según exige el contrato de cierre de ciclo
(`prompts/sddk/phases/release.md`, sección Receipt And Gate Contract).

```
release-receipt  (evidence/release-v0.16.8-receipt.md)
  sha256 3ca7efbb71814cc3e449903eaea4017029a2b24127149e4c47b71177d0f1554a
      │
      │  tag v0.16.8, objeto 2afe78ea93afdae4b499e414fe0aa2ecb22aef82
      │  peel df72bcc00bd5f3666f107a29cbe2c3300269a74f
      ▼
archive-manifest  (este fichero)
```

| Artefacto | Ruta | sha256 |
|---|---|---|
| merge-receipt | `evidence/release-v0.16.8-merge-receipt.md` | `17cd2ef82818435aa8c1a568fe0b219686fb6751df616f231c74bb08590212ed` |
| release-receipt | `evidence/release-v0.16.8-receipt.md` | `3ca7efbb71814cc3e449903eaea4017029a2b24127149e4c47b71177d0f1554a` |
| inventory | `{cycle-artifacts}/inventory.json` | `160af1ef9f21defb1f0b558a0c113fc8736f29bdb373c295495a1d0ce777c0d4` |
| CI journal | `evidence/pipelinek/journal-8eda4ea.sqlite` | `8c7d8a4da9297c645c9e331cd34c3c00253bd9d3fd27cfb8e823e4c7ad51c9df` |

## Transiciones registradas en el ledger

| Secuencia | Transición | Resultado |
|---|---|---|
| 7 | `release.complete` | `succeeded` → `RELEASED` / `archive`, event `evt-bdc6d471-e495-497f-9021-7a03d689ec75`, hash `sha256:cfd8c1d5…` |
| — | `archive.complete` | cierra el ciclo (este manifiesto) |

Gates evaluados con evidencia material, no afirmados:

| Gate | Receipt | Evidencia |
|---|---|---|
| `no-pending-effects` | `gate-no-pending-effects-7895ce400e968e92-3` | `HEAD == origin/main` y peel remoto de la etiqueta idénticos, por lectura independiente con `git ls-remote` |
| `release-uat-approved` | `gate-release-uat-approved-7895ce400e968e92-2` | veredicto real de `sddk uat gate release`: `gate: skip`, ALLOWED para release type `patch` |
| `ledger-valid` | `gate-ledger-valid-f194017507ecb226-1` | `sddk ledger verify` → `event_count: 71` |
| `vault-index-current` | `gate-vault-index-current-f194017507ecb226-1` | índice del vault del proyecto sin drift |

## Verificación de la release

- Suite completa: **1754 passed** en 450.62s, con `StepStarted` reales
  en el journal (no cache hit).
- `ruff check src tests`: limpio. `ruff format --check`: 188
  archivos formateados.
- Release governance gate: 2 passed.
- `origin/main` = peel de `v0.16.8` = HEAD local = `df72bcc`.

## Lo que este ciclo entrega

Descomposición del god-module `platform/storage.py` (**2837 → 1807
LoC**, −36%) en cinco componentes reales mediante patrón strangler
(ADR-0016): `SqliteRunRepository`, `SqlitePolicyStore`,
`SqliteKnowledgeRepository`, `SqliteEventStore` y
`SqlitePromotionRepository`. Cada corte con su red de contrato escrita
antes del refactor, y cero ediciones en callers (REQ-WI56-1/I1).

## Deuda que queda viva al cerrar

1. **Realimentación infinita de la evidencia UAT**:
   `tests/uat_audit.py` graba `git rev-parse HEAD` dentro del JSON de
   evidencia, así que cada commit invalida la del anterior y vuelve a
   ensuciar el árbol. Exige cambio de contrato del formato de
   evidencia: work item propio, no un ajuste colado aquí.
2. **B1**: `sddk release plan` exige un `Cargo.toml` que este proyecto
   Python no tiene. La release sigue el camino manual documentado.
3. **B3**: el ledger del ciclo `wi-45` referencia una rama
   (`feat/wi-45-uow-coverage`) que nunca existió en `cycle.created`. El
   ledger es append-only; no se corrige.
4. **Caché de `pipelinek`**: no invalida al cambiar el código fuente. No
   se toca porque corregirlo exige editar `.pipeline.kts`, que es la
   autoridad de verificación del proyecto. Decisión del mantenedor.
5. **Ciclos aún en `RELEASE_PENDING`**: `wi-45-uow-coverage` y
   `stored-claim-evidence-boundary`, más `wi-40-test-connection-lifecycle`
   en `OPEN`/`build`. Ninguno tiene receipts de merge ni de release
   propios, porque ninguno tuvo una release publicada que los
   respaldara.
