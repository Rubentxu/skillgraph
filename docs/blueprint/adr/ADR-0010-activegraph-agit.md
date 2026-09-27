# ADR-0010 — Integraciones externas como adaptadores

Estado: propuesta para validar.

## Contexto

ActiveGraph y agit contienen capacidades
que podrían aportar valor a SkillGraph.

## Decisión propuesta

No adoptar sus modelos completos como núcleo.

Probar ActiveGraph como proveedor de primitivas
de eventos y estado reactivo.

Considerar agit únicamente para trazabilidad
o recuperación opcional de sesiones.

## Motivos

SkillGraph necesita contratos propios de
bricks, handoffs, conocimiento y workflows.

## Consecuencias

Definir interfaces de adaptación.

Comparar prototipos antes de incorporar
dependencias permanentes.

## Revisit trigger

Revisar después de los spikes de integración
con evidencia de complejidad, compatibilidad
y recuperación.
