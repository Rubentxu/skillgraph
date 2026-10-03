# B6 — Exploración: el origen epistémico de cada afirmación

Fecha: 2026-10-03
Ciclo: `p-b7740b96d79ec013/b6`
Gate: `exploration-sufficient` → `phase.explore.complete`

## La pregunta del gate, literal

> **Gate B6.** Cada afirmación importante del Knowledge Graph distingue
> `observed` · `derived-deterministically` · `agent-inferred` ·
> `human-asserted`, y conserva su provenance.

Y la dirección que lo pide, del roadmap:

```
agente detecta necesidad → solicita capability → herramienta determinista
observa → normalizador produce hechos/evidencias → SkillGraph persiste
relaciones → agente interpreta
```

Lo que **no** debe pasar: *el LLM analiza el código, inventa la estructura
y escribe el grafo*.

## Medido antes de escribir nada

`scripts/measure_b6_provenance.py`, versionado en `scripts/` (no en
`.pipelinek/`, por el backlog `bl-bl-01M41DFZEZ0003882TZNP7NPM0`).

**Resultado: 4 de 4 preguntas en alcance ABIERTAS.**

| | pregunta | estado |
|---|---|---|
| P1 | ¿existe el origen epistémico como vocabulario cerrado? | ABIERTO |
| P2 | ¿el origen está tipado, o es `str` libre? | ABIERTO |
| P3 | ¿la base impone el vocabulario, o solo Python? | ABIERTO |
| P4 | ¿quién AFIRMA se distingue de CÓMO se extrajo? | ABIERTO |

## El hallazgo: el campo que parecía el sitio ya existía

No es un campo que falte. `Claim.extraction_method` está declarado desde
antes del bloque, y es el sitio donde uno lo pondría por nombre. Medido:

```
knowledge/graph.py::Claim.extraction_method   str = "static_analysis"
```

Sus tres valores escritos en el árbol son `static_analysis`, `regex_def` y
`manual` — y **los tres son métodos de extracción, no orígenes epistémicos**.

Son dos ejes ortogonales:

- `extraction_method` responde **¿CÓMO se extrajo esto?** — un regex, un
  análisis estático.
- el origen epistémico responde **¿QUIÉN AFIRMA que es verdad, y con qué
  autoridad?**

Con `extraction_method="regex_def"` no se sabe si lo afirmó la máquina, un
agente o una persona. Y escribir `agent-inferred` ahí perdería el método.
**Un campo no puede decir las dos cosas.** La separación no es una
preferencia de diseño: es la única forma de que el gate tenga dónde
escribir.

## Y medido, en contra de lo que parece

Lo que un `grep` sugiere es que el campo está en uso. Midiendo por capa:

```
extraction_method="manual"     10 escrituras  -> 10 en tests/,  0 en src/
extraction_method="regex_def"   4 escrituras  ->  4 en tests/,  0 en src/
```

**En `src/` no hay ninguna escritura explícita.** En producción sólo existe
el *default* de la declaración del dataclass.

Esto refuerza el hallazgo en vez de contradecirlo: el método de extracción
es un eje que **nadie rellena**. Un eje que nadie rellena no puede ser donde
nazca el origen epistémico.

## La tercera capa: la base no puede exigir lo que Python no exige

`claims.extraction_method` es `TEXT NOT NULL` **sin `CHECK`**. El
vocabulario, si existiera, viviría sólo en Python — y basta un `INSERT`
directo que no pase por `Claim` para colar cualquier texto. El gate
declara que «cada afirmación distingue su origen» y no lo puede exigir en
el sitio donde se escribe de verdad.

## Definición de terminación

El bloque se cierra cuando el medidor da **0 huecos abiertos en alcance**, y
el medidor es válido solo si:

1. **Sabe dar rojo.** Un instrumento que solo sabe decir «todo bien» no
   mide nada.
2. **Verde y rojo se distinguen por la misma medida.** El detalle de cada
   pregunta se deduce del mismo predicado que produce su veredicto.

Lo que queda **fuera de alcance** se registra y no baja el veredicto: es
deuda, no un olvido. En este bloque es **P5** — si el proveedor real *puebla*
conocimiento o lo *consume*—, que depende de una credencial que este
entorno no tiene.
