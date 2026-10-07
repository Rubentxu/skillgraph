# B38 — El gate más cercano al push decía `SUCCESS` sin haber comprobado nada

> Medición hecha **antes** de escribir una línea.
> Script: `scripts/measure_b38_pre_push.py`, nueve rondas.
> Sondas: `scripts/mutate_b38_pre_push.py`, nueve sondas.
> Commits: `042c0fd` (medición ampliada), `d023277` (el arreglo y sus siete
> tests), `f66dc29` (el harness), `54b8fe0` (la cifra), `a6cd712` (el
> verificador).
> Recibo: **4125 passed, 3 skipped, 0 failed, 842,69 s, rc=0**, sobre `a6cd712`
> con el árbol limpio. 4125 + 3 = **4128** = `STATE.yaml tests.total`.
> Suelos rc=0 (`cli/` 93,31 %, `runtime/` 98,41 %, global 97,13 %) ·
> `project_truth` rc=0 · ratchet 5/5 a cero · sondas **B38 9/9**, **B37 6/6**,
> **B36 5/5**, **B35 8/8** — las tres primeras series se vuelven a correr porque
> B38 toca el mismo fichero de hook que B37 y los hooks comparten guard.

## DE DÓNDE SALIÓ

El subtítulo de B37 era «lo que el hook de pre-push no llega a medir», y eso
estaba escrito **sin haberlo medido**. Es el mismo defecto que el gate de
`v0.42.1` le cazó al autor: una afirmación con la autoridad del nombre de un
bloque y sin instrumento detrás.

## EL BYPASS NO ERA EL DEFECTO

Medido, con un `scripts/ci.sh` de doble y el hook real:

```
R6  `ci.sh` = `exit 0` y NADA MÁS
    [pre-push] OK: la receta canonica dio SUCCESS sobre 718b683

R7  `ci.sh` = imprime el veredicto de la receta y sale 0
    [pre-push] OK: la receta canonica dio SUCCESS sobre 718b683

R8  salida del hook con R6 IDÉNTICA a la de R7: True
```

Con `HOOK_SKIP_PUSH_TESTS=1` la última línea era exactamente la misma, con la
receta sin ejecutar. **R8 es la ronda que decide el alcance**: el bypass era
**un caso** de un defecto estructural, no el defecto.

El hook **delega** y solo sabe una cosa: que el delegado devolvió 0. Un exit
code de 0 dice que el proceso terminó — no que la receta corriera, ni que
hiciera nada.

Es el defecto de B37 en el pre-commit con una palabra más fuerte: allí el `OK`
era neutro y se podía leer como «el hook ok»; aquí el `SUCCESS` afirma una
ejecución que no ocurrió, **en el gate que está a un comando de salir del
repo**.

## LO QUE SE ARREGLA, Y NO ES INVENTADO

`.pipeline.kts` imprime `Pipeline finished with SUCCESS`, y no es una cadena
elegida para el arreglo:

- **20 apariciones byte a byte iguales** en los artefactos del repo, en línea
  propia y sin nada alrededor;
- es la **misma** cadena que el propio hook ya nominaba en su mensaje de error.

O sea que el hook ya tenía en la mano todo lo que hacía falta: capturaba esa
salida en `$_log` y **después la borraba sin haberla mirado**.

```sh
if ! grep -qxF "$VEREDICTO_RECETA" "$_log"; then ... exit 1; fi
```

El `OK` deja de ser una copia del exit code y pasa a ser una afirmación
verificada contra el propio delegado. Si el delegado sale con 0 y no emite su
veredicto, el hook se pone rojo en vez de decir `SUCCESS`.

## LAS SONDAS ENCONTRARON UN AGUJERO EN EL ARREGLO

La primera versión del arreglo usó `grep -qF`. Las sondas lo cazaron:

| # | sonda | diagnóstico |
|---|---|---|
| M1 | el grep exige una frase que nadie emite | el camino bueno exige `rc == 0` |
| M2 | el grep acepta una línea que **contiene** el veredicto sin **ser** el | la línea entera |
| M3 | el bypass vuelve a afirmar `SUCCESS` | el bypass se declara |
| M4 | el bypass vuelve a callarse | el bypass se declara |
| M5 | el `OK` deja de citar el veredicto que exigió | el camino bueno lo cita |
| M6 | la cadena exigida no es la que declara el resto del repo | veredicto derivado |
| M7 | dice el error y **no corta el push** | el código de salida |
| M8 | sin la `x` del grep, vuelve a aceptar la subcadena | la línea entera |
| M9 | el grep pasa a no-sensible-a-mayúsculas | la capitalización |

