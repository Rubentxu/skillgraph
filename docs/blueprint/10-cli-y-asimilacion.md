# CLI, Domain Packs y asimilación de skills

## 1. CLI

La CLI es la interfaz principal de la aplicación.

Debe permitir operaciones explícitas y ejecución
de capacidades declaradas por Domain Packs.

## 2. Comandos iniciales

```bash
skillgraph init

skillgraph project create mi-proyecto

skillgraph source add /ruta/origen \
  --project mi-proyecto

skillgraph pack import /ruta/skill

skillgraph pack validate mi-pack

skillgraph pack assimilate mi-pack

skillgraph capability list \
  --project mi-proyecto

skillgraph run mi-pack:review \
  --project mi-proyecto

skillgraph run status <run-id>

skillgraph run resume <run-id>

skillgraph graph show <graph-ref>

skillgraph context preview <run-id> <node-ref>

skillgraph events <run-id>
```

Son contratos candidatos de CLI.

## 3. Comandos dinámicos

Un Domain Pack declara capacidades y entrypoints.

La CLI genera entradas dinámicas en el catálogo
sin crear un ejecutable Python por capacidad.

Los aliases son opcionales y se resuelven
dentro de un ámbito explícito.

Un paquete no puede sobrescribir comandos
reservados del núcleo.

## 4. Asimilación

IMPORT
-> ANALYZE
-> STRUCTURE
-> VALIDATE
-> REGISTER
-> ACTIVATE

La importación no ejecuta código del paquete.

## 5. Niveles de adopción

### Encapsulado

La skill original se conserva como comportamiento
ejecutable sujeto a un contrato externo.

### Parcialmente estructurado

Se extraen capacidades, decisiones y gates conocidos.

Las partes no comprendidas permanecen encapsuladas.

### Estructurado

Las decisiones, acciones, relaciones y contratos
relevantes están representados explícitamente.

## 6. Informe de fidelidad

Cada instrucción original debe clasificarse como:

- PRESERVED
- STRUCTURED
- TRANSFORMED
- PENDING
- UNSUPPORTED

El informe debe contener referencias a su fuente.

La validez del YAML no demuestra por sí sola
la equivalencia del comportamiento.

## 7. Activación progresiva

Una capacidad se activa cuando:

- Su contrato es válido.
- Sus dependencias están disponibles.
- Su ejecutor está configurado.
- Sus capacidades han sido autorizadas.
- No existen ambigüedades bloqueantes.

La presencia de scripts Python no implica
autorización automática para ejecutarlos.

## 8. Skill convencional como entrada

Una skill puede comenzar como un único brick
encapsulado y evolucionar hacia varios subgrafos.

No forzar la creación de decisiones artificiales
para transformar cada párrafo en un nodo.

## 9. Experimento inicial

Utilizar dos skills con características distintas:

- Una skill metodológica con decisiones y gates.
- Una skill con recursos y conocimiento incremental.

Comparar los contratos generados, la fidelidad
y las partes que necesitan revisión humana.
