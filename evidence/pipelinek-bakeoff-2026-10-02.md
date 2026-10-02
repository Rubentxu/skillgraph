# Bake-off pipelinek — correccion controlada (2026-10-02)

Fecha: 2026-10-02
Alcance: resolver con datos el backlog "pipelinek version sin gobernar"
(WI-57/63): que binario produce veredictos CONFIABLES sobre el
`.pipeline.kts` real de este repo dentro del entorno agentico.

> **Este documento CORRIGE una version previa del mismo dia.** Esa
> version afirmaba que el binario `0.43.0` (shim asdf) era "NO confiable"
> (FAILURE falso a ~10s) y que el canon de AGENTS.md `v0.39.0` "ni
> siquiera esta instalado". **Ambas afirmaciones son incorrectas.** El
> bake-off inicial solo miraba los installs de asdf y atribuyo a una
> version un fallo transitorio no reproducible. Los datos de abajo
> provienen de tres runs controlados, cada uno con su propio journal.

## Runs controlados (los tres con ejecucion real)

| Binario | Origen | unit-tests | Wall | Veredicto |
|---|---|---|---|---|
| **0.39.0** | mise (backend `github:Rubentxu/pipeline-kotlin`) | `1880 passed in 86.12s` | ~87s | SUCCESS, captura completa |
| **0.43.0** | shim asdf | `1880 passed in 85.64s` | ~94s | SUCCESS, captura completa |
| 0.46.0 | asdf | `1880 passed in 87.26s` | ~88s | SUCCESS, captura completa |

RunIds:

- 0.39.0 — `ef3f2706-4a83-4b25-b23f-05a9d3d89a33`
  (db `.pipelinek/db-0390.sqlite`, control `.pipelinek/control-0390/`)
- 0.43.0 — `02acc69b-6112-44c4-bd60-0ec4e65a7541`
  (db `.pipelinek/db-asdf43.sqlite`, control `.pipelinek/control-asdf43/`)
- 0.46.0 — `15fbceb1-c4cc-4b55-b81e-ae402c0504a5` (run del bake-off inicial)

En los tres: journal con `CompilationStarted`, `RunStarted`,
`StageStarted`, `StepStarted`, `EchoOutputCaptured` con la linea de
pytest, `StageFinished/success` en los 5 stages, `RunFinished/success`,
`Pipeline finished with SUCCESS`, **cero `StepFailed`** y **cero
`RunFinished/failure`**. Ademas `All checks passed!` en el stage `lint`
y `last-run present` / `workspace tracking present` en `evidence`.

## Correccion 1 — el "FAILURE falso a ~10s" no se reproduce

Bajo test controlado, `0.43.0` ejecuta la suite completa (85.64s) y
emite `SUCCESS` con la captura real de pytest. El sintoma descrito
anteriormente no se reprodujo. **Conclusion: no hay evidencia de que
la version sea la causa; el sintoma, de existir, fue transitorio y su
atribucion a la version no esta sostenida.** No se debe cambiar el
canon por ese motivo.

## Correccion 2 — 0.39.0 SI estaba instalado

`mise ls --installed` registra `github:Rubentxu/pipeline-kotlin 0.39.0`.
El canon de AGENTS.md estaba disponible todo el tiempo; el bake-off
inicial solo inspecciono `~/.asdf/installs/` y concluyo que faltaba.

## Causa raiz real: ambiguedad de PATH entre dos gestores de tools

El defecto no estaba en ninguna version, sino en que **dos gestores de
tools coexistian** sin que el repo lo declarara:

- `asdf` expone `pipelinek` como shim en `PATH`
  (`/home/rubentxu/.asdf/shims/pipelinek`).
- `mise` mantiene `github:Rubentxu/pipeline-kotlin` instalado
  (0.39.0, 0.39.1-rc1, 0.43.0) y `~/.config/mise/config.toml` fijaba
  0.39.1-rc1.
- `mise.toml` del repo **no fijaba `pipelinek` en absoluto**.

Consecuencia: el comando canonico de AGENTS.md
(`pipelinek run --db .pipelinek/db.sqlite ...`) resolvia al shim de
asdf, no al canon documentado. Que ese shim funcionara o no era
irrelevante: el veredicto no era reproducible entre maquinas.

## Correccion aplicada

`mise.toml` fija el canon, con el **id de backend completo**:

```toml
"github:Rubentxu/pipeline-kotlin" = "0.39.0"
```

El id completo es obligatorio: un `pipelinek = "0.39.0"` suelto crea
una entrada de tool distinta que `mise ls` reporta como `(missing)` y
rompe `mise exec -- pipelinek`. Verificado tras el cambio:
`mise which pipelinek` -> `.../0.39.0/bin/pipelinek` y
`VALIDATION SUCCESSFUL`.

Se elige 0.39.0 porque es el canon ya documentado en AGENTS.md
("pipelinek v0.39.0"), no porque sea superior: los tres runs son
equivalentes en veredicto.

## Decision pendiente del operador

Ninguna sobre la version: los tres funcionan y 0.39.0 ya es el canon.
Queda decidir si AGENTS.md debe dejar de describir el binario a mano
(0.39.0, `pipelinek-0.39.0.zip`) y remitir a `mise which pipelinek`,
para que la version se lea del pin y no de la prosa.

## Limpieza

Los artefactos de los experimentos (`.pipelinek/db-0390.sqlite`,
`.pipelinek/db-asdf43.sqlite` y sus controles) NO se versionan:
experimentos aislados de la CI canonica (`.pipelinek/db.sqlite` /
`.pipelinek/control/`).
