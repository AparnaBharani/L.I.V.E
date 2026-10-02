from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Give every constraint/index a predictable name. Without this, PostgreSQL
# invents names, and a future migration that needs to drop or change a
# constraint (e.g. adding a new event type to a CHECK) can't reliably refer to it.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
