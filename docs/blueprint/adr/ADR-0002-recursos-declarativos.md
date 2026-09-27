# ADR-0002 — Bricks como recursos declarativos

Estado: aceptada como dirección de diseño.

## Contexto

Las skills monolíticas mezclan reglas,
procedimientos, contexto y decisiones.

## Decisión

Utilizar bricks declarativos inspirados en
los recursos personalizados de Kubernetes.

Separar:

- Definiciones de tipos.
- Instancias de recursos.
- Controladores.
- Estado deseado.
- Estado observado.
- Ejecuciones concretas.

## Motivos

Facilitar extensión, composición, trazabilidad
y validación por una capa determinista.

## Consecuencias

Los contratos estructurales serán fijos.

Los tipos especializados podrán registrarse
mediante Domain Packs.

La analogía con Kubernetes no implica utilizar
Kubernetes ni reproducir su infraestructura.

## Revisión

Reabrir si la distinción entre tipo, recurso
y ejecución introduce duplicación injustificada.
