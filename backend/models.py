from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    coins = Column(Integer, default=0)
    streak = Column(Integer, default=0)
    attribute_perception = Column(Integer, default=1)
    attribute_strength = Column(Integer, default=1)
    attribute_intelligence = Column(Integer, default=1)
    attribute_charm = Column(Integer, default=1)

    tasks = relationship("Task", back_populates="owner")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(100), nullable=False)
    description = Column(String(255))
    difficulty_tier = Column(Integer, default=1)
    status = Column(String(20), default="未完成")  # "未完成", "已完成", "已过期"
    is_loop = Column(Boolean, default=False)

    owner = relationship("User", back_populates="tasks")
