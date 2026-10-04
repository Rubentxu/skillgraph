"""Core bounded context of SkillGraph.

Pure types and errors that have no dependency on infrastructure,
storage, runtime, or any other bounded context. This is the rock
on which the rest of the codebase is built.

Modules in this subpackage:

- :mod:`skillgraph.core.errors` — Domain exception hierarchy.
- :mod:`skillgraph.core.runtime_types` — Closed ADTs (node kinds,
  run states, claim predicates, source kinds, finding results).
- :mod:`skillgraph.core.recipe` — ContextRecipe declaration and
  validation.

New code SHOULD import from :mod:`skillgraph.core` to make the
bounded context explicit. Legacy imports will be removed in a
future major version.

Por que este modulo declara ``__all__`` y lo que cuesta
---------------------------------------------------------
B9 midio, propiedad por propiedad, la condicion «resource/controller API
estable» y la dio **OPEN** con una razon concreta: este modulo no
declaraba ``__all__``. Un paquete sin superficie declarada no tiene
nada que pueda decir que es estable, por muy quieto que el arbol este.

La version anterior de este docstring decia que «cada modulo de aqui
tambien se reexporta desde su ubicacion de primer nivel» (``skillgraph.errors``
y eso). **Medido: es falso.** Ni `skillgraph.errors` ni `skillgraph.recipe`
ni `skillgraph.runtime_types` existen como modulos. Lo que si existe son
atributos reexportados a nivel de paquete desde ``skillgraph/__init__.py``, y
son **un subconjunto**: 20 nombres de 60. Asi que la frase no describia mal la
superficie, describia otra que no esta. Se borra en vez de arreglarse, porque
arreglarla seria fabricar un modulo de compatibilidad que nadie pidio y que
volveria a caducar.

La superficie se DECLARA, y se deriva
-------------------------------------
``__all__`` no esta escrito a mano: sale de unir el ``__all__`` de los tres
modulos, que si lo declaran. Si alguien anade un simbolo a
``skillgraph.core.errors.__all__`` y no lo reexporta aqui, el guard de
superficies se pone rojo nombrando el simbolo. Una lista escrita a mano
permitiria que la promesa del docstring —«el nucleo declara su superficie»—
fuese untrue sin que nada lo notase.

Los simbolos vienen del submodulo de origen, no de una copia local: reexportar
el objeto, no recrearlo, para que ``skillgraph.core.ValidationError is
skillgraph.core.errors.ValidationError`` sea cierto y el ``except`` que escribe
un consumidor y el que lanza el nucleo sean la misma clase.
"""

from skillgraph.core import errors as _errors, recipe as _recipe, runtime_types as _runtime_types

#: Los tres modulos del nucleo, en el orden en que se declara la superficie.
#: El orden no es estetico: fija el orden de aparicion en ``__all__``.
MODULOS: tuple[str, ...] = ("errors", "runtime_types", "recipe")

_por_modulo = {
    "errors": _errors,
    "runtime_types": _runtime_types,
    "recipe": _recipe,
}

#: La superficie publica del nucleo, derivada de la de cada modulo.
#:
#: No se escribe a mano porque la primera version si se escribia, y Medido:
#: las tres listas tienen 30, 26 y 4 nombres y no se solapan, luego la union
#: son 60. Copiarlos a mano seria 60 lineas que nadie vuelve a mirar y que
#: solo mienten.
SUPERFICIE: tuple[str, ...] = tuple(
    dict.fromkeys(
        nombre for modulo in (_errors, _runtime_types, _recipe) for nombre in modulo.__all__
    )
)

# Los simbolos se inyectan uno a uno porque `from ... import *` no se puede
# marcar como reexporto explicito sin `__all__` en el modulo de origen, y lo
# que se quiere es que ESTA lista sea la unica declaracion de superficie. La
# inyeccion por `globals()` es fea a proposito: hace imposible anadir un
# nombre aqui sin que salga de la union de los tres `__all__`.
for _nombre in SUPERFICIE:
    globals()[_nombre] = next(
        valor
        for _modulo in (_errors, _runtime_types, _recipe)
        if _nombre in _modulo.__all__
        for valor in (getattr(_modulo, _nombre),)
    )
del _nombre

__all__ = ["MODULOS", "SUPERFICIE", *SUPERFICIE]
