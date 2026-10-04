"""B12: la version del esquema es un hecho, y subir una base vieja tiene nombre.

El veredicto del gate decia, textual: «no existe ninguna funcion de upgrade
o de migracion de datos entre releases: no hay de donde subir una base
creada por una version anterior». La medicion de B12 (`/tmp/b12_measure.py`,
0 de 5 PASS) dijo que el problema es mas profundo que «falta la funcion»:

    SCHEMA_VERSION = 1, sin moverse en 73 releases;
    se escribe con INSERT OR IGNORE y NO SE LEE en storage.py;
    borrar la tabla schema_version entera de una base y abrirla la deja
    recrear en silencio, luego la version es un DEFAULT y no un hecho.

Los cinco conjuntos de tests de aqui son DISJUNTOS, y cada uno mira una
cosa distinta. La razon de que sean disjuntos esta al final de cada clase:
si dos conjuntos miraran lo mismo, uno podria caerse y el otro taparlo.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from skillgraph.core.errors import SchemaTooNewError, SkillGraphError
from skillgraph.platform import migrations, schema
from skillgraph.platform.migrations import MIGRACIONES, Migracion
from skillgraph.platform.storage import Storage

RAIZ = Path(__file__).resolve().parents[1]


def _base_lista(tmp_path: Path, nombre: str = "p.db") -> Path:
    """Una base creada por el codigo de HOY, cerrada."""
    st = Storage(tmp_path / nombre)
    st.close()
    return tmp_path / nombre


def _base_sin_libro(tmp_path: Path, nombre: str = "vieja.db") -> Path:
    """Una base de una release anterior: existe, pero no tiene el libro.

    Se construye de verdad —se ejecuta el DDL actual y se le quitan las
    tablas que una release anterior no conocia— en vez de simularla con un
    mock. Un mock que finge una base vieja no comprueba que el codigo la
    pueda abrir; una base de verdad, si.
    """
    ruta = tmp_path / nombre
    st = Storage(ruta)
    st.close()
    con = sqlite3.connect(ruta)
    con.execute("DROP TABLE schema_migrations")
    con.execute("DELETE FROM schema_version")
    con.commit()
    con.close()
    return ruta


# =====================================================================
class TestLaVersionEsDerivada:
    """`SCHEMA_VERSION` no es un literal: sale de las migraciones declaradas."""

    def test_no_es_un_literal_escrito_a_mano(self) -> None:
        """La propiedad es «no se puede olvidar subirla», no «vale 2».

        Un guard por lectura buscaria `SCHEMA_VERSION = 1` y pasaria. La
        propiedad se mide por AST: el valor tiene que ser una expresion que
        dependa de `MIGRACIONES`, porque lo que importa es de donde sale.
        """
        arbol = ast.parse((RAIZ / "src/skillgraph/platform/schema.py").read_text("utf-8"))
        # `SCHEMA_VERSION: int = ...` es un `AnnAssign`, no un `Assign`. Un
        # guard que solo mirara `Assign` no encontraria nada y pasaria en
        # verde por no haber medido: hay que aceptar las dos formas.
        asignaciones = [
            n
            for n in ast.walk(arbol)
            if (
                isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "SCHEMA_VERSION" for t in n.targets)
            )
            or (
                isinstance(n, ast.AnnAssign)
                and isinstance(n.target, ast.Name)
                and n.target.id == "SCHEMA_VERSION"
            )
        ]
        assert len(asignaciones) == 1, "SCHEMA_VERSION debe asignarse una sola vez"
        valor = asignaciones[0].value
        assert valor is not None, "SCHEMA_VERSION se declara sin valor: no es derivable"
        assert not isinstance(valor, ast.Constant), (
            "SCHEMA_VERSION sigue siendo un literal escrito a mano: "
            "se puede olvidar subirlo y nada lo note"
        )
        assert self._deriva_de_migraciones(valor), (
            "SCHEMA_VERSION tiene que derivarse de la lista de migraciones, "
            "directamente o a traves de version_declarada()"
        )

    @staticmethod
    def _deriva_de_migraciones(valor: ast.expr) -> bool:
        """¿El valor depende de `MIGRACIONES`? Se resuelve UN salto.

        `SCHEMA_VERSION = version_declarada()` no menciona `MIGRACIONES` en
        su linea, asi que un guard que solo mirara esa linea mediria la
        forma de escribirla y no la propiedad. Por eso se sigue el salto: si
        el valor es una llamada, se abre el cuerpo de esa funcion y se
        comprueba que ahi dentro se referencia la lista.

        Un salto y no dos a proposito. Con dos, el guard dejaria de medir lo
        que el modulo hace y empezaria a medir el camino que eligio quien
        escribio la linea, que es justo cuando un guard se vuelve decoracion.
        """
        if any(isinstance(n, ast.Name) and n.id == "MIGRACIONES" for n in ast.walk(valor)):
            return True
        if not isinstance(valor, ast.Call):
            return False
        func = valor.func
        if not isinstance(func, ast.Name) or func.id != "version_declarada":
            return False
        arbol = ast.parse((RAIZ / "src/skillgraph/platform/migrations.py").read_text("utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.FunctionDef) and nodo.name == "version_declarada":
                return any(
                    isinstance(n, ast.Name) and n.id == "MIGRACIONES" for n in ast.walk(nodo)
                )
        return False

    def test_coincide_con_el_numero_de_migraciones(self) -> None:
        assert len(MIGRACIONES) == schema.SCHEMA_VERSION, (
            f"declara {schema.SCHEMA_VERSION} y hay {len(MIGRACIONES)} migraciones"
        )

    def test_una_migracion_nueva_mueve_la_version(self) -> None:
        """CONTRA-SALTO en la direccion de la propiedad.

        No se comprueba que un caso REAL mueva la version —eso seria
        escribir una migracion de mentira en el modulo de produccion— sino
        que la FUNCION que calcula la version responde a la lista. Si la
        version se calculara con un numero fijo, esto pasaria igual.
        """
        antes = migrations.version_declarada()
        extra = Migracion(
            id="0003_prueba_de_que_la_version_responde",
            aplicar=lambda cur: cur.execute("SELECT 1"),
        )
        despues = migrations.version_declarada((*MIGRACIONES, extra))
        assert despues == antes + 1, "anadir una migracion tiene que mover la version"


# =====================================================================
class TestElLibroDeMigraciones:
    """Cada migracion aplicada queda anotada, con su identificador."""

    def test_una_base_nueva_tiene_todas_anotadas(self, tmp_path: Path) -> None:
        st = Storage(_base_lista(tmp_path))
        aplicadas = st.migraciones_aplicadas()
        st.close()
        assert aplicadas == tuple(m.id for m in MIGRACIONES), aplicadas

    def test_una_base_nueva_declara_la_version_actual(self, tmp_path: Path) -> None:
        st = Storage(_base_lista(tmp_path))
        version = st.version_esquema()
        st.close()
        assert version == schema.SCHEMA_VERSION, version

    def test_ejecutar_el_libro_dos_veces_no_cambia_nada(self, tmp_path: Path) -> None:
        """La idempotencia se EJECUTA, no se lee.

        Es la propiedad que sostiene todo lo demas: si correr el libro dos
        veces no fuera lo mismo que correrlo una, el libro tendria que
        decidir por el estado del esquema en vez de delegar en cada
        migracion, y ahi es donde se cuela la carrera de B2.
        """
        ruta = _base_lista(tmp_path)
        st = Storage(ruta)
        primera = st.migraciones_aplicadas()
        st.close()

        con = sqlite3.connect(ruta)
        aplicadas_otra_vez = migrations.sincroniza(con.cursor())
        estado = con.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        con.close()

        assert aplicadas_otra_vez == (), f"no quedaban pendientes: {aplicadas_otra_vez}"
        assert tuple(f[0] for f in estado) == primera, "el libro se duplico al correrlo dos veces"

    def test_los_identificadores_son_unicos(self) -> None:
        ids = [m.id for m in MIGRACIONES]
        assert len(ids) == len(set(ids)), f"identificadores repetidos: {ids}"

    def test_los_identificadores_no_dependen_del_orden_de_las_filas(self) -> None:
        """Un id no puede ser el indice: reordenar la lista no lo invalida.

        Es lo que separa «un numero que se renumera al insertar» de «un
        identificador estable». Con indice, meter un hotfix en medio haria
        que una base ya migrada creyera que le falta lo de despues.
        """
        for m in MIGRACIONES:
            assert m.id[0].isdigit(), f"{m.id} deberia empezar por un numero de orden"
            assert "_" in m.id, f"{m.id} deberia decir QUE hace, no solo WHEN"


# =====================================================================
class TestSubirUnaBaseVieja:
    """Abrir una base de una release anterior la sube, y se puede preguntar."""

    def test_una_base_sin_libro_se_abre_y_se_migra(self, tmp_path: Path) -> None:
        ruta = _base_sin_libro(tmp_path)
        st = Storage(ruta)
        aplicadas = st.migraciones_aplicadas()
        version = st.version_esquema()
        st.close()
        assert aplicadas == tuple(m.id for m in MIGRACIONES), aplicadas
        assert version == schema.SCHEMA_VERSION, version

    def test_subir_una_base_conserva_los_datos(self, tmp_path: Path) -> None:
        """Subir no puede ser «recrear todo»: seria perder el proyecto.

        Se escribe en la base ANTES de subirla, y se comprueba que la fila
        sigue ahi despues. Un upgrade que hace la base indistinguible de una
        nueva cumple la version y pierde el trabajo del usuario.

        Se escribe con SQL y no por la API porque `Storage` no expone un
        «crear proyecto»: la fachada delega en repositorios y no tiene ese
        metodo. Inventarse uno en el test haria pasar el test por un camino
        que el producto no tiene.
        """
        ruta = _base_lista(tmp_path)
        con = sqlite3.connect(ruta)
        con.execute(
            "INSERT INTO resources(uid, tenant_id, project_id, api_version, kind, "
            "namespace, name, spec_json) VALUES (?,?,?,?,?,?,?,?)",
            ("u1", "t1", "p1", "v1", "Brick", "ns", "b1", "{}"),
        )
        con.execute("DELETE FROM schema_migrations")
        con.execute("DELETE FROM schema_version")
        con.commit()
        con.close()

        st2 = Storage(ruta)
        st2.close()
        con = sqlite3.connect(ruta)
        filas = con.execute("SELECT uid, name FROM resources").fetchall()
        con.close()
        assert filas == [("u1", "b1")], f"subir la base borro datos: {filas}"

    def test_abrir_una_base_al_dia_no_escribe_nada(self, tmp_path: Path) -> None:
        """CONTRA-SALTO de la REGRESION que este bloque introdujo y corrigio.

        La primera version de `sincroniza` hacia `DELETE FROM schema_version`
        seguido de `INSERT` SIEMPRE. Antes era `INSERT OR IGNORE`, que tras
        la primera apertura no escribe nada, luego abrir una base era una
        LECTURA. Con el `DELETE` incondicional cada proceso tomaba la
        transaccion de escritura al abrir, y con los ocho procesos
        concurrentes de `test_b2_real_concurrency` uno se quedaba sin su
        turno. MEDIDO antes de arreglar: tres corridas dan verde, verde y
        ROJO, con «se esperaban 8 autores distintos y hay 7».

        Por que esto se mide aqui y no contando ejecuciones del test
        concurrente: aquel test es INTERMITENTE por definicion —ocho
        procesos y un bloqueio—, y seis ejecuciones en verde no son una
        prueba, son una tirada. `total_changes` es determinista: cuenta las
        filas que la conexion ha modificado, y si abrir no escribe, sale 0
        siempre.

        El otro lado tambien se mide. Una base que HAY que subir si escribe,
        y tiene que escribir: si el contrasalto de arriba pasara porque la
        version no se escribe nunca, la propiedad seria certaina por no
        hacer nada.
        """
        ruta = _base_lista(tmp_path)
        st = Storage(ruta)
        assert st._conn.total_changes == 0, (
            "abrir una base ya al dia escribio: es lo que perdio un proceso "
            "en la prueba de concurrencia"
        )
        st.close()

        con = sqlite3.connect(ruta)
        con.execute("DELETE FROM schema_version")
        con.commit()
        con.close()

        st2 = Storage(ruta)
        assert st2._conn.total_changes > 0, (
            "subrir una base atrasada no escribio nada: la version no se "
            "corrigio y el contrasalto de arriba pasaria por no hacer nada"
        )
        st2.close()

    def test_la_versio_n_se_puede_preguntar_a_la_base(self, tmp_path: Path) -> None:
        """La pregunta del bloque: ¿que version tiene este proyecto?

        Se responde por el DATO de la base, no por la constante del modulo.
        Preguntar a una base recien creada y a una ya subida tiene que dar lo
        mismo, y si se respondiera leyendo `SCHEMA_VERSION` la segunda
        respuesta seria tautologica: no estaria preguntando a la base.
        """
        ruta = _base_lista(tmp_path)
        st = Storage(ruta)
        declarada_en_python = st.version_esquema()
        st.close()
        con = sqlite3.connect(ruta)
        leida_de_sql = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        con.close()
        assert declarada_en_python == leida_de_sql, (
            f"el codigo dice {declarada_en_python} y la tabla dice {leida_de_sql}"
        )


# =====================================================================
class TestUnaBaseMasNuevaNoSeAbre:
    """Abrir en silencio un esquema que el codigo no conoce es perder datos."""

    def test_una_base_mas_nueva_falla(self, tmp_path: Path) -> None:
        ruta = _base_lista(tmp_path)
        con = sqlite3.connect(ruta)
        con.execute("DELETE FROM schema_version")
        con.execute(
            "INSERT INTO schema_version(version) VALUES (?)",
            (schema.SCHEMA_VERSION + 1,),
        )
        con.commit()
        con.close()

        with pytest.raises(SchemaTooNewError) as exc:
            Storage(ruta)
        assert exc.value.code == "sg_schema_too_new"

    def test_el_error_dice_que_versiones_se_vieron(self, tmp_path: Path) -> None:
        """Un verificador que dice «falso» sin decir «donde» es un callejon.

        El mensaje tiene que permitir arreglarlo sin abrir un debugger: la
        version que declara la base y la que declara el codigo.
        """
        ruta = _base_lista(tmp_path)
        futura = schema.SCHEMA_VERSION + 7
        con = sqlite3.connect(ruta)
        con.execute("DELETE FROM schema_version")
        con.execute("INSERT INTO schema_version(version) VALUES (?)", (futura,))
        con.commit()
        con.close()

        with pytest.raises(SchemaTooNewError) as exc:
            Storage(ruta)
        mensaje = str(exc.value)
        assert str(futura) in mensaje, mensaje
        assert str(schema.SCHEMA_VERSION) in mensaje, mensaje

    def test_no_sale_como_traceback_de_sqlite(self, tmp_path: Path) -> None:
        """El error es del DOMINIO, no del adapter que lo detecta.

        Un `sqlite3.OperationalError` atravessaria el `except` que traduce a
        exit code y llegaria al operador como Traceback. Es el mismo defecto
        que WI-109 cerro por el otro lado de la misma frontera.
        """
        ruta = _base_lista(tmp_path)
        con = sqlite3.connect(ruta)
        con.execute("DELETE FROM schema_version")
        con.execute(
            "INSERT INTO schema_version(version) VALUES (?)",
            (schema.SCHEMA_VERSION + 1,),
        )
        con.commit()
        con.close()

        with pytest.raises(SkillGraphError) as exc:
            Storage(ruta)
        assert not isinstance(exc.value, sqlite3.Error), type(exc.value)


# =====================================================================
class TestLaColumnaAdHocDejoDeSerUnCasoEspecial:
    """`claims.assertion_origin` era una funcion escrita a mano en Storage."""

    def test_la_migracion_de_la_columna_esta_en_el_libro(self) -> None:
        ids = [m.id for m in MIGRACIONES]
        assert any("assertion_origin" in i for i in ids), (
            f"la migracion de la columna no esta en el libro: {ids}"
        )

    def test_una_base_sin_esa_columna_la_recupera(self, tmp_path: Path) -> None:
        ruta = _base_lista(tmp_path)
        con = sqlite3.connect(ruta)
        con.execute("ALTER TABLE claims DROP COLUMN assertion_origin")
        con.commit()
        con.close()

        st = Storage(ruta)
        columnas = {f[1] for f in st._conn.execute("PRAGMA table_info(claims)").fetchall()}
        st.close()
        assert "assertion_origin" in columnas, "la columna no se ha recuperado"

    def test_storage_no_tiene_ya_el_metodo_ado_hoc(self) -> None:
        """El caso especial desaparece del facade, no se esconde en el libro.

         Si el metodo se queda, hay dos caminos para migrar y el que se
        YR forgetting el codigo nuevo seguiria siendo el que funciona. Es la
         misma trampa que un «conectar != contener» de WI-102.
        """
        assert not hasattr(Storage, "_anade_column_claims_assertion_origin"), (
            "la migracion ad-hoc sigue en el facade: hay dos caminos para lo mismo"
        )
