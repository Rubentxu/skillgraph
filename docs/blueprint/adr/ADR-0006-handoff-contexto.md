# ADR-0006 — Handoff inmutable y contexto mínimo

Estado: aceptada como dirección de diseño.

## Contexto

Las conversaciones completas dificultan
la recuperación, el aislamiento y la trazabilidad.

## Decisión

Cada nodo recibe un handoff materializado
con contrato, contexto autorizado y referencias
al conocimiento necesario.

El handoff es inmutable y queda persistido.

## Motivos

Permitir agentes especializados y recuperación
sin dependencia del historial conversacional.

## Consecuencias

Se necesita un gestor de Context Recipes.

La información obligatoria no se elimina
para satisfacer límites de tokens.

Las fuentes externas se tratan como datos
y no como autoridad sobre los permisos.

## Revisit trigger

Revisar las recetas cuando las ejecuciones
demuestren necesidades de contexto omitidas.
