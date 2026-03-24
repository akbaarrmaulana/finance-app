import os
from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv

load_dotenv()

# We use fallback to a local sqlite database for local development if DATABASE_URL is not set
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./finance.db")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Render dialect mapping for postgres:// vs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

from typing import Any

# For Supabase connection pooler, we need pool_pre_ping to check for dropped connections
kwargs: dict[str, Any] = {"echo": True, "connect_args": connect_args}
if not DATABASE_URL.startswith("sqlite"):
    kwargs["pool_pre_ping"] = True
    kwargs["pool_recycle"] = 300 # refresh connections every 5 minutes

engine = create_engine(DATABASE_URL, **kwargs)

# We removed the heavy supabase client and will use gotrue directly for auth
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
