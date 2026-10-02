# Verificación WI-102 — la receta canónica puede perder un contrato y seguir verde

- **Ciclo**: `p-b7740b96d79ec013/wi102-recipe-contracts-vanish`
- **Sesión**: `wi102-20261002T233501Z`
- **Fecha**: 2026-10-03
- **Run de certificación**: `efebb07c-1aee-4a15-8462-27efd4eca8f2`
  — 8/8 stages, **2673 passed in 224,37 s**, 0 `StepFailed`, árbol quieto
- **Run descartado**: `bbf59e06-46c8-4d1f-8ad4-b9fe977973f0` — dio SUCCESS, pero
  **no cuenta**: el árbol se editó mientras corría (§7).
- **SHA-256 de `.pipeline.kts`**: sin cambios desde WI-98
  (`d865896832f1c391344cb76a1b52b14c68915b99cefd985e976381dfe8d3ddcc`)

---

## 1. El hallazgo

`AGENTS.md` («CI Local Obligatorio») declara que `.pipeline.kts` es **la
fuente de verdad** y que ejecuta cuatro contratos exigibles. Se borró el
bloque entero de la etapa `coverage-floors` —la que impone los suelos que
`§6.3` declara exigibles— y se ejecutó el comando canónico de verdad.

| quién debía enterarse | resultado |
|---|---|
| `scripts/check_ci_recipe_parity.py` | **exit 0** — «OK: …» |
| `pytest tests/test_wi98_ci_recipe_parity.py` | **37 passed** |
| la receta, ejecutada de verdad | **`Pipeline finished with SUCCESS`** |
| ¿menciona `coverage-floors` en su salida? | **0** |
| ¿menciona su `VEREDICTO` de suelos? | **0** |

Receta: 5953 → 5439 bytes. Una etapa borrada, ninguna rotura. La receta
siguió siendo la fuente de verdad y ya no contenía la mitad de lo que la
fuente de verdad declara.

## 2. Causa raíz

`evaluar_etapas` (C3) comprobaba que `etapas_canonicas` fuera **legible**:

```python
declaradas = set(informe.etapas_canonicas)
if not declaradas:
    return (Problema(CODIGO_ETAPA_DESCONOCIDA, ...),)
return ()
```

Leer del script es correcto —es lo que evita un guard que vigila su propia
lista—, pero **leer** y **exigir** son dos cosas distintas y solo se
implementó la primera. Una lista de etapas vacía por legibilidad es tan
válida como una completa.

C4 exigía que quien ejecuta `pytest` esté **conectado** a la receta. Nadie
exigía que la receta **contenga** los contratos. Conectar sin contener, y
contener sin conectar, fallan igual.

## 3. C5

```
C5  todo `scripts/check_*.py` lo invoca la receta canónica
```

La forma es deliberadamente **sin lista**: el conjunto sale del repo, no de
una constante. Una lista de contratos obligatorios dentro del guard es la
misma trampa que `DIRECTORIOS_NO_RECETA` en WI-99 — obliga a mantener
enumerado lo que el guard debería comprobar solo, y ese mantenimiento es
precisamente el trabajo que se quiere automatizar.

Así, un checker nuevo entra en el contrato el día que se escribe, y borrar
una etapa se detecta porque el checker que invocaba deja de estar
invocado.

Cubre también el caso inverso, que hasta WI-102 era invisible: **escribir
un checker y no enchufarlo en la receta**. Es un guard que no guarda nada,
con la misma forma exacta que un guard real.

### Lo que no cubre

El descubrimiento es por la convención `check_*.py`, y se declara en vez de
disimularse. Un contrato escrito con otro nombre queda fuera del invariante,
igual que un script sin extensión quedaba fuera de C3 antes de WI-100.

## 4. Verificación después del arreglo, no antes

Misma mutación, mismo script autocontrolado:

| quién debía enterarse | antes | ahora |
|---|---|---|
| `check_ci_recipe_parity.py` | exit 0 («OK») | **exit 1**, `sg_ci_contrato_huerfano`, con el nombre del checker |
| `pytest test_wi98_ci_recipe_parity.py` | 37 passed | **3 failed** |
| la receta, ejecutada de verdad | `SUCCESS` | **`Pipeline finished with FAILURE`** |

La tercera fila es la importante: **la receta se detecta a sí misma**. El
stage `ci-parity` corre el checker, el checker sale con 1, el stage falla y
la receta deja de poder certificarse. Una receta a la que le quitas un
contrato ya no puede afirmar que lo cumple.

El mensaje de éxito también se actualizó: decía cuatro contratos y el
guard ya mide cinco. Un «OK» que no menciona el quinto deja al lector sin
saber que el quinto se puede borrar, que es el defecto de WI-101 en
miniatura.

## 5. Mutaciones — 6/6 en rojo

`.pipelinek/wi102_mutate.sh` + `.pipelinek/wi102_muts/m1..m6.py`. Las
mutaciones viven en ficheros Python aparte, no en `python -c` dentro del
shell: anidar comillas y barras invertidas entre bash y Python se rompió
dos veces durante este bloque, y un script de medición con el escapado mal
puesto no mide — falla por otra cosa y parece que midió.

