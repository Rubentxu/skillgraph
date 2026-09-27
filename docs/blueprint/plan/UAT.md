# User Acceptance Testing

Los UAT deben ejecutarse sobre una distribución
instalada y un directorio de datos aislado.

Las pruebas con FakeAgentAdapter se realizan antes
de introducir agentes reales.

## UAT-01 — Proyecto sin contaminación

Dado un repositorio limpio,
cuando se registra como proyecto,
entonces SkillGraph almacena sus datos internos
fuera de ese repositorio.

Comprobar que no aparecen archivos internos,
bases de datos ni índices nuevos dentro de él.

## UAT-02 — Aislamiento de proyectos

Dados dos proyectos del mismo tenant,
cuando se crea conocimiento privado en uno,
entonces el otro no puede recuperarlo mediante
una consulta ordinaria no autorizada.

## UAT-03 — Brick declarativo

Dado un Domain Pack Markdown válido,
cuando se registra,
entonces sus capacidades aparecen en el catálogo.

Un YAML inválido debe rechazarse antes de activar
el comportamiento.

## UAT-04 — Ejecución determinista

Dado un workflow con una decisión y una hoja,
cuando el agente simulado devuelve un outcome válido,
entonces el motor activa únicamente la transición
declarada y registra su resultado.

## UAT-05 — Handoff

Dado un nodo con ContextRecipe,
cuando se compila su handoff,
entonces contiene las entradas obligatorias,
las decisiones aplicables y el conocimiento vigente.

No debe contener información de otro proyecto
ni necesitar el historial completo.

## UAT-06 — Recuperación

Dada una ejecución interrumpida,
cuando se reinicia la CLI,
entonces se recuperan el estado y los resultados
confirmados y se continúa desde un punto seguro.

## UAT-07 — Idempotencia

Dado un evento entregado dos veces,
cuando el controlador lo procesa,
entonces no se duplica la acción ni el resultado.

## UAT-08 — Ampliación dinámica

Dada una problemática no contemplada,
cuando se propone un subgrafo válido y autorizado,
entonces se incorpora únicamente el cambio solicitado.

Los nodos completados mantienen sus revisiones
y resultados originales.

## UAT-09 — Ampliación no autorizada

Dada una propuesta que solicita nuevas capacidades,
cuando no existe autorización,
entonces el motor no incorpora la ampliación.

Debe conservarse evidencia de su rechazo
o de su estado de espera.

## UAT-10 — Invalidación de conocimiento

Dado un conjunto de afirmaciones vinculadas a fuentes,
cuando cambia una fuente relevante,
entonces se marcan las afirmaciones afectadas
y no se presentan como conocimiento vigente
sin revalidación.

## UAT-11 — Asimilación de skill

Dada una skill convencional,
cuando se importa,
entonces se conserva la fuente original
y se genera un informe de estructuración.

Las partes ambiguas deben permanecer señaladas;
no se presentan como decisiones verificadas.

## UAT-12 — Dominio especializado

Dado un Domain Pack narrativo,
cuando se registran Character y StoryArc,
entonces el proyecto puede crear y relacionar
instancias sin modificar el código del núcleo.

## UAT-13 — Promoción entre bases

Dada una propuesta de promoción persistida
en un proyecto,
cuando se interrumpe el proceso durante su publicación,
entonces la reconciliación permite completarla
sin duplicar la capacidad compartida.

## UAT-14 — Código de terceros

Dado un Domain Pack con un script Python,
cuando se importa y valida,
entonces el script no se ejecuta automáticamente.

## UAT-15 — Fuente maliciosa

Dada una fuente que contiene instrucciones
para alterar permisos o transiciones,
cuando un agente la consulta,
entonces esas instrucciones no se convierten
en autoridad sobre el workflow.

La comprobación debe incluir restricciones reales
del adaptador, no solamente instrucciones de prompt.

## UAT-16 — Estado histórico

Dada una nueva revisión de un brick,
cuando se inspecciona una ejecución anterior,
entonces se conserva la definición y el handoff
que produjeron su resultado.

## Evidencias obligatorias

Para cada UAT registrar:

- Identificador.
- Revisión de SkillGraph.
- Revisión del Domain Pack.
- Fixture o proyecto de prueba.
- Pasos ejecutados.
- Resultado esperado.
- Resultado observado.
- Logs y artefactos.
- Estado PASS/FAIL/BLOCKED.

No marcar PASS sin ejecutar el escenario.
