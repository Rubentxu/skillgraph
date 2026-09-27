# ADR-0008 — Aislamiento local por tenant y proyecto

Estado: aceptada como dirección de diseño.

## Contexto

La plataforma debe servir para varios proyectos
y dominios sin almacenar datos internos en ellos.

## Decisión

Guardar los datos de SkillGraph en directorios
de aplicación del usuario.

Utilizar bases centrales por tenant
y bases específicas por proyecto.

## Motivos

Separar conocimiento privado, ejecuciones
y definiciones reutilizables.

## Consecuencias

Las referencias entre ámbitos requieren
un resolver autorizado.

Un tenant lógico no constituye aislamiento
de seguridad frente al mismo usuario del SO.

## Revisit trigger

Revisar al introducir usuarios del sistema
diferentes que compartan recursos.