| # | mutación | guard vigilado | clase de fallo | resultado |
|---|---|---|---|---|
| M1 | C5 → `return ()` explícito | `…sin_enchufar_se_detecta` | falso verde | ROJO |
| M2 | solo mira el primer huérfano | `…varios_sin_enchufar…` | falso verde | ROJO |
| M3 | el lector no quita comentarios | `…mencion_en_comentario…` | falso verde | ROJO |
| M4 | el descubrimiento no descubre | `…checker_nuevo_entra…` | falso verde | ROJO |
| M5 | el lector no admite subdirectorios | `…subdirectorio_se_reconoce` | **FALSO POSITIVO** | ROJO |
| M6 | la etapa borrada, **fichero real** | `TestC5ContraElRepoReal` | falso verde | ROJO |

**M6 es la contrapueba que hace este bloque distinto.** Sin ella, C5 sería un
invariante que solo sabe fallar con informes sintéticos: limpio en todas las
pruebas, ciego en el repo. Es la forma exacta de M5 de WI-101, el `echo` de
diagnóstico que contó como invocación durante dos commits.

**M5 es la única que produce un falso positivo**, y por eso es la que más
justifica el mutar. Un guard que no vigila es visible; un guard que señala
al código equivocado entrena a su lector a ignorar sus avisos.

## 6. Un fallo propio, encontrado durante el bloque

La primera versión de la regex de C5 no admitía carpetas entre `scripts/` y
`check_`, pero `checkers_de` descubre con `rglob`. Un checker en
`scripts/sub/check_x.py` entraba en el conjunto de contratos y su
invocación no se leía: se reportaba **huérfano un contrato que la receta
ejecuta**.

Lo destapó una **lectura** —el resultado de `checkers_invocados_por` con una
ruta anidada era un `frozenset()` vacío—, no un test.

Es la **tercera** vez en este bloque de tres workitems que un guard descubre
por una sintaxis y lee por otra: WI-99 dejó fuera los hooks al inventariarlos
por extensión, WI-100 los dejó fuera otra vez con `rglob("*.sh")` porque no
tienen extensión, WI-102 aquí. Arreglado en `d94c333`, con dos tests: uno que
el lector acepta el subdirectorio, y otro que compone las dos mitades sobre
un repo de verdad.

## 7. Dos certificaciones: una descartada y una contable

El run `bbf59e06` terminó con `Pipeline finished with SUCCESS` y **no cuenta**:
mientras corría (~4 min), las mutaciones estaban reescribiendo
`.pipeline.kts` y `scripts/check_ci_recipe_parity.py`. Editar durante la
certificación la invalida — no porque el resultado fuera falso, sino porque
nadie sabe qué ficheros leyó el `pytest` de dentro.

Se repitió sobre el árbol quieto: run `efebb07c`, 8/8 stages, 2673 passed,
`git status --porcelain` vacío al terminar. Un run verde sobre un árbol que
se movía no es una certificación: es una coincidencia.

## 7 bis. El guard de citas comprueba resolubilidad, no verdad

Las primeras citas del bloque vivo de `CURRENT.md` apuntaban a
`scripts/check_ci_recipe_parity.py:352` y `:479`. Esas líneas **existen** —el
fichero tiene 848— y no son las de C5, que están en 421 y 589.
`test_toda_cita_del_bloque_vivo_resuelve` las dio por buenas: comprueba que la
línea exista y que el fichero no sea ambiguo, no que la línea diga lo que el
texto afirma.

Anotado, no arreglado: es un guard que declara más de lo que mide, que es la
misma serie de este bloque una capa más arriba, y abrirlo aquí sería otro
workitem. Las citas se escribieron ya en las líneas ciertas, y el hecho queda
escrito en el propio `CURRENT.md` para que quien lo lea sepa que el guard de
citas tiene esa debilidad.

## 8. Certificación

| stage | outcome |
|---|---|
| `discover-repo` | success |
| `sync-deps` | success |
| `unit-tests` | success — **2673 passed in 224.37s** |
| `coverage-floors` | success |
| `package-build` | success |
| `ci-parity` | success — **ahora con C5** |
| `lint` | success |
| `evidence` | success |

`Pipeline finished with SUCCESS`, **0 `StepFailed`**, 8/8.

## 9. Criterios de aceptación

| # | criterio | estado |
|---|---|---|
| 1 | checker sin invocar en la receta → rojo | verificado (M1, M6) |
| 2 | checker invocado solo en un comentario → rojo | verificado (M3) |
| 3 | checker invocado en orden real → verde | verificado (`test_todo_checker_del_repo…`) |
| 4 | receta intacta → verde | verificado (`test_el_contrato_real_no_tiene_problemas`) |
| 5 | mutaciones | **6/6 en rojo**, una contra el fichero real |
| 6 | descubrimiento y lector ven lo mismo | verificado (M5, `d94c333`) |
| 7 | `ruff check src tests scripts` + `format --check` | verdes |
| 8 | receta canónica 8/8, `SUCCESS` | run `efebb07c` |

## 10. Lo que este bloque NO arregla

- **No exige un número de etapas.** Un número es una constante que hay que
  actualizar cada vez que se añade una etapa, y actualizar una constante
  para que un guard siga verde es el trabajo que el guard debería hacer solo.
- **No toca el contenido de ninguna etapa.** C5 vigila que los contratos se
  ejecuten, no que midan lo que su nombre dice. Un checker que se degrada en
  silencio sigue en verde y sigue enchufado: es un problema de otro
  workitem, y no se abre aquí.
- **No toca** `.gitignore`, los 4 errores de `sddk lint` de perfil *autor de
  pack*, los 63 informes de `audits/`, ni las líneas CJK preexistentes.
- **No hay push.** Sin autorización del operador.
