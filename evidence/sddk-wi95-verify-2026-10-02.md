# WI-95 — El CHANGELOG decía `[Unreleased]` para bloques que ya se habían publicado

- **Ciclo**: `p-b7740b96d79ec013/wi-95-changelog-claims-unreleased-work`
- **Fecha**: 2026-10-02
- **Suite**: 2559 passed (2551 antes; +8)
- **Commits**: `9caeaa2` (corrección del CHANGELOG), `b06c258` (el guard)

## La medición, antes de tocar nada

El bloque empieza con la misma pregunta que abrió WI-93 y WI-94: *¿qué
contratos declara el repo que nada comprueba?* `STATE.yaml` tiene una red que
lo ata a `git tag` con igualdad exacta desde WI-74
(`tests/test_state_release_integrity.py`, 8 tests). **`CHANGELOG.md` no tenía
ninguna.**

| Medición | Valor |
|---|---|
| tags SemVer en git | 46 |
| versiones distintas en CHANGELOG | 44 |
| tags **sin sección** | **2** (`v0.16.14`, `v0.16.15`) |
| secciones con versión **sin tag** | 0 |
| cabeceras `[Unreleased]` de bloques publicados | **3** (WI-87, WI-88, WI-89) |
| tests que parseen el CHANGELOG | **0** |

## Qué afirmaba, y qué era verdad

El fichero llevaba **dos releases de desfase** sin que nada lo notara.

| Cabecera | Realidad medida |
|---|---|
| `## [Unreleased] — WI-89` | publicado como **v0.16.15** (`6819f99`) |
| `## [Unreleased] — WI-88` | publicado como **v0.16.14** (`3cfce09`) |
| `## [Unreleased] — WI-87` | publicado como **v0.16.14** (`3cfce09`) |

Un `[Unreleased]` es una promesa: *este trabajo todavía no ha salido*. Con el
tag puesto, la promesa es falsa.

### El fichero se contradecía a sí mismo

Lo más incómodo no era la cabecera: era que el **cuerpo repetía la misma
falsedad con la verdad en la misma frase**.

La sección de WI-88 decía, en dos líneas consecutivas:

> **Sin bump todavía**: el `fix(cli)` de este bloque dispara el PATCH; la
> release que lo contiene es `v0.16.14`.

«Sin bump todavía» y «la release que lo contiene es v0.16.14» no pueden ser
ambas ciertas. Lo eran cuando se escribió —el tag aún no existía— y dejaron de
serlo al etiquetar, sin que nadie volviera a leer la frase.

## La corrección

Cuerpo intacto salvo donde repetía la misma falsedad. Cada sección lleva una
nota `CORREGIDA` que dice qué estaba y por qué, siguiendo la línea de WI-91
con las afirmaciones propagadas: **la corrección se escribe en el documento,
no se aplica en silencio**.

Corregir una etiqueta de versión **no es reescribir historia**: el relato del
cambio no se toca, y la afirmación que se corrige es sobre el presente
(*¿esto salió o no?*), no sobre lo que ocurrió.

## El guard

`tests/test_wi95_changelog_release_claims.py`, 8 tests. Comprueba la
**propiedad**, no el texto de una sección:

1. **Biyección con `git tag`**: todo tag SemVer tiene sección, y toda sección
   con versión tiene tag.
2. **Nada publicado se anuncia como `[Unreleased]`**.
3. **Una `(cont.)` tiene su versión padre justo antes**, y **sólo la primera
   aparición de una versión puede no ser continuación**.

### Un agujero encontrado por la mutación M3, al primer intento

La primera versión del guard comprobaba la regla de `(cont.)` contando
repeticiones: *ninguna versión con más de dos secciones*. M3 —convertir un
`(cont.)` en una sección de versión más— **no la cazó**, porque dos secciones
no son «más de dos».

El invariante correcto no es contar, es de forma:

> Sólo la primera aparición de una versión puede no ser continuación.

Sin eso, la convención `(cont.)` es **decorativa**: nada obliga a marcarla, así
que puede dejar de marcarse sin que nadie lo note. La mutación se aplicó al
artefacto (el CHANGELOG), no al código del guard, porque lo que hay que
demostrar es que el guard detecta cuando el documento vuelve a mentir.

| # | Mutación | Resultado |
|---|---|---|
| M1 | volver a `[Unreleased]` una release publicada | **cazada** |
| M2 | anunciar `v0.16.99`, que git no tiene | **cazada** |
| M3 | convertir un `(cont.)` en versión suelta | **cazada** (tras cerrar el hueco) |
| M4 | control final: byte-idéntico | **OK** |

`cazadas=3  no-cazadas=0  no-aplicadas=0`

## El desorden antiguo: medido, documentado, NO arreglado

La secuencia de versiones del fichero **no está en orden descendente**:

```
... 0.14.1 | 0.7.0  0.7.1  0.7.2  0.8.0  0.7.3  0.6.0  0.5.0  0.4.1  0.4.0
    0.3.0  | 0.8.1  0.9.0  0.10.0 ... 0.14.0
```

Diez pares fuera de orden, un `0.8.0 → 0.7.3` suelto, y dos tramos de otra
época con otra convención.

**No se corrige, y es una decisión, no una pereza:**

- Es **cosmético**. Ningún lector, script ni release depende del orden.
- Es **preexistente**, de una época con otra convención.
- Mover 20 secciones de texto histórico es exactamente el riesgo que este
  proyecto lleva cuatro bloques evitando (WI-91, WI-92, WI-93, WI-94).

La alternativa —exigir orden global en el guard— haría que fallara en el
primer run por culpa de secciones de 2026-09, y **un guard que falla por ruido
se aprende a ignorar**, que es peor que el defecto que vigila.

Lo que sí se vigila es que **la zona que se escribe hoy** (≥ 0.14.1) siga en
orden descendente. El test se llama `test_el_tramo_moderno_se_mantiene_ordenado`
y sólo mira ahí.

## Conocimiento negativo

- **Un documento puede contradecirse a sí mismo línea a línea.** La
  contradicción interna («sin bump todavía» / «la release que lo contiene es
  v0.16.14») es **más fácil de detectar** que la falsa afirmación aislada, y
  estaba debajo de la vista. Cuando dos frases del mismo párrafo se
  contradicen, una de las dos se quedó en el tiempo: hay que preguntarse cuál
  cambió, no cuál es falsa.
- **Un regex que se queda en el primer `]` no ve el `(cont.)`**, porque va
  fuera de los corchetes: `## [0.16.19] (cont.)`. Un test que cuenta
  continuaciones con ese regex cuenta **cero** y da verde sin comprobar nada.
  Es la misma familia que el `rc` de un `| tail`: un assert sobre una
  subcadena comprueba que la subcadena exista, no la propiedad.
- **Un guard que exige un orden que el propio fichero no cumple se aprende a
  ignorar.** Vigilar la zona que se escribe hoy es útil; exigir orden global
  sobre historia que nadie va a tocar es ruido.
- **Agrupar un fix pendiente es lo que hace útil la regla de cadencia.** En
  WI-94 se resistió abrir una etiqueta por un `fix` de tests. Una release más
  tarde salió con dos `fix` —el pendiente y el del bloque nuevo— y ninguna de
  las dos es trivial. La tentación de la micro-release se paga sola.

## Lo que sigue sin probarse

Este bloque **no** toca la cobertura ni los adaptadores. El criterio de salida
de **H9** sigue declarado incumplido por la razón de siempre: no hay
credenciales de proveedor real (Anthropic/OpenAI) en este entorno, y eso no es
resoluble desde el repositorio.
