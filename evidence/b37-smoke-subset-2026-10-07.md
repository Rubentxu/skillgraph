# B37 — El bypass que queda, y lo que el hook de pre-push no llega a medir

> Medición hecha **antes** de escribir una línea.
> Script: `scripts/measure_b37_smoke_subset.py`, cuatro rondas sobre 1163 commits.
> Sondas: `scripts/mutate_b37_smoke_subset.py`, seis sondas.
> Commits: `30248ed` (medición), `8c3ca44` (el arreglo y sus cinco tests),
> `40617fc` (el harness), `a4dbb96` (la cifra).
> Recibo: **4118 passed, 3 skipped, 0 failed, 904,48 s, rc=0**, sobre `a4dbb96`
> con el árbol limpio. 4118 + 3 = **4121** = `STATE.yaml tests.total`.
> Suelos rc=0 (`cli/` 93,31 %, `runtime/` 98,41 %, global 97,13 %) ·
> `project_truth` rc=0 · ratchet 5/5 a cero · sondas **B37 6/6**, **B36 5/5**,
> **B35 8/8**.

## LO QUE SE MIDIÓ

```
551  no stagean .py          -> el smoke no lanza pytest
252  stagean solo codigo     -> `pytest -q src/...` colecta cero, rc=5, y el
                                hook sigue como si hubiera medido
264  stagean un solo test    -> corre ese y nada mas, sin decirlo
  3  stagean el guard de WI-116 tocando codigo

803 de 1163 commits — el 69 % — pasaron por el hook sin ejecutar un test
```

## EL DEFECTO NO ERA QUE EL SMOKE NO CORRIERA: ERA QUE SE CALLA

`scripts/hooks/pre-commit` anuncia el smoke **solo cuando lo corre**, y su
línea final era la misma en los tres caminos por los que puede pasar:

```
[pre-commit] OK
```

Medido sobre el hook real, antes del arreglo, en los tres caminos:

```
A  nada stageado          ->  [pre-commit] OK
B  HOOK_SKIP_TESTS=1      ->  [pre-commit] OK
C  smoke corrido          ->  [pre-commit] OK
```

Tres líneas, y **nada** sobre los tests. Un `OK` que se lee igual en los tres
es un `OK` que no dice nada, y quien lee el scroll no puede saber cuál de los
dos fue. La misma forma de fallo que WI-100 —donde el hook anunciaba «smoke,
N files staged» y corría la suite entera durante 124 s— y de WI-108, donde
un `skip` sin declarar se leía como una suite limpia: **no lo que se mide,
sino que quede escrito cuando no se midió**.

## LO QUE NO SE ARREGLA, Y SE DICE EN EL PROPIO HOOK

Este hook es un **filtro**, no una certificación. El veredicto sobre el repo
entero lo dan `scripts/hooks/pre-push` y la receta canónica, ambos con el
instrumento correcto. Que 252 commits puedan parecer verdes sin que nada se
haya medido es lo que hace un filtro; sustituirlo por la suite entera es lo
que WI-100 ya midió: **12× más lento para medir lo mismo**.

Lo que sí estaba roto, y es lo único que se arregla, es el **silencio**.

## EL ARREGLO

Bloque 4 del hook, tres ramas, siempre:

```
[pre-commit] tests: NINGUNO stageado — este commit no ha medido nada
[pre-commit] tests: OMITIDOS por HOOK_SKIP_TESTS=1 — este commit no ha ejecutado ninguno
[pre-commit] tests: el smoke de arriba es lo UNICO que ha corrido; el resto no se ha medido
[pre-commit] OK
```

Y lo declara **pegado al `OK`**, que es donde se lee.

## POR QUÉ LOS TESTS EJECUTAN EL HOOK Y NO LO LEEN

Un guard que buscara una cadena en el fichero aprueba el defecto entero: el
hook **tiene** `pytest` —el defecto de WI-100— y **tiene** `tests:` aunque
esté dentro del `if` del smoke, que es literalmente donde estaba antes del
arreglo. Lo que se mide es lo que el operador **ve**: se copia el hook sin
tocarlo a un repo de pruebas, se anteponen stubs de `mise`/`ruff`/`uv` al
PATH y se mira lo que imprime.

| # | propiedad | cómo |
|---|---|---|
| nada stageado, dice que no ha medido | `test_sin_ficheros_py_stageados_dice_que_no_ha_medido` | ejecución del hook |
| el bypass lo dice | `test_con_bypass_dice_que_los_tests_se_omitieron` | ejecución del hook |
| el camino que sí mide no pierde su anuncio | `test_con_smoke_corriendo_lo_dice_tambien` | ejecución del hook |
| **los tres caminos dicen algo** | `test_todos_los_caminos_dicen_algo_sobre_los_tests` | parametrizado sobre los tres |
| **el orden: la declaración precede al `OK`** | `test_el_ok_cierra_despues_de_declarar_los_tests` | las dos últimas líneas |

