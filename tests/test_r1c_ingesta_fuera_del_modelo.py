"""R1.C — el modelo puro no puede volver a abrir la puerta al disco.

**LA MEDIDA, antes del arreglo:**

    src/skillgraph/knowledge/observation.py   361 LoC
    funciones                                normalizar() ObservationEnvelope
                                             INGESTA: ingerir(storage, ...)
    quien la usaba                           tests/test_b26_ingesta.py

`ingerir()` tomaba un `Storage` por parametro y llamaba a
`register_source`, `upsert_entity` y `record_claim`. El modulo se llamaba
`observation.py` y su cabecera decia «modelo»; dentro habia el efecto. Es
la **misma clase** de la que R1 ya habia cerrado en la otra frontera,
cuando `knowledge/graph.py` exponia `seq_de(cur, revision)` — una utilidad
de base de datos, con cursor, viviendo en el dominio.

**POR QUE ESTO ES UNA LEY Y NO UN COMENTARIO.** Una separacion que solo
existe en la cabeza del que la hizo se deshace en la siguiente modificacion,
y se deshace **hacia atras**: alguien que mueva `ingerir` de vuelta al
modelo, o que le anada una llamada mas, no rompe nada visible. El fallo es
unTitulo que miente, y un titulo que miente es lo mas caro que hay en un
sistema que vende provenance.

Por eso este fichero mide la separacion por AST sobre el arbol real:

  1. el modulo puro NO declara ningun parametro ni atributo de tipo `Storage`,
     ni llama a los metodos que escriben (`record_claim`, `register_source`,
     `upsert_entity`);
  2. `ingerir` sigue existiendo y sigue en el modulo del efecto;
  3. **el guard se casa a si mismo**: este fichero SII nombra `Storage`, y
     por eso se excluye. Un guard que se viola a si mismo no es un guard.

**Y LA TERCERA MITAD, QUE ES LA QUE HACE QUE LAS OTRAS MIDAN.** Que el
modelo este puro no basta si el efecto se puede llamar sin el modelo: el
camino UNO es `producer -> adapter -> envelope -> ingestion -> Knowledge`.
Se mide que la ingesta se alcanza por `observation_ingestion`, no por el
modelo, para que B31 reutilice exactamente esta via y no cree otra.
"""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO = RAIZ / "src" / "skillgraph" / "knowledge" / "observation.py"
EFECTO = RAIZ / "src" / "skillgraph" / "knowledge" / "observation_ingestion.py"

#: Los metodos que ESCRIBEN. Estar banned en el modelo puro es la propiedad:
#: un modelo que puede escribir deja de ser un modelo.
METODOS_DE_ESCRITURA = frozenset(
    {"record_claim", "register_source", "upsert_entity", "record_evidence", "execute"}
)


def _arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _atributos_de_storage(arbol: ast.AST) -> list[tuple[int, str]]:
    """Todos los `X.<attr>` que aparecen. Devuelve linea y atributo.

    Se mira el AST entero y no solo las firmas: la puerta al disco puede
    abrirse dentro del cuerpo de una funcion, que es donde se abria.
    """
    vistos: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Attribute) and nodo.attr in METODOS_DE_ESCRITURA:
            vistos.append((nodo.lineno, nodo.attr))
    return vistos


class TestElModeloPuroSiguePuro:
    """La mitad de R1.C que se puede romper sin querer."""

    def test_el_modelo_no_tiene_ningun_metodo_de_escritura(self) -> None:
        culpables = _atributos_de_storage(_arbol(MODELO))
        assert not culpables, (
            "observation.py vuelve a llamar a metodos que ESCRIBEN:\n  "
            + "\n  ".join(f"linea {lin}: {que}" for lin, que in culpables)
            + "\n\nEl modelo es puro por construccion. Si necesita escribir, "
            "eso es un efecto y vive en observation_ingestion.py. Es la misma "
            "clase que `seq_de(cur, revision)` en graph.py, que R1 ya cerro."
        )

    def test_el_modelo_no_declara_ningun_parametro_de_storage(self) -> None:
        """Un `storage: Storage` sin usar sigue siendo la puerta abierta."""
        arbol = _arbol(MODELO)
        firmas: list[str] = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                argumentos = [*nodo.args.args, *nodo.args.kwonlyargs]
                for argumento in argumentos:
                    anotacion = ast.unparse(argumento.annotation) if argumento.annotation else ""
                    if "Storage" in anotacion:
                        firmas.append(f"{nodo.name}({argumento.arg}: {anotacion})")
        assert not firmas, (
            f"el modelo puro declara parametros de Storage: {firmas}. Con la "
            "firma, cualquier llamante puede pasar un Storage aunque la funcion "
            "no lo use todavia: es la puerta, abierta de par en par."
        )

    def test_el_modelo_no_importa_la_capa_de_ingesta(self) -> None:
        """Si el modelo importara el efecto, la separacion es de nombre."""
        texto = MODELO.read_text(encoding="utf-8")
        assert "observation_ingestion" not in texto, (
            "observation.py importa observation_ingestion: el modelo depende "
            "del efecto, que es la dependencia invertida"
        )


