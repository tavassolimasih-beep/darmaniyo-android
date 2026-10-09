import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# درمانیو از SQL Server Express استفاده می‌کند.
# اتصال را می‌توان در فایل .env تغییر داد.
# مثال Windows Authentication:
# DATABASE_URL=mssql+pyodbc://@localhost\\SQLEXPRESS/Clinic?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mssql+pyodbc://@localhost\\SQLEXPRESS/Clinic?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes",
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    # حالت موبایل (Termux): دیتابیس داخل همان گوشی، در یک فایل
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
