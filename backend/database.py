from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Build DB URL
# Format: postgresql+asyncpg://user:password@host:port/dbname
user = os.getenv("POSTGRES_USER", "phantom")
password = os.getenv("POSTGRES_PASSWORD", "phantom")
db_name = os.getenv("POSTGRES_DB", "phantom_db")
host = "postgres" # Service name in docker-compose. Usually 'postgres' or 'localhost' if running locally

# Check if running in Docker (by env) or Local
if os.getenv("DOCKER_MODE") != "true":
    host = "localhost"

DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:5432/{db_name}"

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
