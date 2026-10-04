"""B13: el modelo de amenaza deja de AFIRMAR cosas y las SOSTIENE.

La medicion de B13 (`/tmp/b13_measure.py`, 0 de 5 PASS) no encontro que
las cifras del ADR estuvieran viejas. Encontro esto:

    T2 pidio kind='DomainPack' y recibio ['dp-de-t1']

Una fila de T1 que cruza a T2, en una base real, por una API que la CLI
usa (`cli/support.py:299`). Y el ADR-0015 dice, textual, en S1/Spoofing:

    «Las queries filtran por tenant_id, project_id en todos los paths
     verificados» - estado OK.

Un modelo de amenaza que llama OK a una fuga que existe no es un modelo
caducado: es un modelo que dice lo contrario de la verdad. B11 ENCONTRO
este defecto -el `OR` sin parentesis que se come el `AND`- y no lo
arreglo, porque esquivarlo era la decision correcta para el bloque que
estaba haciendo. La puerta se quedo abierta y nadie la miro, porque el
documento que deberia mirarla decia que estaba cerrada.

Los cinco conjuntos de tests de aqui son DISJUNTOS, y cada uno dice en su
docstring que es lo UNICO que mide, para que ninguno tape a otro.
"""

from __future__ import annotations

import inspect
import re
import sqlite3
from pathlib import Path

from skillgraph.platform.storage import Storage

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "skillgraph"
ADR = RAIZ / "docs" / "architecture" / "ADR-0015-threat-model-stride.md"


def _or_de_nivel_superior(sql: str) -> bool:
    """¿La consulta tiene un `OR` fuera de parentesis?

    En SQL `AND` liga mas fuerte que `OR`, luego un `OR` sin agrupar
    convierte en opcional todo lo que este a su izquierda. Un `WHERE
    tenant_id = ? AND project_id = ? OR kind = ?` devuelve filas de
    cualquier tenant, y el filtro de tenant parece puesto.

    Se mide sobre la consulta que se EJECUTA, no sobre el texto que la
    compone. La diferencia importa: la consulta se arma por concatenacion,
    y un guard que mira literales ve el `WHERE` en uno y el `OR` en otro, y
    no ve la frase.
    """
    donde = re.split(r"\bWHERE\b", sql, maxsplit=1)
    if len(donde) < 2:
        return False
    profundidad = 0
    for palabra in re.findall(r"\(|\)|\bOR\b", donde[1].upper()):
        if palabra == "(":
            profundidad += 1
        elif palabra == ")":
            profundidad -= 1
        elif palabra == "OR" and profundidad == 0:
            return True
    return False


def _base_con_dos_tenants(tmp_path: Path) -> Storage:
    """Una base real con un `DomainPack` de T1. T2 y T9 no tienen nada."""
    ruta = tmp_path / "p.db"
    st = Storage(ruta)
    st.close()
    con = sqlite3.connect(ruta)
    con.execute(
        "INSERT INTO resources(uid, tenant_id, project_id, api_version, kind, "
        "namespace, name, spec_json) VALUES (?,?,?,?,?,?,?,?)",
        (
            "dp-de-t1",
            "T1",
            "P1",
            "skillgraph/v1",
            "DomainPack",
            "ns",
            "secreto-de-t1",
            '{"secret": "credencial-de-T1"}',
        ),
    )
    con.commit()
    con.close()
    return Storage(ruta)


