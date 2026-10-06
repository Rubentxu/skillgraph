"""B24 — un proveedor local que habla la FORMA de la respuesta.

**Lo que esto es, y lo que no es.**

Es un servidor HTTP en `127.0.0.1` que responde con la forma exacta que
`_parse_anthropic_response` espera. Sirve para que el recorrido completo —de
`create_run` a la relectura del estado— se ejecute **sin credencial y sin
dinero**, y para que ese recorrido se pueda volver a ejecutar en cada cambio.

**NO es una certificacion del proveedor.** Un servidor local no es Anthropic.
Lo que se mide aqui es que las ocho fronteras del recorrido funcionan: que el
`Handoff` firmado llega al adapter, que lo que sale vuelve como `AgentResult`,
que la transicion persiste y que despues se puede releer. Lo unico que queda
por certificar fuera es «que el proveedor real conteste», y eso lo mide
`tests/test_uat_real_provider.py` con la credencial.

**POR QUE NO ES UN DOBLE DE CADA SALTO.** B2 existe para dejar de medir
capacidad existente con dobles. Si aqui el adapter fuera un doble, estariamos
certificando que el doble funciona. Lo que se ejercita aqui es el
`HttpAgentAdapter` de verdad, con su `httpx.Client` de verdad, su retry y su
parseo de verdad; lo unico que se sustituye es el otro extremo del cable.

**MEDIDO AL CONSTRUIRLO: `base_url` sustituye la URL ENTERA, no solo el
host.** `build_request` hace `url = self.config.base_url or _ANTHROPIC_URL`, asi
que apuntando a `http://127.0.0.1:PORT` la peticion llega a `/` y no a
`/v1/messages`. Este servidor acepta cualquier ruta por eso, y ningun test
mira la ruta: lo que se mide es que LLEGO una peticion construida por el
adapter de verdad.

**POR QUE NO SE USA CUANDO HAY CREDENCIAL.** Si `SG_UAT_REAL_PROVIDER=1`, este
servidor no se levanta: el recorrido va contra el proveedor real. Un camino,
dos endpoints, y el que se certifica es siempre el que dice el opt-in.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

#: Lo que devuelve. `_parse_anthropic_response` exige `content[0].text` no
#: vacio, y `_parse_llm_text_as_agent_result` espera JSON en ese texto: es el
#: mismo contrato que cumpliria un proveedor de verdad.
RESPUESTA_ANTHROPIC: dict[str, Any] = {
    "id": "msg_local",
    "type": "message",
    "role": "assistant",
    "model": "local",
    "content": [{"type": "text", "text": json.dumps({"outcome": "ok", "result": {"local": True}})}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


class _Handler(BaseHTTPRequestHandler):
    """Registra lo que le llego, para que el test pueda mirarlo."""

    #: Peticiones recibidas, como lista de `(ruta, body)`.
    peticiones: ClassVar[list[tuple[str, dict[str, Any]]]] = []
    #: Respuesta a devolver. Cambiable para probar 429/500/4xx.
    cuerpo: ClassVar[dict[str, Any]] = RESPUESTA_ANTHROPIC
    estado: ClassVar[int] = 200

    def do_POST(self) -> None:
        largo = int(self.headers.get("content-length", "0"))
        crudo = self.rfile.read(largo) if largo else b"{}"
        try:
            body = json.loads(crudo or b"{}")
        except json.JSONDecodeError:
            body = {}
        type(self).peticiones.append((self.path, body))
        salida = json.dumps(type(self).cuerpo).encode("utf-8")
        self.send_response(type(self).estado)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(salida)))
        self.end_headers()
        self.wfile.write(salida)

    def log_message(self, *_args: Any) -> None:
        """Silencio: el log del servidor ensucia la salida de pytest."""


@contextmanager
def proveedor_local(**config: Any) -> Iterator[str]:
    """Levanta el servidor y devuelve su URL base. Se apaga al salir."""
    _Handler.peticiones = []
    _Handler.cuerpo = RESPUESTA_ANTHROPIC
    _Handler.estado = 200
    for clave, valor in config.items():
        setattr(_Handler, clave, valor)

    servidor = HTTPServer(("127.0.0.1", 0), _Handler)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}"
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=5)
        _Handler.peticiones = []


def peticiones() -> list[tuple[str, dict[str, Any]]]:
    """Lo que el servidor recibio. Es la prueba de que hubo una llamada REAL."""
    return list(_Handler.peticiones)