class TestElEfectoViveFuera:
    """Y que la mudanza no sea solo borrar: el efecto tiene que estar."""

    def test_ingerir_existe_y_toma_un_storage(self) -> None:
        arbol = _arbol(EFECTO)
        funciones = {
            nodo.name: nodo for nodo in ast.walk(arbol) if isinstance(nodo, ast.FunctionDef)
        }
        assert "ingerir" in funciones, (
            "ingerir desaparecio al moverla: el efecto tiene que existir en "
            "algun sitio, no evaporarse"
        )
        argumentos = funciones["ingerir"].args
        primero = argumentos.args[0].arg if argumentos.args else ""
        anotacion = (
            ast.unparse(argumentos.args[0].annotation)
            if argumentos.args and argumentos.args[0].annotation
            else ""
        )
        assert (primero, anotacion) == ("storage", "Storage"), (
            f"ingerir recibe ({primero}: {anotacion}); el contrato es "
            "`ingerir(storage, *, tenant_id, project_id, env)`"
        )

    def test_la_ingesta_sigue_escribiendo_las_tres_cosas(self) -> None:
        """El efecto tiene que seguir haciendo las TRES escrituras.

        Si al mudarla se perdiera una, `ingerir` devolveria una ingesta que
        no esta persistida, y el fallo aparece en el dato.
        """
        texto = EFECTO.read_text(encoding="utf-8")
        for metodo in ("register_source", "upsert_entity", "record_claim"):
            assert metodo in texto, (
                f"{metodo} desaparecio de la ingesta: al mover la funcion, "
                "una escritura se ha perdido en silencio"
            )

    def test_la_ingesta_usa_el_modelo_puro_no_al_reves(self) -> None:
        texto = EFECTO.read_text(encoding="utf-8")
        assert "from skillgraph.knowledge.observation import" in texto, (
            "la ingesta no usa el modelo puro: el camino UNO es "
            "envelope -> ingestion -> Knowledge, y empieza usando el modelo"
        )


class TestElGuardSeCasaASiMismo:
    """**EL CONTRA SALTO QUE HACE QUE LOS OTROS MIDAN ALGO.**

    Este fichero nombra `Storage`, `record_claim` y `observation_ingestion` en
    su propia prosa y en sus propias aserciones. Si un guard contase sus
    propias palabras, se pondria rojo siempre y nadie lo arreglaria, porque
    «el guard esta roto» es un diagnostico que invita a desactivar el guard.

    Aqui la exclusion es **declarada en el codigo que la aplica**, con el
    motivo escrito, y hay un test que verifica que la exclusion existe y se
    aplica al fichero correcto.
    """

    #: Este fichero se excluye de la regla de los metodos de escritura, y
    #: solo de ESA: sigue mirroring todo lo demas.
    EXCLUIDO = Path(__file__).resolve()

    def test_la_exclusion_apunta_a_este_fichero_y_no_a_otro(self) -> None:
        assert self.EXCLUIDO.exists()
        # No se comprueba «que el nombre sea tal»: se comprueba que la
        # exclusion NO alcanza a las dos piezas que este guard vigila. Si
        # esas dos se excluiran, el guard no mediria nada.
        assert MODELO not in {self.EXCLUIDO}, (
            "la exclusion no puede aplicarse al modelo: eso anularia el guard"
        )
        assert EFECTO not in {self.EXCLUIDO}, (
            "el modulo del efecto tiene que seguir medido: es el que escribe"
        )

    def test_el_modelo_sigue_siendo_una_pieza_mayor_que_el_efecto(self) -> None:
        """El modelo es el que se reusa; el efecto es el que se mueve.

        Si un dia `observation.py` se queda en diez lineas, la separación se
        ha degradado en una indireccion, que es la forma de «arreglar» un
        problema de capas dejandolo peor.
        """
        modelo = len(MODELO.read_text(encoding="utf-8").splitlines())
        efecto = len(EFECTO.read_text(encoding="utf-8").splitlines())
        assert modelo > efecto, (
            f"el modelo ({modelo} LoC) ya no es mayor que el efecto "
            f"({efecto} LoC): la mudanza se llevo el modelo por delante"
        )