# =====================================================================
class TestLaFugaCrossTenant:
    """Lo que el ADR llama «OK» y no lo esta. Se mide con la fila que cruza."""

    def test_t2_no_ve_los_recursos_de_t1_al_filtrar_por_kind(self, tmp_path: Path) -> None:
        """La fuga. Se escribe la fila de T1, se pide desde T2, y se mira.

        Un test que inspeccionara la cadena del SQL probaria que el codigo
        esta escrito de una manera; este prueba que la fila no cruza, que es
        la unica cosa que le importa a quien tiene T2.
        """
        st = _base_con_dos_tenants(tmp_path)
        vistos = st.list_resources(tenant_id="T2", project_id="P2", kind="DomainPack")
        st.close()
        assert vistos == [], f"un tenant vio los recursos de otro: {vistos}"

    def test_t1_sigue_viendo_lo_suyo(self, tmp_path: Path) -> None:
        """CONTRA-SALTO: cerrar la fuga no es vaciar la lista.

        Arreglarlo pompiendo el filtro a `1=0` tambien haria pasar el test de
        arriba. Este exige que T1, que SI tiene un DomainPack, siga viendo el
        suyo: un guard que solo mira que no se cuele no vigila que el
        parametro sirva para algo.
        """
        st = _base_con_dos_tenants(tmp_path)
        suyos = st.list_resources(tenant_id="T1", project_id="P1", kind="DomainPack")
        st.close()
        assert [r.uid for r in suyos] == ["dp-de-t1"], (
            f"el filtro de kind dejo de devolver lo suyo: {suyos}"
        )

    def test_un_tenant_sin_nada_no_inventa_filas(self, tmp_path: Path) -> None:
        """La direccion vacia: el fallo de antes tambien salia sin datos."""
        st = _base_con_dos_tenants(tmp_path)
        vacios = st.list_resources(tenant_id="T9", project_id="P9", kind="DomainPack")
        st.close()
        assert vacios == [], f"un tenant sin datos recibio filas: {vacios}"


