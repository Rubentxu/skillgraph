# ADR-0004 — Workflows dinámicos por composición y patches

Estado: propuesta para validar.

## Contexto

La generación de workflows completos puede producir
cambios difíciles de comparar y recuperar.

## Decisión propuesta

Utilizar subgrafos reutilizables y GraphPatches
que representen modificaciones mínimas.

El núcleo interpreta las transiciones.

El agente puede proponer ampliaciones,
pero no aplicarlas directamente.

## Motivos

Preservar decisiones y ejecuciones anteriores.

Evitar regenerar el workflow completo
ante cada problemática nueva.

## Alternativas

Árbol universal monolítico.

Generación de un script nuevo para cada ejecución.

## Evidencia pendiente

Spike de incorporación de un subgrafo
durante una ejecución activa.

## Revisit trigger

Revisar cuando un caso concreto requiera
generación de lógica de coordinación
que no pueda expresarse con las primitivas.
