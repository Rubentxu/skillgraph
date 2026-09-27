# Persistencia local, SQLite y aislamiento

## 1. Decisión inicial propuesta

Utilizar SQLite convencional y relaciones tipadas
como primer backend de almacenamiento.

No introducir inicialmente una extensión de grafos.

La decisión se revisará después de medir consultas
reales sobre dependencias y conocimiento.

## 2. Ámbitos

Usuario del sistema operativo
  -> Tenant lógico
      -> Proyecto
          -> Workspace
          -> Ejecuciones

Un tenant lógico dentro de una misma cuenta
no constituye por sí solo aislamiento de seguridad
frente a procesos con permisos de esa cuenta.

## 3. Directorios

Utilizar directorios de datos de aplicación propios
de cada sistema operativo.

Ejemplo conceptual:

```text
skillgraph/
  catalog.sqlite
  tenants/
    tenant-a/
      tenant.sqlite
      library/
      projects/
        project-001/
          project.sqlite
          artifacts/
          runs/
```

La ubicación se resuelve mediante una abstracción
de rutas del sistema operativo.

No escribir bases de datos, índices ni archivos
internos de SkillGraph en los repositorios fuente.

## 4. Responsabilidades de las bases

### Catálogo local

Identidad y localización de tenants.

### Base del tenant

Domain Packs compartidos, tipos, capacidades,
políticas y referencias a proyectos.

### Base del proyecto

Conocimiento, relaciones, ejecuciones, eventos,
handoffs, resultados y evidencias del proyecto.

## 5. Esquema inicial orientativo

```sql
CREATE TABLE resources (
  uid TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  project_id TEXT,
  kind TEXT NOT NULL,
  namespace TEXT NOT NULL,
  name TEXT NOT NULL,
  resource_version INTEGER NOT NULL,
  generation INTEGER NOT NULL,
  spec_json TEXT NOT NULL,
  status_json TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX resource_identity
ON resources (
  tenant_id,
  project_id,
  kind,
  namespace,
  name
);

CREATE TABLE resource_revisions (
  uid TEXT NOT NULL,
  revision INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(uid, revision)
);

CREATE TABLE relations (
  uid TEXT PRIMARY KEY,
  source_uid TEXT NOT NULL,
  target_uid TEXT NOT NULL,
  kind TEXT NOT NULL,
  properties_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX relations_by_source
ON relations(source_uid, kind);

CREATE INDEX relations_by_target
ON relations(target_uid, kind);

CREATE TABLE events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  resource_uid TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  causation_id TEXT,
  correlation_id TEXT
);

CREATE TABLE operations (
  operation_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  resource_uid TEXT NOT NULL,
  phase TEXT NOT NULL,
  result_ref TEXT
);
```

Es un esquema de arranque, no una migración SQL
completa lista para producción.

Las claves foráneas, restricciones de ámbito,
transacciones y tablas especializadas se concretarán
durante el spike de persistencia.

## 6. Grafo

Los recursos son vértices.

Las relaciones tipadas son aristas.

Las consultas recursivas permiten recorrer dependencias.

Las consultas frecuentes pueden utilizar índices
o proyecciones especializadas.

No usar JSON arbitrario como sustituto de esquemas
validados de dominio.

## 7. WAL

WAL permite lectores concurrentes y un escritor.

Las transacciones deben ser breves.

No asumir funcionamiento correcto de WAL sobre
sistemas de archivos de red.

## 8. Varias bases

Una transacción que actualiza varias bases adjuntas
no ofrece atomicidad global frente a fallos del host
cuando se utiliza WAL.

La promoción de conocimiento desde un proyecto
a un catálogo compartido utilizará:

1. Resultado persistido en la base origen.
2. Mensaje de outbox.
3. Aplicación idempotente en la base destino.
4. Confirmación de la operación.
5. Reconciliación si se interrumpe el proceso.

## 9. Aislamiento

No permitir referencias implícitas a otros tenants.

Las referencias entre ámbitos deben pasar por
un resolver autorizado.

Los controladores y agentes no reciben conexiones
directas a bases de datos arbitrarias.

## 10. Evolución

El backend debe exponerse mediante interfaces
de repositorio y almacenamiento.

La lógica de dominio no debe depender directamente
del SQL utilizado.

Una extensión de grafos se introducirá solamente
cuando un benchmark representativo demuestre
una necesidad que SQLite convencional no resuelve
adecuadamente.