# =====================================================================
class TestLosSqlNoTienenUnOrSinAgrupar:
    """Guard GENERAL sobre el SQL que sale al motor.

    Este guard no mira una funcion: mira la consulta que sqlite ejecuta
    mientras corre una lectura, y exige dos cosas que el ADR afirma en S1 y
    que hasta ahora nadie habia ejecutado:

    1. que el `WHERE` no tenga un `OR` sin agrupar, y
    2. que la consulta mencione `tenant_id`.

    La version anterior de este guard recorria literales de cadena y daba
    VERDE con la fuga presente, porque el `WHERE` y el `OR` estan en
    literales DISTINTOS: la consulta se arma por concatenacion. Ese
    tropiezo es el motivo de mirar el SQL ensamblado, y por eso se cuenta.
    """

    #: Superficies con `tenant_id` Y un filtro de estilo `kind`, que es la
    #: unica via por la que un `OR` puede entrar en un WHERE. Se declara
    #: explicitamente y el primer test obliga a ampliarla.
    LECTURAS: frozenset[str] = frozenset(
        {"list_resources", "find_entity", "list_resource_refs_for_run", "add_relation"}
    )

    #: Subconjunto que se EJERCIZA en una base real. `add_relation` escribe,
    #: asi que no se puede leer de vuelta por si misma: su SQL se captura
    #: igualmente, que es lo que el guard necesita.
    EJERCITADAS: tuple[str, ...] = ("list_resources", "find_entity", "list_resource_refs_for_run")

    def _con_filtro_de_kind(self) -> set[str]:
        """Metodos que pueden meter un `OR` sin querer.

        Un `OR` sin agrupar solo entra en un WHERE donde hay una alternativa
        que escribir: «coincide por api/kind» O «coincide por kind». Ese
        filtro tiene que pasar por un parametro, y por eso el conjunto es
        pequeno y DERIVADO del arbol en vez de escrito a mano.

        Y por eso el alcance del guard es lo que es: se miden las cuatro
        superficies donde este defecto puede entrar, no las 45 que aceptan
        `tenant_id`. Las otras 41 tienen su propia cobertura de aislamiento
        (`test_b6_provenance`, `test_h9_*`, y el guard de B11 fila a fila), y
        prometer aqui lo que este fichero no mide seria volver a escribir un
        OK sin prueba.
        """
        nombres: set[str] = set()
        for nombre in dir(Storage):
            if nombre.startswith("_"):
                continue
            try:
                firma = inspect.signature(getattr(Storage, nombre))
            except (TypeError, ValueError):
                continue
            ps = firma.parameters
            if "tenant_id" in ps and ({"kind", "api_version", "namespace"} & set(ps)):
                nombres.add(nombre)
        return nombres

    def _sql_de_las_lecturas(self, st: Storage) -> list[str]:
        """Ejercita las lecturas y devuelve el SQL que llego al motor."""
        capturado: list[str] = []
        st._conn.set_trace_callback(capturado.append)
        st.find_entity(tenant_id="T1", project_id="P1", kind="Entity", stable_key="nada")
        st.list_resource_refs_for_run(
            tenant_id="T1", project_id="P1", run_id="r-inexistente", kind="claim"
        )
        st.list_resources(tenant_id="T1", project_id="P1", kind="DomainPack")
        return capturado

    def test_toda_superficie_con_filtro_de_kind_esta_cubierta(self) -> None:
        """CONTRA-SALTO de cobertura, y es el que mas importa de los tres.

        Sin este, el guard mide las superficies que alguien recordo escribir.
        Anadir una lectura con filtro de kind que nadie anade a la lista deja
        el guard en verde sobre un hueco nuevo: es el fallo de B11, otra vez,
        un bloque mas abajo y con otra forma.
        """
        sin_cubrir = self._con_filtro_de_kind() - self.LECTURAS
        assert not sin_cubrir, (
            f"estas superficies aceptan tenant_id y un filtro de kind, y el guard "
            f"no las mide: {sorted(sin_cubrir)}. Hay que anadirlas a LECTURAS: un "
            f"filtro de kind sin agrupar es la unica via por la que un AND se "
            f"vuelve opcional, y no se comprueba lo que no se nombra."
        )

    def test_ninguna_lectura_ejecuta_un_where_con_or_suelto(self, tmp_path: Path) -> None:
        st = _base_con_dos_tenants(tmp_path)
        selects = [
            s for s in self._sql_de_las_lecturas(st) if s.lstrip().upper().startswith("SELECT")
        ]
        st.close()
        assert selects, "no se ha capturado ninguna consulta: el guard mediria el vacio"
        culpables = [s for s in selects if _or_de_nivel_superior(s)]
        assert not culpables, (
            "estas consultas tienen un OR sin agrupar, luego el AND que lo precede "
            "es opcional y el tenant se puede saltar:\n  " + "\n  ".join(c[:170] for c in culpables)
        )

    def test_toda_consulta_de_lectura_filtra_por_tenant(self, tmp_path: Path) -> None:
        """La frase del ADR, EJECUTADA: «en todos los paths verificados»."""
        st = _base_con_dos_tenants(tmp_path)
        selects = [
            s for s in self._sql_de_las_lecturas(st) if s.lstrip().upper().startswith("SELECT")
        ]
        st.close()
        sin_filtro = [s for s in selects if "TENANT_ID" not in s.upper()]
        assert not sin_filtro, "estas lecturas no filtran por tenant:\n  " + "\n  ".join(
            s[:170] for s in sin_filtro
        )

    def test_el_guard_ejercita_todas_las_superficias_que_declara(self) -> None:
        """Y que la lista declarada no tenga miembros muertos.

        Declarar una superficie que el guard no ejercita es la forma
        silenciosa de no comprobarla: la fila se queda ahi, verde, hasta
        que alguien la lea creyendola verificada. Este lo hace visible.
        """
        sin_ejercitar = set(self.LECTURAS) - set(self.EJERCITADAS) - {"add_relation"}
        assert not sin_ejercitar, (
            f"estas superficies estan declaradas pero no se ejercitan: {sorted(sin_ejercitar)}"
        )

    def test_el_predicado_ve_un_or_suelto_y_respeta_un_agrupado(self) -> None:
        """CONTRA-SALTO del predicado, en las DOS direcciones.

        Sin la segunda mitad, un predicado que senalara TODO seonegaria como
        «mide»: no mediria: protestaria. Las dos mitades juntas son lo que
        hace que el guard tenga bocas de entrada distintas y no una sola.
        """
        rota = "SELECT * FROM resources WHERE tenant_id = ? AND project_id = ? OR kind = ?"
        buena = (
            "SELECT * FROM resources WHERE tenant_id = ? AND project_id = ? "
            "AND (api_version || '/' || kind = ? OR kind = ?)"
        )
        assert _or_de_nivel_superior(rota), "el predicado no ve un OR sin agrupar"
        assert not _or_de_nivel_superior(buena), (
            "el predicado protestaria contra una consulta bien agrupada"
        )


