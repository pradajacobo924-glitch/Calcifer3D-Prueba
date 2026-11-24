from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import mysql.connector
from mysql.connector import Error


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SQL_SCHEMA_PATH = PROJECT_DIR / "database" / "calcifer3d.sql"


def get_db_config(include_database: bool = True) -> dict[str, object]:
    """
    Obtiene la configuración de conexión a MySQL.
    Soporta:
    1. URIs completas: MYSQL_ADDON_URI (Clever Cloud), MYSQL_URL o DATABASE_URL
    2. Variables de Clever Cloud: MYSQL_ADDON_HOST, MYSQL_ADDON_PORT, MYSQL_ADDON_USER, MYSQL_ADDON_PASSWORD, MYSQL_ADDON_DB
    3. Variables estándar: MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
    4. Valores por defecto locales (127.0.0.1:3306, root, calcifer3d)
    """
    uri = (
        os.getenv("MYSQL_ADDON_URI")
        or os.getenv("MYSQL_URL")
        or os.getenv("DATABASE_URL")
    )
    if uri:
        parsed = urlparse(uri)
        config: dict[str, object] = {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": parsed.username or "root",
            "password": parsed.password or "",
            "connection_timeout": int(os.getenv("MYSQL_TIMEOUT", "10")),
        }
        if include_database:
            db_name = parsed.path.lstrip("/") if parsed.path else "calcifer3d"
            config["database"] = db_name
        return config

    host = os.getenv("MYSQL_HOST") or os.getenv("MYSQL_ADDON_HOST") or "127.0.0.1"
    port = int(os.getenv("MYSQL_PORT") or os.getenv("MYSQL_ADDON_PORT") or "3306")
    user = os.getenv("MYSQL_USER") or os.getenv("MYSQL_ADDON_USER") or "root"
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("MYSQL_ADDON_PASSWORD") or ""
    database = os.getenv("MYSQL_DATABASE") or os.getenv("MYSQL_ADDON_DB") or "calcifer3d"

    config: dict[str, object] = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "connection_timeout": int(os.getenv("MYSQL_TIMEOUT", "10")),
    }
    if include_database:
        config["database"] = database
    return config


def get_connection(include_database: bool = True):
    config = get_db_config(include_database=include_database)

    try:
        return mysql.connector.connect(**config)
    except Error:
        if config.get("host") not in {"127.0.0.1", "localhost"}:
            raise

        fallback_config = dict(config)
        fallback_config["host"] = "::1"
        return mysql.connector.connect(**fallback_config)


def database_is_initialized() -> bool:
    try:
        with get_connection(include_database=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE() AND table_name = 'usuarios'
                    """
                )
                row = cursor.fetchone()
                return bool(row and row[0] > 0)
    except Error:
        return False


def bootstrap_database() -> None:
    if not SQL_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"No se encontro el archivo SQL: {SQL_SCHEMA_PATH}")

    if database_is_initialized():
        return

    # Si estamos en entorno local y la base no existe aún, intentar crearla
    config = get_db_config(include_database=False)
    target_db = str(get_db_config(include_database=True).get("database", "calcifer3d"))

    if config.get("host") in {"127.0.0.1", "localhost", "::1"}:
        try:
            with get_connection(include_database=False) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{target_db}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                    )
                connection.commit()
        except Error:
            pass

    # Conectar directamente a la base de datos asignada y ejecutar el esquema
    # Se filtran CREATE DATABASE y USE para no fallar en nubes (Clever Cloud) con usuarios restringidos
    with get_connection(include_database=True) as connection:
        with connection.cursor() as cursor:
            sql_script = SQL_SCHEMA_PATH.read_text(encoding="utf-8")
            statements = [
                statement.strip()
                for statement in sql_script.split(";")
                if statement.strip()
            ]
            for statement in statements:
                clean_lines = [
                    line.strip()
                    for line in statement.splitlines()
                    if line.strip() and not line.strip().startswith("--") and not line.strip().startswith("/*")
                ]
                normalized_stmt = " ".join(clean_lines).upper()
                if normalized_stmt.startswith("CREATE DATABASE") or normalized_stmt.startswith("USE "):
                    continue
                cursor.execute(statement)
        connection.commit()
