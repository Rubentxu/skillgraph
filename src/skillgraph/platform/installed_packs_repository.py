"""B11 — persistencia del REGISTRO de packs instalados.

Por que NO vive en `resources`
-----------------------------
MEDIDO antes de escribir esto: `upsert_resource` RECHAZA cambiar el `spec`
bajo la misma identidad, con `IdentityConflictError`. Es deliberado —un
recurso es inmutable, y cambiarlo es un conflicto, no una edicion—, pero
hace que `sg pack update` sea estructuralmente IMPOSIBLE si el registro
se apoya en esa tabla: la version nueva es un spec distinto bajo la misma
identidad, luego el storage la rechaza siempre, y el `update` del enunciado
no tendria donde escribir.

Una instalacion no es un recurso. El recurso es el CONTENIDO del pack; la
instalacion es el HECHO de que ese pack este vivo en este proyecto, y ese
hecho tiene su propio ciclo. Por eso tiene su propia tabla.

`retirar` no borra la fila: mueve `estado` a `retired`. Ver la cabecera de
`skillgraph.packaging.registry`, que explica por que un DELETE perderia la
unica respuesta que existe a «¿este proyecto ha tenido alguna vez este
pack?» —la fila borrada es la unica parte que la guardaba—.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from skillgraph.core.errors import ValidationError
from skillgraph.packaging.manifest import parse_manifest
from skillgraph.packaging.registry import (
    ESTADO_INSTALADO,
    ESTADO_RETIRADO,
    FilaDePack,
    RegistroDePacks,
)

if TYPE_CHECKING:  # pragma: no cover - solo para el type-checker
    from skillgraph.platform.storage import Storage


class SqliteInstalledPacksRepository:
    """El registro de packs instalados de un proyecto, sobre `installed_packs`.

    SQL aqui y no en el controlador: `Storage` encapsula el SQL (AGENTS.md 8)
    y este es el unico sitio que habla con la tabla.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    # --- lectura ---------------------------------------------------------

    def listar(
        self, *, tenant_id: str, project_id: str, solo_instalados: bool = True
    ) -> RegistroDePacks:
        """Las filas de ese proyecto, como un registro.

        El filtro de `tenant_id` y `project_id` va en el `WHERE` y no se
        relaja: un registro que enseñara packs de otro proyecto seria una
        fuga entre tenants, y el aislamiento por tenant es un contrato
        (ADR sobre multi-tenancy), no una preferencia.

        MEDIDO, y por que no se delega el filtro en el `kind` de otra
        consulta: `list_resources` lo construye como
        `AND api_version || '/' || kind = ? OR kind = ?`, SIN parentesis, y
        el `OR` se come el `AND` que lo precede. Un filtro que parece
        acotar y no acota es peor que no filtrar, porque ademas da la
        sensacion de que acota.
        """
        sql = "SELECT * FROM installed_packs WHERE tenant_id = ? AND project_id = ?"
        params: tuple[Any, ...] = (tenant_id, project_id)
        if solo_instalados:
            sql += " AND estado = ?"
            params = (*params, ESTADO_INSTALADO)
        sql += " ORDER BY name"
        filas = self._storage._conn.execute(sql, params).fetchall()
        return RegistroDePacks(tuple(_a_fila(f, tenant_id, project_id) for f in filas))

    # --- escritura -------------------------------------------------------

    def guardar(self, fila: FilaDePack, *, tenant_id: str, project_id: str) -> None:
        """Deja `fila` como la fila vigente de ese pack.

        `INSERT ... ON CONFLICT DO UPDATE` y no un `SELECT` seguido de un
        `INSERT` o un `UPDATE`: son dos escrituras en dos transacciones, y
        entre medias otra conexion podria insertar la misma fila. La
        constraint decide, que es lo que dice AGENTS.md 8 —la idempotencia
        va por constraint, no por codigo—.
        """
        self._storage._conn.execute(
            """
            INSERT INTO installed_packs
                (tenant_id, project_id, name, manifest_json, estado, uid, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(tenant_id, project_id, name) DO UPDATE SET
                manifest_json = excluded.manifest_json,
                estado = excluded.estado,
                uid = excluded.uid,
                updated_at = excluded.updated_at
            """,
            (
                tenant_id,
                project_id,
                fila.pack,
                json.dumps(fila.manifiesto.to_dict(), sort_keys=True),
                fila.estado,
                fila.uid,
            ),
        )
        self._storage._conn.commit()

    def marcar_retirado(self, *, tenant_id: str, project_id: str, name: str) -> int:
        """Mueve la fila a `retired`. Devuelve cuantas filas cambio.

        Que devuelva el numero de filas es lo que permite decir «no estaba
        instalado» con verdad en vez de con suposicion: un `UPDATE` que no
        cambia nada y un `UPDATE` que cambia una fila son indistinguibles si
        no se mira.
        """
        cur = self._storage._conn.execute(
            """
            UPDATE installed_packs SET estado = ?, updated_at = datetime('now')
            WHERE tenant_id = ? AND project_id = ? AND name = ? AND estado = ?
            """,
            (ESTADO_RETIRADO, tenant_id, project_id, name, ESTADO_INSTALADO),
        )
        self._storage._conn.commit()
        return cur.rowcount


def _a_fila(fila: Any, tenant_id: str, project_id: str) -> FilaDePack:
    """De una fila de la tabla a la fila del registro. Falla si el estado no es conocido."""
    try:
        manifiesto = parse_manifest(json.loads(fila["manifest_json"]))
    except (json.JSONDecodeError, KeyError, ValidationError) as exc:
        raise ValidationError(
            f"la instalacion de {fila['name']!r} tiene un manifiesto ilegible: {exc}"
        ) from exc
    estado = fila["estado"]
    if estado not in {ESTADO_INSTALADO, ESTADO_RETIRADO}:
        raise ValidationError(
            f"la instalacion de {fila['name']!r} tiene un estado desconocido: {estado!r}; "
            f"los dos que existen son {ESTADO_INSTALADO!r} y {ESTADO_RETIRADO!r}"
        )
    if fila["tenant_id"] != tenant_id or fila["project_id"] != project_id:
        # No deberia pasar con el WHERE de arriba, y por eso se comprueba:
        # una fila de otro proyecto que se colara aqui significaria que el
        # filtro no acota, y eso se quiere ver en un test, no en produccion.
        raise ValidationError(
            f"la instalacion de {fila['name']!r} dice ser de "
            f"{fila['tenant_id']}/{fila['project_id']} y se pidio "
            f"{tenant_id}/{project_id}: el filtro no esta acotando"
        )
    return FilaDePack(
        pack=manifiesto.name,
        estado=estado,
        manifiesto=manifiesto,
        uid=fila["uid"],
    )