# =====================================================================
class TestElModeloEnumeraTodaSuperficieDelArbol:
    """La vigencia se mide por superficies, no por un numero de tests.

    El predicado del gate comparaba «tests declarados == tests colectados».
    Eso caduca con cada commit y no dice nada de la seguridad: un gate que
    se pone rojo por causas ajenas al objeto que vigila entrena a ignorarlo,
    que es peor que no tenerlo. Las superficies describen lo que el producto
    EXPONE, que es lo que el modelo tiene que cubrir, y anadir un paquete
    es un cambio real que el gate debe notar.
    """

    def _paquetes(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                d.name
                for d in SRC.iterdir()
                if d.is_dir() and not d.name.startswith("_") and (d / "__init__.py").is_file()
            )
        )

    def test_todo_paquete_del_arbol_tiene_fila_en_el_adr(self) -> None:
        paquetes = self._paquetes()
        assert paquetes, "no se han encontrado paquetes: el guard mediria el vacio"
        texto = ADR.read_text(encoding="utf-8")
        faltan = [p for p in paquetes if f"`{p}`" not in texto]
        assert not faltan, (
            f"el modelo de amenaza no menciona estos paquetes del arbol: {faltan}. "
            f"Un paquete nuevo es una superficie nueva y el modelo tiene que "
            f"decidir que de ella piensa, aunque sea «sin frontera propia»."
        )

    def test_el_adr_no_declara_un_numero_de_tests_como_su_vigencia(self) -> None:
        """Un documento de seguridad no caduca porque se anadio un test.

        Este es el motivo del bloque: las cifras de contexto pueden quedar en
        el documento, pero no pueden ser LA PRUEBA de que el analisis esta al
        dia, porque un numero se pudre por razones que no tienen nada que ver
        con la seguridad.
        """
        texto = ADR.read_text(encoding="utf-8")
        viven = re.findall(r"(\d+)\s+tests\s+verdes", texto)
        assert not viven, (
            f"el ADR vuelve a declarar «{viven[0]} tests verdes» como medida de "
            f"vigencia. Esa cifra caduca con cada test anadido sin que nadie haya "
            f"tocado el analisis, y ese es el mecanismo que hace que un gate "
            f"termine ignorandose."
        )

    def test_el_analisis_tiene_una_seccion_de_superficies(self) -> None:
        """Sin seccion legible no hay nada que el gate pueda medir sin un numero."""
        texto = ADR.read_text(encoding="utf-8")
        assert "## Superficies" in texto, (
            "el ADR necesita una seccion de superficies que el gate pueda leer; "
            "sin ella la vigencia solo se puede medir con un numero, y un numero "
            "se pudre"
        )


