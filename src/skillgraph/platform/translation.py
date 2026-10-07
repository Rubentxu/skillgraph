"""Traducción de errores del adapter a errores de DOMINIO.

# POR QUÉ ESTE MÓDULO EXISTE

`sqlite3.IntegrityError` es un tipo **del adapter**. El dominio no debería
nombrarlo ni capturarlo, y hasta R0 lo nomebraba: `knowledge_controller.py`
tenía `import sqlite3` y dos `except sqlite3.IntegrityError`, que es lo que
hacía que `grep sqlite3 knowledge/` diese positivo y la frontera fuera de
adorno.

La traducción va **en el borde**: el adapter captura lo que SQLite lanza y
levanta `IntegrityError` de `skillgraph.core.errors`. El dominio captura eso.

# POR QUÉ SOLO SE TRADUCE LA FK, Y EL RESTO SE PROPAGA INTACTO

Un `except Exception` + `"FOREIGN KEY" in str(exc)` reportaría como «no
existe la entidad» cualquier error cuyo mensaje **mencionara** esa frase: un
CHECK, un trigger, un error de dominio que la includa. WI-114 ya midió esa
clase de defecto y la regla es explícita: **el tipo se comprueba antes que el
texto, y lo que no se reconoce se propaga**.

# POR QUÉ NO ES UN `DECORADOR`

Podría serlo, y sería menos código. Un decorador sobre `record_claim` tendría
que adivinar que el error viene del `with` interno y no de la preparación de
los argumentos, y esa adivinanza es justo lo que este módulo existe para
evitar. Explícito se lee mejor que implícito cuando la frontera es el punto.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from skillgraph.core.errors import IntegrityError


@contextmanager
def traduciendo_integridad() -> Iterator[None]:
    """Traduce `sqlite3.IntegrityError` de FK a `IntegrityError` de dominio.

    Lo que **no** es FK se propaga intacto, y con él su traza.

    **POR QUÉ SOLO FK Y NO CUALQUIER INTEGRITY.** Un `UNIQUE` violado, un
    `CHECK` y una FK llegan todos como `IntegrityError`: SQLite no los
    distingue en el tipo. Traducirlos todos a un único error de dominio
    perdería el motivo, y quien lo viera no podría saber si reintentar
    sirve. La FK es la que tiene una respuesta de dominio clara —«la entidad o
    la fuente no existen»— y la que los llamadores ya saben interpretar.
    """
    try:
        yield
    except sqlite3.IntegrityError as exc:
        if "FOREIGN KEY" not in str(exc):
            raise
        raise IntegrityError(str(exc)) from exc


__all__ = ["traduciendo_integridad"]
