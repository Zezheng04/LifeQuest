from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_level_xp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    gold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    perception: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    insight: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    logic: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    charisma: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active_date: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    streak_freeze_cards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    target_name: Mapped[str] = mapped_column(String(120), default="雅思 8.0 竞速对决", nullable=False)
    target_date: Mapped[str] = mapped_column(String(32), default="2024-12-31", nullable=False)
    attr1: Mapped[str] = mapped_column(String(32), default="听力(感知)", nullable=False)
    attr2: Mapped[str] = mapped_column(String(32), default="阅读(洞察)", nullable=False)
    attr3: Mapped[str] = mapped_column(String(32), default="写作(逻辑)", nullable=False)
    attr4: Mapped[str] = mapped_column(String(32), default="口语(魅力)", nullable=False)

    rival: Mapped["Rival"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    quests: Mapped[list["Quest"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    rewards: Mapped[list["Reward"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Rival(Base):
    __tablename__ = "rivals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_level_xp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    perception: Mapped[float] = mapped_column(Float, default=5.5, nullable=False)
    insight: Mapped[float] = mapped_column(Float, default=5.5, nullable=False)
    logic: Mapped[float] = mapped_column(Float, default=5.5, nullable=False)
    charisma: Mapped[float] = mapped_column(Float, default=5.5, nullable=False)
    last_login_date: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="普通人 (1.0x)", nullable=False)

    user: Mapped[User] = relationship(back_populates="rival")


class Quest(Base):
    __tablename__ = "quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    quest_type: Mapped[str] = mapped_column(String(32), nullable=False)
    attribute: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="未完成", nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frequency: Mapped[str] = mapped_column(String(32), default="一次性", nullable=False)
    active_days: Mapped[str] = mapped_column(String(32), default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="quests")


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="rewards")
