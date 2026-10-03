"""Superficie de presentacion de SkillGraph: lo que un operador ve.

Este paquete existe para que la CLI y la TUI **compartan** la forma de
leer el sistema, en vez de reimplementarla cada una. La justificacion
completa, el criterio de terminacion del bloque y lo que queda fuera de
alcance estan en `views.py`, que es donde vive la primitiva.

Se expone aqui lo que un consumidor necesita, y nada mas:

    from skillgraph.presentation import TableView, Column, DetailView

Lo que NO se expone, a proposito: nada que abra disco. Una vista se
construye desde lo que el dominio ya devolvio, y una vista que abriera la
base seria una segunda via de consulta — que es el duplicado que este
bloque existe para evitar.
"""

from __future__ import annotations

from skillgraph.presentation.views import Column, DetailView, TableView

__all__ = [
    "Column",
    "DetailView",
    "TableView",
]
