from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db import Base
import app.models  # noqa: F401  (register all tables)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)
target_metadata = Base.metadata
_SCHEMA = None if _settings.db_schema == "public" else _settings.db_schema


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    if _SCHEMA:
        from sqlalchemy import event

        @event.listens_for(connectable, "connect")
        def _set_path(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute(f"set search_path to {_SCHEMA}, public")
            cur.close()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          version_table_schema=_SCHEMA, include_schemas=False)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
