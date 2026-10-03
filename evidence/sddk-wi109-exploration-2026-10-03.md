# Informe de exploración — WI-109

Ciclo: `p-b7740b96d79ec013/wi109-code-a-exit` · Fecha: 2026-10-03
Serie: «¿qué declara el repo que nada comprueba?», undécima vía.

## La pregunta y su respuesta

La consigna del bloque era `AGENTS.md §1.2`: *prohibido `raise ValueError`
/ `raise Exception` en código de dominio*.

**Medida antes de tocar nada**:

```
grep -rn 'raise ValueError\|raise Exception' src/   ->  0 coincidencias
```

La prohibición literal **se cumple hoy**. La hipótesis de partida era
falsa en su premisa: no había un defecto que instrumentar, había un
guard que se habría escrito para no poder fallar nunca.

## Lo que la exploración encontró en su lugar

La misma sección §1.2 tiene una tercera viñeta que sí era cierta y no
estaba instrumentada:

> *Cada excepción lleva un `code` estable (`sg_*`) usado por la CLI para
> traducir a exit codes.*

Medido en tres partes (instrumentos en `.pipelinek/`):

1. **La traducción no existía.** `runner.main` hacía
   `except SkillGraphError -> return EXIT_DOMAIN` para todo. `EXIT_PARSE`
   y `EXIT_VALIDATION` sólo se alcanzaban porque cada comando repetía su
   propio `except ParseError`: la decisión la tomaba el **tipo** en el
   sitio de la llamada, y el `code` se imprimía sin decidir nada.

2. **Entrada de usuario malformada salía como traceback.**
   `knowledge compile <p> '{"obligatory": ['` devolvía `rc=1` con el
   `Traceback` entero de `json.JSONDecodeError`: el `json.loads` estaba
   **fuera** del `try` y `JSONDecodeError` no es `SkillGraphError`.
   Un defecto que ve el usuario, no una hipótesis.

3. **Tres clases compartían `sg_error`** (la raíz,
   `SelfCertificationBlockedError`, `HandoffBlockedError`) y **dos
   `sg_invalid_expansion`**. Un `code` compartido no puede mapear a dos
   exit codes distintos, y entonces el `code` deja de ser la clave: la
   traducción prometida **no se podía construir encima de él**.

## Instrumentos usados, y su estado

| instrumento | qué midió | veredicto |
|---|---|---|
| `.pipelinek/wi109_measure.py` | M1 literal, M2 builtins por AST, M3/M4 `code` efectivos | M1 = 0 (la regla se cumple), M2 = 14 raises fuera de jerarquía, M4 = 2 colisiones |
| `.pipelinek/wi109_exp.py` | el mismo `ParseError` por dos caminos, con sonda de mutación | sonda **válida** (11 → 13) |
| `.pipelinek/wi109_sondas.py` | cadena de captura de `main()` | sólo errores de dominio: un builtin escapa como traceback |
| `.pipelinek/wi109_mutate.py` | 11 mutaciones con sonda por mutación | 11/11 cazadas |

## Decisiones de alcance, y por qué

**Dentro**: la traducción `code -> exit`, los dos `json.loads` de entrada
de usuario, los tres `code` colisionados, el guard, y `§1.2` diciendo
cómo se comprueba.

**Fuera, registrado sin abrir frente**:

- Los **14 `raise` de builtins** (`TypeError` ×6, `KeyError` ×5,
  `RuntimeError` ×2, `NotImplementedError` ×1). Casi todos en
  invariantes internas de adaptadores (`unwrap()`, `dto.py`) y ninguno en
  el camino de error que ve el usuario. Un guard que declara exceptions
  en una lista es la misma lista un nivel más abajo.
- Las **4 funciones con ramas que devuelven el mismo exit code**
  (`expansion.py:446`, `promotion.py:361`, `runner.py:162`,
  `runner.py:382`): código muerto, no de dominio.

## Riesgo medido antes de escribir

Tests que afirman `rc == 10`: **16**. De ellos, los que son
`ParseError` o `ValidationError` (que deberían ser 11/12): **0**.
Consecuencia: el comportamiento as-built de 10 para errores de dominio
no distinguibles **está bien observado**. No se cambia.

## Riesgo residual, declarado

El segundo `json.loads` sin `try` (`support.py`, `plan.json`) queda
cubierto por el guard estructural pero **no se alcanzó por ejecución**:
la autorización de la propuesta se valida antes de cargar el plan.
Se dice porque todo lo demás se ha medido con el binario, y fingir
symetría en un punto no verificado sería el mismo defecto que este
bloque cierra.