**M2 y M8 son el hallazgo.** Exigir que la frase **esté** en la salida no es
exigir que **sea** el veredicto: un delegado que imprimiera
`Pipeline finished with SUCCESS (rehecho)` contiene la frase entera y no ha
ejecutado la receta. Con `-x` se cierra, y no afloja nada porque está medido:
la receta emite esa frase sola en su línea.

**M1 y M9 no mataban a nada, y las dos hay que decir por qué.**

- **M1** apuntaba al test del camino **malo**, y ahí no puede caer: con la frase
  cambiada el grep tampoco la encuentra cuando el delegado no emite nada,
  luego `rc != 0` se cumple igual y el test pasa. La frase equivocada rompe el
  camino **bueno**, que es el que exige `rc == 0`. Es el error de razonar
  sobre *qué cambia* en vez de sobre *qué se rompe*.
- **M9** se apoyaba en `Successful` como contraejemplo, y `Successful` **no es**
  `SUCCESS` con otra capitalización: es **otra palabra más larga**. El grep la
  rechazaba con y sin `-i`, luego la sonda no medía nada y se reportaba como si
  midiera. De ahí salió el séptimo test: una **variante de capitalización** de
  la frase exacta sí distingue.

## CUATRO VERIFICADORES DÉBILES, TODOS CON LA MISMA CAUSA

El instrumento de este bloque dio cuatro lecturas equivocadas en lugar de
ninguna:

1. **R1** decidía por `splitlines()[-1]`. En un repo que no es git,
   `git rev-parse` revienta y la línea del `SUCCESS` queda dos más arriba.
2. **R8** comparaba la salida **entera** de dos corridas: lo único que las
   diferenciaba era el sha del commit del repo temporal.
3. Normalizado el sha, **R8 seguía dando `False`**: el `rm -f "$_log"` del hook
   lo intercepta `mavis-trash`, que imprime una línea con el nombre del
   temporal. Otro valor que cambia por construcción.
4. **R6/R7** buscaban la cadena `SUCCESS` en toda la salida. Tras el arreglo el
   mensaje de error del hook **contiene** esa cadena, luego la ronda reportaba
   que el hook seguía diciendo `SUCCESS` con un hook que ya no lo hace.

**La lección es general y por eso queda escrita:** comparar dos corridas exige
normalizar **todo** lo que varía por construcción, y esa lista no se adivina a
ojo. Se ve cuando el comparador dice `False` y el diff son dos líneas de ruido.

## EL HARNESS SE ROMPIÓ TRES VECES ANTES DE CONTAR

Y una era **el mismo defecto de B13 y B36, por tercera vez**:
`replace(..., 1)` sobre un anclaje no único. El anclaje
`if ! grep -qF ...` aparece **dos veces** en el hook —en un comentario y en el
código—, luego M2 mutó la **prosa**, dejó el código intacto, el hook siguió
vigilado y el harness la reportó `INOCUA`. Una sonda que cambia un comentario
no mide nada.

El arreglo no fue apuntar al texto correcto: fue que el harness **no pueda**
contarse una sonda como ejecutada si su anclaje no aparece exactamente una vez,
y que **diga el recuento** cuando no. Con eso, la ronda siguiente se paró en
seco al quedar el anclaje viejo tras el cambio a `-x`, en vez de reportar nueve
cazadas sobre un hook que no había medido.

## LO QUE SE CORRIGE DE MÁS, Y ESTABA MEDIDO

El hook anunciaba `~4min`. El push de `v0.42.2` del 2026-10-07 tardó
**13 min 49 s** (23:56:14 → 00:10:03). Una afirmación del hook que nada mide, y
del mismo tipo que el `SUCCESS`.

También: el hook instalado en `.git/hooks/` estaba en `111ef242…` mientras el
versionado iba en `77a79a94…`. El gate que gobierna cada push era el que estaba
en el disco, y por eso la medición trae la ronda R3.

## LO QUE NO SE ARREGLA

**El bypass sigue existiendo.** `HOOK_SKIP_PUSH_TESTS=1` es legítimo —el propio
hook lo ofrece— y lo que cambia es que **ahora se declara**:

```
[pre-push] tests: OMITIDOS por HOOK_SKIP_PUSH_TESTS=1 — este push NO ha sido verificado
```

**Y si la frase cambia, el hook se pondrá rojo.** Es lo correcto: es
fail-closed, y el mensaje de error cita la frase que esperaba. El séptimo test
deriva del árbol que el veredicto exigido es el mismo que declaran los
instrumentos que lo emiten, para que ese cambio se note en la suite y no en el
próximo push de todos.