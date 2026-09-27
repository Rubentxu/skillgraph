# ADR-0011 — Controladores genéricos y extensiones opcionales

Estado: propuesta para validar.

## Contexto

Los Domain Packs necesitan comportamientos
reactivos sin obligar a escribir Python.

## Decisión propuesta

Implementar un conjunto mínimo de controladores
genéricos en el núcleo.

Permitir controladores declarativos con operadores
registrados y extensiones Python autorizadas.

## Motivos

Mantener facilidad de autoría y permitir
especialización cuando sea necesaria.

## Consecuencias

La validación de un paquete debe distinguir
declaraciones y código ejecutable.

Los controladores proponen operaciones;
el núcleo valida su aplicación.

## Revisit trigger

Introducir una nueva primitiva solamente cuando
un caso concreto no pueda resolverse mediante
composición de las existentes.
