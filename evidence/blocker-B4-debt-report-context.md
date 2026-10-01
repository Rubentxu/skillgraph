# Blocker B4 — `sddk debt report` resuelve el contexto equivocado

Fecha: 2026-09-29
Severidad: **alta** (produce verde falso)
Estado: **abierto, con workaround documentado**

## Síntoma

`sddk debt report <OUT>` escribe un reporte cuyo `cycle_id` pertenece a
**otro proyecto**, y `sddk debt gates debt-severity-assigned` /
`debt-priority-assigned` responden `PASS` sobre ese reporte ajeno.

En este workspace:

```bash
$ sddk debt report /tmp/debt.json
wrote /tmp/debt.json
$ cat /tmp/debt.json
{
  "schema_version": "1.1.0",
  "cycle_id": "p-52b95ef55999f9de/kernel-cycle-8",   <-- otro proyecto
  "generated_at": "2026-09-29T11:20:20.852141427Z",
  "findings": []
}
$ sddk debt gates debt-severity-assigned
PASS: 0 findings checked
$ sddk debt gates debt-priority-assigned
PASS: 0 findings checked
```

El proyecto correcto es `p-74299cf88f51dab9` (confirmado por
`sddk adopt status --root . --scope .` y por
`sddk config resolve`).

## No es un problema de path

Se probó desde el directorio del proyecto real:

```bash
$ cd /home/rubentxu/.local/share/sddk/projects/p-74299cf88f51dab9
$ sddk debt report /tmp/debt2.json && cat /tmp/debt2.json
"cycle_id": "p-52b95ef55999f9de/kernel-cycle-8"   <-- idéntico
```

Mismo resultado. El subcomando no resuelve el contexto desde el CWD, y
`debt report` y `debt gates` **no aceptan `--root`, `--project` ni
ninguna opción de scoping** (verificado en `sddk debt report --help` y
`sddk debt gates --help`: no tienen opciones más allá de `-h`).

## Por qué importa

`findings: []` produce `PASS` en los dos gates de deuda. Si el
comando leyó el estado de un ciclo ajeno, ese `PASS` no dice nada
sobre este proyecto. Es exactamente el patrón de **verde falso** que
este repositorio ya conoce con los cache hits de `pipelinek`
(regla fijada en v0.16.5): un verde sin evidencia de que se ejecutó
sobre lo que dice medir.

El riesgo es concreto: `debt report` está ahí para encontrar deuda
del ciclo actual. Si siempre devuelve `findings: []`, cualquier
ciclo cuya fase de verify exija estos dos gates los pasa sin haber
mirado nada.

## Gravedad adicional: el reporte ajeno tiene contenido real

`sddk debt incs` llegó a listar **49 incidentes de `p-52b95ef55999f9de`**.
El vault de este proyecto,
`/home/rubentxu/.sddk-knowledge/p-74299cf88f51dab9`, está **vacío**
(`total 0`), lo que confirma que esos 49 INC no son de skillgraph.

## Workaround aplicado en este ciclo

No se usó el reporte generado por `sddk debt report`. Se usó el
reporte propio de este proyecto:

`/home/rubentxu/.local/share/sddk/projects/p-74299cf88f51dab9/cycle-artifacts/p-74299cf88f51dab9/wi-04-housekeeping-traceability/debt-report.json`

| Campo | Valor |
|---|---|
| `subject` | `516bb20ff9e541e1c196de24191b04161e0ffaf6` |
| `verdict` | `PASS` |
| `findings` | 0 |
| `closed` | 3 (WI-02B, WI-03, y una tercera) |

El `subject` `516bb20` es **ancestro de `HEAD`** y está dentro de la
release publicada v0.16.8 (`df72bcc`), verificado con
`git merge-base --is-ancestor 516bb20 HEAD` → exit 0.

Los receipts de gate registraran explícitamente que la evidencia
viene de este fichero y **no** de `sddk debt report`, para que nadie
después los lea como si el bug estuviera resuelto.

## Lo que hace falta para cerrarlo

Es un bug del framework SDDK (`sddk-engine` / `sddk-cli`), no de
skillgraph. Opciones, ninguna disponible desde este workspace:

1. Que `debt report` y `debt gates` acepten `--root` / `--project` /
   `--cycle`, como ya hacen `cycle` y `adopt`.
2. O que resuelvan el contexto por el mismo mecanismo que
   `sddk config resolve` (que sí devuelve el proyecto correcto).

Hasta que una de las dos exista, **`sddk debt gates` no debe usarse
como evidencia en este proyecto** sin verificar antes el `cycle_id`
del reporte.