El quinto es el que más pesa, y no estaba en el diseño original. Sin él,
declarar la nota dos líneas más abajo deja el `OK` **exactamente igual de
indistinguible**, y el arreglo estaría a medio hacer sin que ningún test lo
notase.

## SONDAS: SEIS, Y LAS DOS QUE IMPORTAN SON M1 Y M6

Las sondas deshacen el **silencio**, no la lógica: cada una quita una rama
del bloque 4, o devuelve al bloque el defecto exacto que se cerró.

```
CAZADA  M1  el bloque dentro del `if` del smoke — el defecto exacto, en su forma literal
CAZADA  M2  sin la rama de «nada stageado»
CAZADA  M3  sin la rama del bypass
CAZADA  M4  el camino que sí mide tampoco cierra declarando
CAZADA  M5  el hook miente: dice «medido» donde no ha medido
CAZADA  M6  la declaración se mueve detrás del `OK`
```

**M1 y M6 son las que cubren las dos afirmaciones que el arreglo hacía sin
sostenerlas solo.** Entre las dos, quitan exactamente las dos cosas nuevas:

- M1 reduce la declaración a **un** camino. Un guard por búsqueda lo aprueba:
  el bloque se ejecuta, la cadena está, el hook sale con 0.
- M6 la deja **debajo** del `OK`, donde quien lee el scroll ve primero el
  «todo bien» y la nota queda fuera de la lectura.

M5 es la sonda de la mentira: no basta con que el hook diga *algo*, tiene que
decir lo que **es**. Un guard que exigiera «hay una línea sobre los tests»
aprobaría un hook que dice «medido» y no ha medido nada.

## EL INSTRUMENTO MINTIÓ ANTES DE CONTAR, Y SE PARÓ EN SECO

La primera versión del `BLOQUE_4` de M1 llevaba **guiones ASCII** donde el
hook tiene **em-dash** (U+2014). La sustitución no ocurría, la sonda no
mutaba nada, y el harness se habría reportado a sí mismo como *seis cosas
cazadas* sin haber medido una.

Es el error de WI-113 y el de B37 en un solo sitio: **una sonda que no
muta nada y se cuenta como cazada**. El arreglo no fue corregir la cadena,
sino que el harness **no pueda** llegar a contarla:

- comprueba **antes de mutar** que las tres líneas de la declaración siguen
  siendo las que el fichero declara, y si no, para en seco con el texto
  ausente;
- `CAZADA` exige que caiga el **diagnóstico nombrado** de esa sonda, no
  cualquier test rojo — cuatro sondas que heredan el fallo de la quinta se
  contarían como cuatro;
- `mutado == original` es `SIN_SONDA`, no `CAZADA`.

Y las sondas se cerraron **después** del `ruff format`, que es cuando tienen
que volver a probarse: el texto del fichero había cambiado y la cadena de la
sonda apuntaba al estado viejo.

## LO QUE EL HARNESS RESTAURA, Y POR QUÉ ESCRIBE

`git checkout --` restaura **del índice**, así que sin commit debajo
«restaurar» y «borrar» son la misma operación — el defecto que B36 cerró en
los siete `scripts/mutate_*.py`. Este harness escribe lo que leyó, y al
final comprueba **las dos cosas**: que la suite vuelve a pasar y que el hook
tiene byte a byte lo que tenía.

```
cazadas 6/6   invalidas 0   inocuas 0   sin sonda 0
tras restaurar: rc=0, hook intacto=True
```

## LO QUE SIGUE SIN MEDIR, Y SE DICE

**El bypass sigue existiendo.** `HOOK_SKIP_TESTS=1` es legítimo —el propio
hook lo ofrece— y los tres commits de este bloque lo usaron, porque stagean
`scripts/` y el smoke de un fichero de instrumentación no es una
certificación. Lo que cambia es que **ahora el hook lo dice**:

```
[pre-commit] tests: OMITIDOS por HOOK_SKIP_TESTS=1 — este commit no ha ejecutado ninguno
[pre-commit] OK
```

Es el primer caso del repo donde esa salida aparece en un commit real, y la
salida es exactamente la que el arreglo de este bloque produce.

**Lo que el pre-push no mide, y sigue sin medir.** La certificación de este
bloque es la receta canónica completa. El hook de pre-commit **no** la
sustituye, y las tres ramas del bloque 4 son exactamente la forma de que nadie
lo confunda: un `OK` que dice, en la línea de arriba, qué se midió y qué no.

**Y el 69 % no baja a cero.** Los 803 commits que no midieron ya están
escritos. Lo que baja es el número de commits **futuros** que puedan
parecer verdes sin que quede escrito que no se midieron.