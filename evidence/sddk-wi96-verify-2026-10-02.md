# WI-96 — La regla de SemVer estaba escrita donde nadie la verifica, y es falsa tal cual

- **Ciclo**: `p-b7740b96d79ec013/wi-96-semver-rule-declared-never-derived`
- **Fecha**: 2026-10-02
- **Commits**: `8e147e1` (la regla a su dueño), `08d4a60` (el cálculo), `da86a66` (dos correcciones que impuso el uso)

## La pregunta

La de WI-93 y WI-95, por tercera vez: *¿qué declara el repo que nada
comprueba?* Esta vez el contrato no es un suelo de cobertura ni un registro
de release. Es **la regla que decide el número de versión**.

## La medición, contra la regla tal como estaba escrita

La reglaVivía **solo** en la cabecera de `CHANGELOG.md`:

> - `feat` → MINOR · `fix` → PATCH · `feat!`/`fix!`/`BREAKING CHANGE` → MAJOR ·
>   `refactor`, `test`, `docs`, `spec`, `chore`, `style` → sin bump

Aplicada a las **47 etiquetas** reales:

| | |
|---|---|
| releases cuyo SemVer **no se deduce** de la regla | 9 |
| de las cuales con un cambio rompedor real | 3 |
| releases que la regla dice que **no deberían existir** | 9 |

Y `AGENTS.md §12`, que se titula «Regla de release», **no la contenía**:
solo las reglas mecánicas (fuente de verdad, tag ↔ `__version__`, `.devN`).

## El dato que duele

`v0.7.0`, `v0.15.0` y `v0.16.2` hicieron **cambios rompedores** y ninguna llegó
a `1.0.0`. La regla escrita dice que un breaking change es MAJOR. El proyecto
la hizo mal tres veces, y cada vez lo decidió a mano porque en 0.x no
obligaba.

La exención 0.x que lo explica estaba escrita **en el mensaje de esos tres
commits y en ningún otro sitio**.

### Y el giro del bloque: ningún marcador

Al escribir el detector resultó que **los tres precedentes no llevan el
marcador de la convención**. No hay `!` en el asunto ni un footer
`BREAKING CHANGE:` al principio de una línea: lo que hay es una **viñeta de
prosa** («Esto es BREAKING CHANGE para importadores externos que usaban…»).

Eso no es un detalle, es **el problema entero**:

> Con el marcador, ninguna herramienta puede verlos. Sin él, el bump se
> deduce mal y la exención queda sin justificación visible.

El primer clasificador que escribí buscaba la cadena `BREAKING CHANGE` en el
cuerpo, y por eso contaba como breaking un commit que solo la *describe* —el
propio bloque que estaba escribiendo la cláusula se contaba a sí mismo. Al
corregirlo a la forma de footer (`^BREAKING[ -]CHANGE:?\s`), los tres
precedentes disappeared del recuento. La conclusión correcta no es «no eran
breaking», sino **«fueron breaking y no estaban marcados»**.

## Lo que hace el bloque

1. **La regla se muda a `AGENTS.md §12`** («Derivar la versión»), que es su
   dueño, e incorpora la **salvedad 0.x** con los tres precedentes nombrados.
   Salir de 0.x queda escrito como decisión explícita.
2. **El CHANGELOG pasa a referenciar §12.** Dos enunciados de la misma regla
   son dos fuentes que se desincronizan, y una ya se ha desincronizado.
3. **`scripts/derive_semver.py`**: calcula el bump de cada etiqueta **y de
   HEAD**, e informa de las divergencias y de los cambios rompedores sin
   marcar.
4. **Las trece divergencias se registran, no se corrigen.** Son etiquetas
   publicadas; su número es provenance.

## El resultado que importa

```
== desde v0.16.20 hasta HEAD ==
  b/f/x/n/d: 0/1/1/2/0
  la regla pide MINOR -> v0.17.0
```

Y desde `v0.16.3` hasta `v0.16.20` el bump **se deduce sin excepción de
tipo**: 18/18. El guard exige coincidencia solo a partir de ahí, porque antes
el proyecto operaba con otra política y exigir la de hoy sería tan falso como
el defecto que se corrige.

## Mutaciones: 3/3, y las dos primeras las encontró el propio guard

| # | Mutación | Resultado |
|---|---|---|
| M1 | borrar la salvedad 0.x de `AGENTS.md §12` | **cazada** |
| M2 | volver a escribir la regla en la cabecera del CHANGELOG | **cazada** |
| M3 | que `clasificar` deje de reconocer `feat` | **cazada** |

- **M1 no la cazó la primera vez.** El test buscaba la cadena `0.x`, y la
  mutación la **conservaba** mientras vaciaba la cláusula. La aserción ahora
  exige la **sección** y que la regla de `1.0.0` aparezca **negada**, que es
  lo que hace la cláusula.
- **M2 no la cazó la primera vez, y es la de WI-95.** El patrón buscaba `->`
  y el fichero usa `→`: pasaba en verde **con la tabla presente**. Un guard
  que no encuentra lo que busca no vigila nada.

## Conocimiento negativo

- **Un guard que busca una cadena comprueba que la cadena exista, no la
  propiedad.** Dos veces en este bloque, con dos cadenas distintas.
- **Ensanchar una regla después de ver los datos es rehacer la regla.** El
  detector de «cambios rompedores sin marcar» identifica los tres
  precedentes, y **no cuenta** para el bump: la convención es la convención.
  Es una heurística con ruido, y por eso informa, no decide.
- **La decisión correcta puede seguir siendo invisible.** Las tres veces que
  no se subió a 1.0.0 se decidió bien; lo que faltó fue el marcador que la
  haría citable por una máquina. **Marcar cuesta un carácter y no obliga a
  nada** mientras se esté en 0.x, porque la cláusula lo exonera.
- **Un guard que exige algo que el propio repo no cumple se aprende a
  ignorar.** De ahí que la exigencia de coincidencia empiece en `v0.16.3` y
  no en la primera etiqueta, y que las divergencias se comparen
  bidireccionalmente: ni una nueva sin registrar, ni una vieja que se
  «arregle» sin quitar su nombre.
- **La herramienta se corrigió usándola.** Los dos fallos del clasificador
  (`BREAKING CHANGE` en prosa, y la falta de una dirección «qué versión
  toco») no salieron leyendo el código: salieron ejecutándolo.

## Lo que sigue sin probarse

Este bloque no toca cobertura ni adaptadores. El criterio de salida de **H9**
sigue declarado incumplido por la razón de siempre: no hay credenciales de
proveedor real (Anthropic/OpenAI) en este entorno, y eso no es resoluble desde
el repositorio.
