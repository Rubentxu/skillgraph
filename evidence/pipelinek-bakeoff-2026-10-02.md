# Bake-off pipelinek: 0.43.0 (asdf, defectuoso) vs 0.46.0 (mise, confiable)

Fecha: 2026-10-02
Alcance: resolver con datos el backlog "pipelinek version sin gobernar"
(WI-57/63): que version produce veredictos CONFIABLES sobre el
`.pipeline.kts` real de este repo dentro del entorno agentico.

## Resultado

| Binario | Origen | unit-tests | Veredicto |
|---|---|---|---|
| 0.43.0 | shim asdf (activo por PATH) | FAILURE falso a ~10s sin captura; en otro run SUCCESS sin ejecucion visible | **NO confiable** |
| **0.46.0** | `mise x pipelinek@0.46.0` | **87.7s reales, EchoOutputCaptured con `1880 passed in 87.26s`**, journal completo | **CONFIABLE** (run verificado: `15fbceb1-c4cc-4b55-b81e-ae402c0504a5`) |

Run de verificacion 0.46.0 (journal del engine, secuencia 18-21):
StepStarted 07:15:48.6 -> EchoOutputCaptured 07:17:16.7 con los puntos
de pytest y "1880 passed in 87.26s" -> StepFinished -> success. Todos
los stages (discover/sync/unit-tests/lint/evidence) con captura real y
"Pipeline finished with SUCCESS".

## Causa raiz del defecto de 0.43.0 (diagnostico previo, WI-57/63)

El paso `unit-tests` era dado por muerto a los ~10s (el pytest real
seguia vivo y terminaba bien) o declarado exitoso sin ejecucion
visible: supervision por cookie/pipe defectuosa en la build 0.43.0.
El canon AGENTS.md (v0.39.0) ni siquiera esta instalado.

## Recomendacion al operador

1. **Fijar 0.46.0 como canonico** via mise: anadir
   `[tools] pipelinek = "0.46.0"` a `mise.toml` (o equivalente asdf) y
   actualizar AGENTS.md (canon v0.39.0 obsoleto y no instalado).
2. NO usar el shim asdf 0.43.0 mientras dure la transicion.
3. Decision final: del operador (este documento solo aporta los datos).

## Evidencia cruda

- Run 0.46.0: journal JSON en la salida del comando (runId
  `15fbceb1-c4cc-4b55-b81e-ae402c0504a5`, db de experimento
  `.pipelinek/db-046.sqlite`, control `.pipelinek/control-046/`).
- Run 0.43.0 previo: FAILURE falso documentado en
  `evidence/investigation-2026-10-02.md` y SESSION-JOURNAL 02-oct (X).

## Limpieza

Los artefactos del experimento (`.pipelinek/db-046.sqlite`,
`.pipelinek/control-046/`) NO se versionan: experimento aislado de la
CI canonica (`.pipelinek/db.sqlite` / `.pipelinek/control/`).
