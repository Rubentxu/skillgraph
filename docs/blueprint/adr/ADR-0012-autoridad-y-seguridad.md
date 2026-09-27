# ADR-0012 — Autoridad sobre estado y capacidades

Estado: propuesta para validar.

## Contexto

Los agentes pueden descubrir problemáticas
y proponer modificaciones del workflow.

## Decisión propuesta

El núcleo conserva la autoridad sobre
transiciones, estado y permisos.

Los agentes devuelven resultados y propuestas
estructuradas.

Las modificaciones de capacidades o alcance
requieren autorización conforme a una política
explícita.

## Motivos

Evitar cambios implícitos del comportamiento,
escaladas de permisos y pérdida de trazabilidad.

## Consecuencias

Se necesita un adaptador que aplique realmente
las restricciones del entorno de ejecución.

Un prompt que declara permisos no constituye
por sí mismo una barrera técnica.

## Revisit trigger

Revisar al incorporar nuevos runtimes de agentes
con modelos de permisos diferentes.