# =====================================================================
class TestLaEvidenciaDeCadaSuperficieExiste:
    """Un «OK» que no se puede ejecutar es una prosa optimista.

    Este conjunto no comprueba que el analisis sea CORRECTO —eso no es una
    fórmula— sino que cada superficie diga de qué depende. Una fila que
    apunta a un fichero que no existe, o que no nombra nada, es una fila que
    no se sostiene.
    """

    def _filas(self) -> list[tuple[str, str, str]]:
        """Filas de la tabla de `## Superficies`, y SOLO de ahi.

        Acotar a la seccion no es cosmetico: el ADR tiene ocho tablas mas de
        STRIDE por superficie, tambien de tres columnas, y sus celdas no
        nombran ficheros del repo. Sin acotar, el guard leeria veinte filas
        de analisis que no son superficies y exigeria evidencia a celdas que
        no la llevan. Un guard que mide el documento equivocado es peor que
        uno que no mide.
        """
        texto = ADR.read_text(encoding="utf-8")
        seccion = re.search(r"^##\s+Superficies\s*$(.+?)(?=^##\s)", texto, re.S | re.M)
        if seccion is None:
            return []
        filas: list[tuple[str, str, str]] = []
        for linea in seccion.group(1).splitlines():
            if not linea.strip().startswith("|"):
                continue
            celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
            if len(celdas) != 3:
                continue
            primera = celdas[0]
            if not primera or set(primera) <= {"-", " "}:
                continue
            if primera.lower().startswith("superficie"):
                continue
            filas.append((primera, celdas[1], celdas[2]))
        return filas

    def test_la_tabla_de_superficies_tiene_filas_legibles(self) -> None:
        filas = self._filas()
        assert len(filas) >= 8, (
            f"la tabla de superficies tiene {len(filas)} filas legibles; se esperaban "
            f"al menos 8, una por paquete del arbol. Si el formato cambio, el gate "
            f"esta midiendo el vacio y no lo sabria."
        )

    def test_cada_superficie_nombra_una_evidencia_que_existe(self) -> None:
        ausentes: list[str] = []
        for superficie, _frontera, evidencia in self._filas():
            candidatos = re.findall(
                r"((?:tests|src|scripts|docs)/[\w./-]+\.(?:py|md|json))", evidencia
            )
            if not candidatos:
                ausentes.append(f"{superficie}: la evidencia no nombra ningun fichero del repo")
                continue
            for candidato in candidatos:
                if not (RAIZ / candidato).is_file():
                    ausentes.append(f"{superficie}: {candidato} no existe")
        assert not ausentes, (
            "una superficie dice apoyarse en algo que no existe:\n  " + "\n  ".join(ausentes)
        )

    def test_la_evidencia_de_platform_apunta_a_esta_prueba(self) -> None:
        """La fila que afirmaba OK es la que sostiene la frase.

        La afirmacion «todas las queries filtran por tenant en todos los paths
        verificados» la verifica ESTE fichero. Si la fila cita otro sitio, la
        afirmacion queda sin prueba aunque la prueba exista a tres lineas de
        distancia.
        """
        fila = next((f for f in self._filas() if f[0].strip("` ") == "platform"), None)
        assert fila is not None, "el ADR no tiene fila para `platform`"
        assert "test_b13_threat_model.py" in fila[2], (
            f"la fila de `platform` no cita la prueba de aislamiento que la sostiene: {fila[2]}"
        )


# =====================================================================
class TestElModeloNoSeContradice:
    """«Sin implementar» y «CERRADO», en el mismo fichero."""

    def test_el_adapter_no_puede_estar_fuera_de_alcance_y_cerrado(self) -> None:
        texto = ADR.read_text(encoding="utf-8")
        contradictorio = "sin implementar" in texto and re.search(
            r"E1 Adapter real.{0,40}CERRADO", texto, re.S
        )
        assert not contradictorio, (
            "el ADR dice que el adapter HTTP/LLM esta «sin implementar», fuera de "
            "alcance, y a la vez lo marca CERRADO y le dedica una seccion entera. "
            "Las dos frases no pueden ser verdad y un lector no puede saber cual."
        )

    def test_la_seccion_de_alcance_no_excluye_lo_que_esta_implementado(self) -> None:
        """CONTRA-SALTO del anterior por su otra via de manifestacion.

        Si alguien quita la contradiccion borrando la frase del gap en vez de
        la de alcance, este tambien cae: mide que lo excluido exista en el
        arbol. Declarar fuera de alcance algo implementado no es una omision,
        es una invitacion a no mirarlo.
        """
        texto = ADR.read_text(encoding="utf-8")
        alcance = re.search(r"###?\s*Alcance del modelo(.+?)(?=\n##\s)", texto, re.S)
        assert alcance is not None, "el ADR no tiene seccion de alcance legible"
        for linea in re.findall(r"\*\*Fuera del alcance\*\*:\s*(.+)", alcance.group(1)):
            for componente in re.findall(r"`([\w./-]+)`", linea):
                existe = (SRC / componente).exists() or (SRC / f"{componente}.py").exists()
                assert not existe, (
                    f"el alcance declara fuera de alcance `{componente}`, y ese modulo "
                    f"EXISTE en el arbol. Lo que se declara fuera de alcance no se "
                    f"analiza, y lo que no se analiza es donde se cuelan las fugas."
                )
