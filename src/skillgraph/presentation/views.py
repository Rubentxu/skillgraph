"""Vistas operacionales: lo que un operador ve, y lo que una maquina lee.

POR QUE ESTE MODULO EXISTE, y por que va DEBAJO de la TUI
---------------------------------------------------------
El objetivo de B7 es literal: «La UX que importa no es conversar con
SkillGraph, es **entender que esta haciendo el sistema y gobernarlo**». Y
el gate nombra diez widgets vivos —Graph, Timeline, Evidence, Decisions,
Resources, Diff, Runs, Policies, Capabilities, Knowledge— que escalan de
summary card a panel a full-screen, «sobre **las mismas APIs y query
models**».

La palabra cargada es «las mismas». Medido antes de escribir nada
(`scripts/measure_b7_operational_ux.py`): cero declaraciones de `--format`
en los siete modulos de comando, y ningun simbolo en todo `src/` que
exponga render. Hoy cada comando imprime cadenas formateadas a mano, luego
cualquier consumidor que no sea una persona tiene que **parsear columnas**.

Y una TUI construida sobre eso no comparte API con la CLI: la duplica. Dos
superficies que construyen la misma fila por su cuenta dicen cosas
distintas en el primer cambio, y ese es el modo tipico de que un gate
deje de ser cierto sin que nadie lo note.

Aqui vive la pieza de la que las dos dependen. Cada vista:

  - es un `frozen=True, slots=True` (AGENTS 1.1), porque una vista que se
    puede mutar mientras se pinta no es una vista;
  - tiene `to_json()`, que devuelve un `dict` estable y ordenado, porque
    el contrato con una maquina no es «una cadena bonita»;
  - tiene `to_text()`, que devuelve texto para una persona, porque la
    CLI **sigue siendo primera clase** y no se degrada a JSON.

Y hay una regla que este modulo hace cumplir y que es la que de verdad
cierra el gate: **una vista no lee disco**. Se construye desde lo que el
dominio ya devolvio. Si una vista abriera la base, dejaria de ser una
vista y passaria a ser una segunda via de consulta —que es exactamente el
duplicado que este bloque existe para evitar—, y dos vias de consulta
divergen la primera vez que el dominio cambia.

QUE NO HACE
-----------
No dibuja. No sabe de terminales, de ancho de columna, de colores ni de
teclas. Eso es de la TUI, y P4 —que la TUI sea usable de verdad— queda
FUERA de alcance de B7: depende de un terminal y de alguien usandola.
Lo que se mide aqui es la pieza de la que la TUI depende, que es
comprobable sin humano.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from skillgraph.core.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class Column:
    """Una columna de una vista tabular: su nombre y su encabezado humano.

    Se declara UNA vez por vista y la usan las dos superficies. Hoy el
    ancho de columna esta escrito dentro de cada `print(f"{x:<40}")`, y
    por eso la salida de la CLI no la puede reutilizar nadie: el ancho es
    parte del `print`, no del dato.
    """

    key: str
    header: str
    width: int = 0
    """0 significa «sin ancho fijo»: lo calcula el que presenta.

    Un ancho fijo en el dato obligaria a la TUI a respetar el ancho que
    eligio la CLI, que es al reves de como funcionan las dos superficies.
    """

    def cell(self, fila: dict[str, Any]) -> str:
        valor = fila.get(self.key, "")
        if isinstance(valor, (tuple, list)):
            valor = ",".join(str(v) for v in valor) or "-"
        elif valor is None or valor == "":
            valor = "-"
        texto = str(valor)
        if self.width:
            return texto.ljust(self.width)[: self.width]
        return texto


@dataclass(frozen=True, slots=True)
class TableView:
    """Una vista tabular: filas + columnas, con las dos representaciones.

    Es la primitiva de la que salen los diez widgets. Un `Diff` y una lista
    de `Resources` se diferencian en las columnas, no en el mecanismo de
    leerlos — y por eso el mecanismo se escribe una vez.
    """

    kind: str
    """El nombre del widget. Se serializa para que un consumidor pueda
    distinguir DOS superficies que devuelven la misma forma."""

    columns: tuple[Column, ...]
    rows: tuple[dict[str, Any], ...] = ()

    @property
    def total(self) -> int:
        return len(self.rows)

    def to_json(self) -> dict[str, Any]:
        """El contrato con una maquina: estable y ordenado.

        `sort_keys=True` NO es cosmetico. Sin el, dos procesos pueden
        serializar el mismo dict en orden distinto segun como se inserto,
        y un consumidor que compare digests ve una diferencia que no
        existe —la M5 de B5, que era la misma clase de fallo.
        """
        return {
            "kind": self.kind,
            "total": self.total,
            "columns": [{"key": c.key, "header": c.header} for c in self.columns],
            # Se ordena por CLAVE con `sorted(fila)`, no con
            # `sorted(fila.items())`. La segunda forma compara tambien los
            # VALORES cuando dos claves se empatan, y un valor puede no
            # ser comparable con otro —una tupla de listas contra una
            # lista de cadenas— y entonces `to_json` revienta con
            # `AttributeError` en vez de devolver la vista. MEDIDO al
            # escribir el primer test de estabilidad: una fila con
            # `executed=("a",)` y `events=1` no se serializaba.
            "rows": [{k: _serializable(fila[k]) for k in sorted(fila)} for fila in self.rows],
        }

    def to_json_text(self) -> str:
        return json.dumps(self.to_json(), indent=2, sort_keys=True, default=str)

    def to_text(self, *, vacio: str = "(sin resultados)") -> str:
        """La representacion para una persona: la que la CLI ya necesita.

        El ancho se calcula del contenido y no se escribe en el dato, que
        es lo que permite que esta misma vista sirva a un terminal de 80
        columnas y a uno de 200 sin que nadie edite la vista.
        """
        if not self.rows:
            return vacio
        anchos = {
            c.key: max(
                len(c.header),
                *(len(c.cell(fila)) for fila in self.rows),
            )
            for c in self.columns
        }
        lineas = [" ".join(c.header.ljust(anchos[c.key]) for c in self.columns)]
        for fila in self.rows:
            partes = []
            for c in self.columns:
                texto = c.cell(fila)
                partes.append(texto.ljust(anchos[c.key]))
            lineas.append(" ".join(partes).rstrip())
        return "\n".join(lineas)

    def find(self, key: str, value: object) -> TableView:
        """Una vista de las filas que cumplen algo, con la MISMA forma.

        Que devuelva otra `TableView` y no una lista de dicts es lo que
        mantiene la forma estable cuando se filtra: un consumidor que
        aprende a leer `kind` y `columns` no tiene que aprender una forma
        distinta para cada filtro.
        """
        return TableView(
            kind=self.kind,
            columns=self.columns,
            rows=tuple(f for f in self.rows if f.get(key) == value),
        )


@dataclass(frozen=True, slots=True)
class DetailView:
    """Una vista de un solo objeto: el «panel» del widget, no la tabla.

    Separada de `TableView` porque el gate pide que cada widget escale de
    summary card a panel a full-screen, y esa escala tiene TRES formas con
    el mismo origen: `to_text` para la tarjeta, `to_json` para el panel, y
    las dos leen los mismos campos.
    """

    kind: str
    title: str
    fields: tuple[tuple[str, Any], ...] = ()
    sections: tuple[tuple[str, tuple[TableView, ...]], ...] = field(default=())

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "fields": {k: _serializable(v) for k, v in self.fields},
            "sections": {nombre: [t.to_json() for t in tablas] for nombre, tablas in self.sections},
        }

    def to_json_text(self) -> str:
        return json.dumps(self.to_json(), indent=2, sort_keys=True, default=str)

    def field(self, name: str) -> Any:
        for clave, valor in self.fields:
            if clave == name:
                return valor
        raise NotFoundError(f"campo {name!r} no existe en la vista {self.kind!r}")

    def to_key_value(self) -> str:
        """La forma `clave=valor` que `runs show` prometia antes de B7.

        No es la MISMA que `to_text`, y no debe serlo. `runs show` tiene
        un contrato externo —`run_id=...`, `state=...`— que hay scripts
        fuera del repo que leen, asi que cambiarlo por una tabla bonita
        seria una ruptura silenciosa. Lo que hace B7 es AÑADIR una
        representacion mas, no sustituir la que ya habia: `to_text` para
        un panel legible, `to_key_value` para el contrato que ya existia,
        `to_json` para una maquina.

        Se conserva el guion de los valores ausentes (`-`) porque asi era,
        y porque es lo que un lector de esas lineas ya asume.

        Y un vacio se imprime aqui como `-` mientras que `to_json` lo
        devuelve como `[]`. No es una discrepancia que haya que arreglar:
        es la diferencia entre la representacion para una persona y la
        representacion para una maquina. Una lista vacia impresa como
        `[]` en una linea de texto es ruido, y un `-` en un JSON obliga al
        consumidor a adivinar si es «vacio» o «la cadena "-»». Cada
        superficie imprime el vacio en el idioma de la que se va a leer.
        Lo que NO puede diferir es el dato: los dos leen los mismos
        campos, que es lo que vigila
        `test_el_json_dice_lo_mismo_que_el_texto`.
        """
        return "\n".join(f"{clave}={_a_texto(valor)}" for clave, valor in self.fields)

    def to_text(self) -> str:
        if not self.fields and not self.sections:
            return f"{self.title}\n(vacio)"
        lineas = [self.title]
        ancho = max((len(k) for k, _ in self.fields), default=0)
        for clave, valor in self.fields:
            lineas.append(f"  {clave.ljust(ancho)}  {_a_texto(valor)}")
        for nombre, tablas in self.sections:
            if not tablas:
                continue
            lineas.append("")
            lineas.append(f"{nombre}:")
            for tabla in tablas:
                lineas.append(tabla.to_text())
                lineas.append("")
        return "\n".join(lineas).rstrip()


def _serializable(valor: Any) -> Any:
    """Convierte a algo que `json.dumps` acepta, sin perder informacion.

    Se usa `default=str` en el `dumps` como red de seguridad, pero aqui se
    hace explicito porque la diferencia se ve: una tupla de listas y una
    lista de tuplas son la MISMA vista y no pueden dar dos JSON distintos.
    """
    if isinstance(valor, (tuple, list)):
        return [_serializable(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _serializable(v) for k, v in sorted(valor.items())}
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def _a_texto(valor: Any) -> str:
    if isinstance(valor, (tuple, list)):
        return ",".join(_a_texto(v) for v in valor) or "-"
    if valor is None:
        return "-"
    if isinstance(valor, dict):
        return "{" + ", ".join(f"{k}={_a_texto(v)}" for k, v in valor.items()) + "}"
    return str(valor)
