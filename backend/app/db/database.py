import os
from threading import RLock
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://cloudmind:cloudmind_password@localhost:5432/cloudmind",
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


_schema_lock = RLock()
_schema_ready = False


def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def create_database_tables() -> None:
    from app.db import models  # noqa: F401

    global _schema_ready
    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return
        Base.metadata.create_all(bind=engine)
        _migrate_tenant_columns()
        _schema_ready = True


def _migrate_tenant_columns() -> None:
    """Apply the small, additive migration needed by pre-tenancy databases."""

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    additions = {
        "users": {
            "role": "VARCHAR(32) NOT NULL DEFAULT 'member'",
            "must_change_password": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
        "projects": {
            "owner_id": "VARCHAR(36)",
        },
        "conversation_sessions": {
            "user_id": "VARCHAR(36)",
        },
        "pipeline_runs": {
            "user_id": "VARCHAR(36)",
        },
        "llm_planning_runs": {
            "user_id": "VARCHAR(36)",
        },
    }

    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in table_names:
                continue
            existing = {
                column["name"] for column in inspect(connection).get_columns(table_name)
            }
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(
                            f'ALTER TABLE "{table_name}" '
                            f'ADD COLUMN "{column_name}" {definition}'
                        )
                    )

        if "projects" in table_names:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_projects_owner_id "
                    "ON projects (owner_id)"
                )
            )
        if "conversation_sessions" in table_names:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_conversation_sessions_user_id "
                    "ON conversation_sessions (user_id)"
                )
            )
        if "pipeline_runs" in table_names:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_user_id "
                    "ON pipeline_runs (user_id)"
                )
            )
        if "users" in table_names:
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)")
            )
        if "llm_planning_runs" in table_names:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_llm_planning_runs_user_id "
                    "ON llm_planning_runs (user_id)"
                )
            )

    if engine.dialect.name != "postgresql" or "projects" not in table_names:
        return

    tenant_foreign_keys = (
        (
            "fk_projects_owner_id_users",
            "ALTER TABLE projects ADD CONSTRAINT fk_projects_owner_id_users "
            "FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE",
        ),
        (
            "fk_conversation_sessions_user_id_users",
            "ALTER TABLE conversation_sessions ADD CONSTRAINT "
            "fk_conversation_sessions_user_id_users FOREIGN KEY (user_id) "
            "REFERENCES users(id) ON DELETE CASCADE",
        ),
        (
            "fk_pipeline_runs_user_id_users",
            "ALTER TABLE pipeline_runs ADD CONSTRAINT fk_pipeline_runs_user_id_users "
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
        ),
        (
            "fk_llm_planning_runs_user_id_users",
            "ALTER TABLE llm_planning_runs ADD CONSTRAINT "
            "fk_llm_planning_runs_user_id_users FOREIGN KEY (user_id) "
            "REFERENCES users(id) ON DELETE CASCADE",
        ),
    )
    with engine.begin() as connection:
        for constraint_name, statement in tenant_foreign_keys:
            exists = connection.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname = :constraint_name"
                ),
                {"constraint_name": constraint_name},
            ).scalar()
            if not exists:
                connection.execute(text(statement))

    # The old schema made repo_url globally unique. Tenancy allows two users to
    # save the same repository, while keeping it unique inside one account.
    for constraint in inspect(engine).get_unique_constraints("projects"):
        if constraint.get("column_names") == ["repo_url"] and constraint.get("name"):
            constraint_name = engine.dialect.identifier_preparer.quote(
                constraint["name"]
            )
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE projects DROP CONSTRAINT {constraint_name}")
                )

    for index in inspect(engine).get_indexes("projects"):
        if (
            index.get("unique")
            and index.get("column_names") == ["repo_url"]
            and index.get("name")
        ):
            index_name = engine.dialect.identifier_preparer.quote(index["name"])
            with engine.begin() as connection:
                connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_projects_repo_url "
                "ON projects (repo_url)"
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_owner_repo_url "
                "ON projects (owner_id, repo_url)"
            )
        )


def drop_database_tables() -> None:
    from app.db import models  # noqa: F401

    global _schema_ready
    Base.metadata.drop_all(bind=engine)
    _schema_ready = False
