"""B9 — dejar la base en WAL sin pedir un lock que no hace falta.

Por que este modulo existe
--------------------------
`Storage.__init__` ejecutaba `PRAGMA journal_mode = WAL` en cada apertura.
El PRAGMA es idempotente —si la base ya esta en WAL, no cambia nada— pero
**toma un lock de escritura para averiguar que no hace nada**. Con ocho
procesos abriendo la misma base a la vez, uno moria con `database is
locked` ANTES de escribir una sola fila, y sus escrituras se perdian sin
excepcion en el padre y sin log: el run «funcionaba» y solo le faltaba un
evento.

B2 lo arreglo con un reintento. Y el reintento no bastaba. MEDIDO en B9,
con ocho procesos sueltos a la vez desde una puerta comun:

    1 de 12 corridas, con 3 de 8 hijos muertos y 50 de 80 filas escritas.

Dos intentos pegados caen en la misma ventana que el primero. El
`busy_timeout` del `connect` no ayuda, porque `journal_mode` **no lo
honra**: devuelve `SQLITE_BUSY` de inmediato, y esperar es cosa nuestra y
no del driver.

Las tres partes del arreglo
--------------------------
1. **Preguntar antes de cambiar.** `PRAGMA journal_mode` sin `= WAL` es
   una LECTURA, y una lectura no pide el lock exclusivo. Una base ya en
   WAL —el caso normal, y el unico que importa con concurrencia— no toca
   el lock de escritura ni una vez.
2. **Releer entre reintentos**, para que el que pierde el cambio se salga
   en vez de seguir peleando contra un modo que otro ya cambio.
3. **Dormir entre reintentos**, que es lo que deja ganar a alguien. Sin
   esto los tres intentos caian en el mismo instante, antes de que el
   ganador terminase su conversion.

Por que vive aqui y no en `storage.py`
--------------------------------------
Por el umbral de tamano: `storage.py` esta por debajo de las 800 lineas
por un guard de WI-65, y anadirle este arreglo lo rompia. Pero la razon de
fondo es que la logica no es de la fachada: `Storage` es una fachada que
delega, y esto es una politica de la base, con su propia politica de
reintento y sus propias constantes. Que sea una funcion que recibe la
conexion, y no un metodo, es lo que la hace comprobable sin abrir una base.

Lo que NO hace
--------------
No se traga el error. Si los intentos se agotan, la excepcion sube:
seguir como si la base estuviera en WAL sin haberlo comprobado seria
mentir sobre el modo con el que se esta escribiendo, que es la clase de
mentira que este bloque mide.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Final

#: Intentos antes de dejar que el error suba. Tres, y no dos, porque la
#: rafaga que lo dispara son ocho procesos abriendo a la vez: MEDIDO, con
#: dos intentos el segundo caia en la misma ventana que el primero y 3 de 8
#: hijos morian.
INTENTOS_WAL: Final[int] = 3

#: Espera base entre intentos, en segundos. El reintento se dobla: 10 ms y
#: luego 20 ms. MEDIDO: con los intentos pegados, sin dormir, el fallo
#: seguia saliendo.
#:
#: El total posible es de 30 ms, y solo se paga cuando la base hay que
#: crearla o sacarla de `delete`. Para quien abre una base que ya existe —
#: el caso normal, y el unico que importa con concurrencia— el modo se lee
#: y ya esta en WAL, luego no se llega aqui: cero espera.
ESPERA_ENTRE_INTENTOS_S: Final[float] = 0.01


def modo_de_journal(conexion: sqlite3.Connection) -> str:
    """El modo de journal actual, en minusculas. Una LECTURA, no un cambio.

    Leerlo no pide el lock exclusivo que el cambio si pide, y esa es toda
    la diferencia entre esta llamada y la que rompia ocho procesos a la vez.
    """
    fila = conexion.execute("PRAGMA journal_mode").fetchone()
    return str(fila[0]).lower() if fila is not None else ""


def asegura_wal(
    conexion: sqlite3.Connection,
    intentos: int = INTENTOS_WAL,
    espera_s: float = ESPERA_ENTRE_INTENTOS_S,
) -> None:
    """Deja la base en WAL, y solo pregunta si hay que cambiarla.

    Tres caminos, y el orden importa:

    1. Ya esta en WAL: se sale sin haber tocado un lock de escritura.
    2. Hay que cambiarlo y se cambia: se sale.
    3. Hay que cambiarlo y otro proceso esta cambiando el modo ahora
       mismo: se espera, se relee y se reintenta, con lo que el que pierde
       se sale en cuanto ve que otro gano.

    Los dos ultimos parametros existen para que un test pueda fijar la
    politica sin tocar las constantes del modulo. No son configuracion de
    producto: son el punto de inyectar un valor que haga la rama de fallo
    alcanzable en una prueba.
    """
    for intento in range(intentos):
        if modo_de_journal(conexion) == "wal":
            return
        try:
            conexion.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError:
            if intento + 1 < intentos:
                time.sleep(espera_s * (2**intento))
    # Ultimo intento sin proteccion: si falla, la excepcion sube. Prefiero un
    # fallo visible a una base en `delete` que nadie sabe que esta en `delete`.
    conexion.execute("PRAGMA journal_mode = WAL")
