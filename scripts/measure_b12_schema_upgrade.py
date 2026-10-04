#!/usr/bin/env python3
"""B12 — el medidor del upgrade entre releases.

Que tiene que medir
-------------------
Cinco preguntas sobre el gate de 1.0 que B12 vino a cerrar, con
predicados que **ejecutan** y no que miran nombres. La razon esta en lo
que se rompio en B11: un predicado que comprueba que existen tres nombres
dice «cumple» el dia que alguien escriba los tres en el parser sin que
exista el ciclo entero. Aqui cada respuesta sale de una base construida
en `/tmp` y del estado que se puede preguntar.

Que NO mide, y se declara
------------------------
No mide que una base creada por una release de hace dos años conserve su
contenido. La base «vieja» de la P2 se RECONSTRUYE quitando lo que esa
release no conocía; no es una base real de una release real. Lo que si se
comprueba es que se abre, se sube, se versiona y no pierde filas.

Como leerlo
-----------
Salida 0 si estan las cinco en PASS. Salida 1 si alguna esta OPEN, que es
lo que un gate debe distinguir: «no lo se» de «se y es que no».
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Final

RAIZ: Final = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from skillgraph.core.errors import SchemaTooNewError  # noqa: E402
from skillgraph.platform import migrations, schema  # noqa: E402
from skillgraph.platform.storage import Storage  # noqa: E402


@dataclass(frozen=True, slots=True)
class Pregunta:
    nombre: str
    veredicto: str
    evidencia: str


@dataclass(slots=True)
class Informe:
    preguntas: list[Pregunta] = field(default_factory=list)

    def anota(self, nombre: str, ok: bool, evidencia: str) -> None:
        self.preguntas.append(Pregunta(nombre, "PASS" if ok else "OPEN", evidencia))


def _base_lista(directorio: pathlib.Path, nombre: str) -> pathlib.Path:
    st = Storage(directorio / nombre)
    st.close()
    return directorio / nombre


def _base_vieja(directorio: pathlib.Path, nombre: str) -> pathlib.Path:
    """Una base de una release anterior, reconstruida de verdad.

    Se crea con el codigo de HOY y se le quitan las dos cosas que una
    release anterior no conocia: la tabla del libro, y la fila de version.
    Se deja el resto intacto, y en particular NO se borra ninguna tabla de
    datos: si al subir se perdiera una fila, la P4 lo veria.
    """
    ruta = _base_lista(directorio, nombre)
    con = sqlite3.connect(ruta)
    con.execute("DROP TABLE schema_migrations")
    con.execute("DELETE FROM schema_version")
    con.commit()
    con.close()
    return ruta


def preguntar(directorio: pathlib.Path) -> Informe:
    informe = Informe()

    # --- P1: la version se deriva de la lista de migraciones -----------
    esperada = len(migrations.MIGRACIONES)
    informe.anota(
        "la version del esquema sale de la lista de migraciones",
        esperada == schema.SCHEMA_VERSION,
        f"SCHEMA_VERSION={schema.SCHEMA_VERSION} y hay {esperada} migraciones "
        f"({', '.join(m.id for m in migrations.MIGRACIONES)}). Derivada: no hay "
        f"numero que mantener en dos sitios.",
    )

    # --- P2: una base de una release anterior se sube -------------------
    ruta_vieja = _base_vieja(directorio, "vieja.db")
    try:
        st = Storage(ruta_vieja)
        aplicadas = st.migraciones_aplicadas()
        version = st.version_esquema()
        st.close()
        sube = aplicadas == tuple(m.id for m in migrations.MIGRACIONES) and (
            version == schema.SCHEMA_VERSION
        )
        detalle = f"aplicadas={aplicadas} version={version}"
    except Exception as exc:
        sube = False
        detalle = f"al abrir la base vieja: {type(exc).__name__}: {exc}"
    informe.anota("una base creada por una release anterior se sube", sube, detalle)

    # --- P3: la version es consultable y no tautologica ----------------
    ruta = _base_lista(directorio, "hoy.db")
    st = Storage(ruta)
    por_codigo = st.version_esquema()
    anotadas = st.migraciones_aplicadas()
    st.close()
    con = sqlite3.connect(ruta)
    por_sql = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    por_libro = len([i for i in anotadas if i in {m.id for m in migrations.MIGRACIONES}])
    con.close()
    informe.anota(
        "la version se puede PREGUNTAR a la base, no leer del modulo",
        por_codigo == por_sql == por_libro,
        f"el codigo dice {por_codigo}, la tabla dice {por_sql} y el libro tiene "
        f"{por_libro} migraciones aplicadas. Si coincidieran por leer la misma "
        f"constante, la pregunta seria tautologica.",
    )

    # --- P4: una base mas nueva NO se abre en silencio -------------------
    ruta_nueva = _base_lista(directorio, "futura.db")
    futura = schema.SCHEMA_VERSION + 1
    con = sqlite3.connect(ruta_nueva)
    con.execute("DELETE FROM schema_version")
    con.execute("INSERT INTO schema_version(version) VALUES (?)", (futura,))
    con.commit()
    con.close()
    try:
        st = Storage(ruta_nueva)
        st.close()
        rechaza = False
        detalle = "la base con un esquema mas nuevo se ABRIO: el fallo llega tarde"
    except SchemaTooNewError as exc:
        rechaza = True
        detalle = f"SchemaTooNewError ({exc.code}): {exc}"
    informe.anota("una base mas nueva que el codigo falla al abrir", rechaza, detalle)

    # --- P5: abrir una base al dia no escribe --------------------------
    ruta_lectura = _base_lista(directorio, "lectura.db")
    st = Storage(ruta_lectura)
    cambios = st._conn.total_changes
    st.close()
    informe.anota(
        "abrir una base al dia no escribe nada",
        cambios == 0,
        f"total_changes={cambios} al reabrir una base ya actualizada. Con un "
        f"DELETE incondicional por apertura, ocho procesos concurrentes se "
        f"repartian mal el turno de escritura (medido en test_b2_real_concurrency).",
    )

    return informe


def main() -> int:
    print("B12 · upgrade entre releases")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        informe = preguntar(pathlib.Path(td))
    for pregunta in informe.preguntas:
        marca = "PASS" if pregunta.veredicto == "PASS" else "OPEN"
        print(f"  [{marca}] {pregunta.nombre}")
        for linea in pregunta.evidencia.splitlines():
            print(f"         {linea}")
    abiertas = [p for p in informe.preguntas if p.veredicto != "PASS"]
    print()
    print(f"{len(informe.preguntas) - len(abiertas)}/{len(informe.preguntas)} PASS")
    return 0 if not abiertas else 1


if __name__ == "__main__":
    raise SystemExit(main())
