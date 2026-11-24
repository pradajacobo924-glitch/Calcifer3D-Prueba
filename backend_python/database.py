from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import mysql.connector
from mysql.connector import Error


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SQL_SCHEMA_PATH = PROJECT_DIR / "database" / "calcifer3d.sql"


def get_env_case_insensitive(*names: str, default: str | None = None) -> str | None:
    """Busca variables de entorno ignorando mayúsculas/minúsculas y espacios en blanco."""
    upper_env = {k.strip().upper(): v.strip() for k, v in os.environ.items() if v}
    for name in names:
        key = name.strip().upper()
        if key in upper_env and upper_env[key]:
            return upper_env[key]
    return default


def parse_mysql_uri(uri: str) -> dict[str, object] | None:
    """
    Parsea una URI de conexión MySQL como:
    mysql://usuario:password@host:3306/nombre_db
    Soporta contraseñas con caracteres especiales y comillas.
    """
    cleaned = uri.strip().strip("'\"")
    if not cleaned.startswith("mysql://"):
        return None

    # Intentar con expresión regular primero (soporta @ en la contraseña)
    match = re.match(r"^mysql://([^:]+):(.*)@([^:/]+)(?::(\d+))?/(.+)$", cleaned)
    if match:
        user, password, host, port_str, db_part = match.groups()
        db_name = db_part.split("?")[0]
        return {
            "host": host,
            "port": int(port_str) if port_str else 3306,
            "user": unquote(user),
            "password": unquote(password),
            "database": db_name,
        }

    # Fallback con urlparse
    parsed = urlparse(cleaned)
    db_name = parsed.path.lstrip("/").split("?")[0] if parsed.path else "calcifer3d"
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else "root",
        "password": unquote(parsed.password) if parsed.password else "",
        "database": db_name,
    }


def get_db_config(include_database: bool = True) -> dict[str, object]:
    """
    Obtiene la configuración de conexión a MySQL.
    Soporta:
    1. URIs completas: MYSQL_ADDON_URI (Clever Cloud), MYSQL_URL o DATABASE_URL
    2. Variables directas: MYSQL_HOST, MYSQL_ADDON_HOST, MYSQLHOST, DB_HOST
    3. Variables estándar e insensibles a mayúsculas
    4. Valores por defecto locales (127.0.0.1:3306, root, calcifer3d)
    """
    uri = get_env_case_insensitive("MYSQL_ADDON_URI", "MYSQL_URL", "DATABASE_URL")
    if uri:
        parsed_config = parse_mysql_uri(uri)
        if parsed_config and parsed_config.get("host"):
            config: dict[str, object] = {
                "host": parsed_config["host"],
                "port": parsed_config.get("port", 3306),
                "user": parsed_config.get("user", "root"),
                "password": parsed_config.get("password", ""),
                "connection_timeout": int(get_env_case_insensitive("MYSQL_TIMEOUT", default="15") or 15),
            }
            if include_database:
                config["database"] = parsed_config.get("database", "calcifer3d")
            return config

    host = get_env_case_insensitive(
        "MYSQL_HOST", "MYSQL_ADDON_HOST", "MYSQLHOST", "DB_HOST", default="127.0.0.1"
    )
    port_str = get_env_case_insensitive(
        "MYSQL_PORT", "MYSQL_ADDON_PORT", "MYSQLPORT", "DB_PORT", default="3306"
    )
    user = get_env_case_insensitive(
        "MYSQL_USER", "MYSQL_ADDON_USER", "MYSQLUSER", "DB_USER", default="root"
    )
    password = get_env_case_insensitive(
        "MYSQL_PASSWORD", "MYSQL_ADDON_PASSWORD", "MYSQLPASSWORD", "DB_PASSWORD", default=""
    )
    database = get_env_case_insensitive(
        "MYSQL_DATABASE", "MYSQL_ADDON_DB", "MYSQLDATABASE", "DB_NAME", default="calcifer3d"
    )

    config: dict[str, object] = {
        "host": host or "127.0.0.1",
        "port": int(port_str or 3306),
        "user": user or "root",
        "password": password or "",
        "connection_timeout": int(get_env_case_insensitive("MYSQL_TIMEOUT", default="15") or 15),
    }
    if include_database:
        config["database"] = database or "calcifer3d"
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
