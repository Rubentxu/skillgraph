# STATE.yaml sync gap — Auditoría 2026-09-25 09:43

## Hallazgo

`STATE.yaml` (línea 649, `release.tag`) dice `v0.6.0` y la lista
`releases:` solo contiene hasta `v0.6.0` (líneas 654-672). La
realidad verificable en `git tag` y `CHANGELOG.md`:

| Tag | Fecha | Tag-SHA (`git rev-list -n 1`) | SHA en STATE | Estado |
| --- | --- | --- | --- | --- |
| v0.3.0 | 2026-09-23 | `f1c9f2ef` | `3f3c2352` (docs) | divergente |
| v0.4.0 | 2026-09-23 | `3b26ada0` | `1f1ec2f2` (docs) | divergente |
| v0.4.1 | 2026-09-23 | `92cb092a` | `2262ac47` (docs) | divergente |
| v0.5.0 | 2026-09-23 | `8bab8abb` | `8bab8abb` (docs) | OK (coincide) |
| v0.6.0 | 2026-09-23 | `fbb5e1c4` | `92cff480` (feat, no tag) | divergente |
| v0.7.0 | 2026-09-24 | `2ae1bca5` | (no listado) | **falta** |
| v0.7.1 | 2026-09-24 | `8b63db6a` | (no listado) | **falta** |
| v0.7.2 | 2026-09-24 | `6c8a457a` | (no listado) | **falta** |
| v0.7.3 | 2026-09-24 | `6a536acf` | (no listado) | **falta** |
| v0.8.0 | 2026-09-24 | `fe3b343f` | (no listado) | **falta** |
| v0.8.1 | 2026-09-24 | `9bc5f61a` | (no listado) | **falta** |
| v0.9.0 | 2026-09-24 | `a4d749e9` | (no listado) | **falta** |
| v0.10.0 | 2026-09-24 | `c6963f07` | (no listado) | **falta** |
| v0.11.0 | 2026-09-24 | `6ad5789c` | (no listado) | **falta** |
| v0.12.0 | 2026-09-24 | `9d9ae093` | (no listado) | **falta** |
| v0.13.0 | 2026-09-24 | `72651ee8` | (no listado) | **falta** |
| **v0.14.0** | **2026-09-24** | **241ccc9f** | **(no listado)** | **falta** |

**Gaps detectados** (3 categorias):

1. **9 releases faltantes** (v0.7.0..v0.14.0).
2. **5 SHAs divergentes** (v0.3.0/v0.4.0/v0.4.1/v0.5.0/v0.6.0): el SHA
   en STATE apunta a un commit docs(changelog) o feat, NO al commit
   donde el tag esta realmente puesto.
3. **`release.tag: v0.6.0` stale** (debería ser v0.14.0).

## Impacto

- **Regla 3 (CIERRE REAL)**: el "último estado verificado" en
  STATE.yaml debe ser el realmente observable. Si dice v0.6.0
  cuando la realidad es v0.14.0, una sesión futura que reanuda
  leyendo STATE.yaml arranca con información obsoleta.
- **Regla 7 (TRAZABILIDAD)**: docs sincronizadas.
- **Regla 4 (CALIDAD)**: detecto esto al verificar coherencia
  documental tras T8.

## Causa raíz

La sección `release.releases` y `release.tag` se quedaron en
v0.6.0 al cierre de la iniciativa g-skillgraph-bootstrap
(2026-09-23). Etapa 7 (v0.7.0..v0.14.0) se cerró como
"refactor follow-up" + "Etapa 7 cerrada" en el propio STATE.yaml
(`etapa7_closed_after_tag: v0.14.0`) **pero nadie actualizó la
sección release**. Es un drift documental, NO técnico.

El commit `878a159 docs(state): sincronizar STATE/CURRENT con
realidad v0.14.0` re-sincronizo tests, coverage y goal.*, pero
omiti la seccion `release.*` por oversight.

## Decisión sobre SHAs divergentes

Estrategia: usar `git rev-list -n 1 vX.Y.Z` (el commit al que
apunta el tag, NO un commit feature intermedio). Esto da la
cita canonica reproducible via `git show vX.Y.Z`.

## Acción

Sincronizar STATE.yaml.release con la realidad verificable:

1. `release.tag: v0.14.0` (último tag real).
2. `release.fecha: 2026-09-24`.
3. `release.semver_bump: MINOR` (sin breaking desde v0.13.0).
4. Reescribir `release.releases:` con las 14 releases reales
   y los 14 SHAs de tag (no de feature commit).
5. Ampliar `release.capacidades_entregadas:` con las
   capacidades v0.7.0..v0.14.0 (refactor arquitectonico +
   6 slices Etapa 7).
6. Actualizar `release.evidencia.tag_sha` para reflejar v0.14.0
   (no v0.6.0).

Adicionalmente:

7. Verificar que `.next-decision.md` no requiere actualizacion
   (es snapshot del cierre de iniciativa, OK dejarlo en v0.6.0).
8. CHANGELOG.md ya cubre v0.14.0 (verificado, 1408 LoC).
9. SESSION-JOURNAL.md cubre la sesion 2026-09-25 con T8
   (sesión 09:15-09:37). OK.

## Plan de cierre (regla 3 CIERRE REAL)

- **No bump**: este es un fix documental, no una feat.
  Sync de docs no genera release (regla 4 SEMVER: docs no bumpa).
- **2 commits atómicos**:
  1. `docs(state): sincronizar release.tag + releases[] con v0.14.0`
  2. `docs(journal): sesion 09:43-09:55 sync estatal post-T8`
- **Verificación**:
  - `git diff STATE.yaml` deja solo los huecos rellenados.
  - `git tag --list 'v0.*' | wc -l` == 14.
  - `grep -c '^    - tag: v0' STATE.yaml` == 14.
  - `python3 -c "import yaml; yaml.safe_load(open('STATE.yaml'))"`
    parsea sin error.

## Coste

- ~15-20 min de edicion + verificacion.
- 0 LoC produccion modificados.
- 0 tests afectados (regla 1: TESTING QUIRURGICO no requiere
  re-correr 772 tests, son docs).
- Riesgo: muy bajo (escritura YAML con campos existentes,
  no se introduce schema nuevo).

## Lo que NO se hace en este audit

- No se reabre la iniciativa (ya cerrada en v0.6.0).
- No se modifica CHANGELOG.md (ya cubre v0.14.0).
- No se modifica .next-decision.md (snapshot historico OK).
- No se aborda backlog P1 opciones A/B/C (requieren spec
  operador; este audit es stewardship documental puro).
- No se retagean SHAs intermedios (los tags reales son los
  vigentes; los SHAs en STATE estaban mal cited, no los tags).
