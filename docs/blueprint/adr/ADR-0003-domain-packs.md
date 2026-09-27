# ADR-0003 — Domain Packs declarativos

Estado: aceptada como dirección de diseño.

## Contexto

SkillGraph debe servir para software, escritura,
enseñanza y otros ámbitos.

## Decisión

Los Domain Packs se definen principalmente
mediante Markdown/YAML.

Pueden aportar tipos, relaciones, reglas,
comportamientos, subgrafos, recetas de contexto
y capacidades de CLI.

Python será opcional.

## Motivos

Mantener una experiencia de autoría tan sencilla
como crear una skill convencional.

Permitir profundidad semántica por dominio
sin modificar el núcleo.

## Consecuencias

El núcleo necesita un registro de tipos versionado.

La instalación no implica ejecutar extensiones.

Cada proyecto habilita explícitamente sus paquetes.

## Revisión

Reabrir si un caso representativo no puede
expresarse sin modificar repetidamente el núcleo.
