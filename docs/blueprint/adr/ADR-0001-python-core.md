# ADR-0001 — Núcleo determinista en Python

Estado: aceptada como dirección de diseño.

## Contexto

SkillGraph combina razonamiento agentico con
operaciones deterministas de validación y estado.

## Decisión

Python será el lenguaje del núcleo, la CLI,
los controladores y el SDK inicial.

Los agentes especializados realizarán el
razonamiento semántico y las acciones abiertas.

## Motivos

- Separación explícita de responsabilidades.
- Facilidad de crear adaptadores locales.
- Integración con SQLite.
- Compatibilidad con prototipos de ActiveGraph.
- Posibilidad de implementar una CLI pequeña.

## Consecuencias

No implementar un LLM como autoridad sobre
las transacciones del almacenamiento.

No obligar a los autores de Domain Packs
a escribir Python.

## Alternativas

Motor principalmente JavaScript.
Orquestador íntegramente basado en prompts.

## Revisión

Reabrir si un requisito concreto demuestra
que Python impide una capacidad esencial.
