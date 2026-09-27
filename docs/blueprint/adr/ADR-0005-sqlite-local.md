# ADR-0005 — SQLite como almacenamiento inicial

Estado: propuesta para validar mediante spike.

## Contexto

Se necesita persistencia local, relaciones,
ejecuciones recuperables y aislamiento multiproyecto.

## Decisión propuesta

Utilizar SQLite convencional como primer backend.

Separar bases de tenant y proyecto.

Mantener una interfaz de almacenamiento independiente
de consultas SQL concretas.

## Motivos

Simplicidad operativa y ausencia de servidor.

Soporte de índices, consultas relacionales
y recorridos recursivos.

## Consecuencias

WAL no aporta transacciones atómicas globales
entre múltiples bases adjuntas ante fallos del host.

Las promociones entre bases requieren outbox
y operaciones idempotentes.

## Alternativas

Extensión de grafos para SQLite.
Almacén externo especializado.
Backend de persistencia de ActiveGraph.

## Revisit trigger

Introducir otro backend cuando las consultas
reales o los requisitos de concurrencia
demuestren una limitación significativa.
