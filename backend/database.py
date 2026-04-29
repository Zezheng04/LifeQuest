from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 数据库连接URL配置 (开发环境默认使用root账号)
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:123456@localhost/lifequest_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
