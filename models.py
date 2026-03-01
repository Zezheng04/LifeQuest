"""
LifeQuest - RPG 风格任务管理应用 · 数据模型
使用 dataclasses 定义 Player, Rival 与 Quest 实体。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class QuestType(str, Enum):
    """任务类型"""
    DAILY = "日常"
    MAIN = "主线"


class QuestAttribute(str, Enum):
    """任务对应属性（影响雅思四维成长）"""
    PERCEPTION = "perception"  # 感知 (对应听力)
    INSIGHT = "insight"        # 洞察 (对应阅读)
    LOGIC = "logic"            # 逻辑 (对应写作)
    CHARISMA = "charisma"      # 魅力 (对应口语)


class QuestStatus(str, Enum):
    """任务状态"""
    INCOMPLETE = "未完成"
    COMPLETE = "已完成"
    ABANDONED = "已放弃"       # 新增：用于惩罚机制


@dataclass
class Player:
    """玩家实体：等级、经验、金币与属性"""
    level: int = 1
    xp: int = 0
    next_level_xp: int = 100
    gold: int = 0
    perception: float = 5.0   # 听力
    insight: float = 5.0      # 阅读
    logic: float = 5.0        # 写作
    charisma: float = 5.0     # 口语
    id: Optional[int] = None  # 数据库主键，新建时可为 None

    def to_db_row(self) -> tuple:
        """转为数据库行（不含 id，用于 INSERT）"""
        return (
            self.level, self.xp, self.next_level_xp, self.gold,
            self.perception, self.insight, self.logic, self.charisma
        )

    @classmethod
    def from_db_row(cls, row: tuple) -> "Player":
        """从数据库行构造"""
        return cls(
            id=row[0],
            level=row[1], xp=row[2], next_level_xp=row[3], gold=row[4],
            perception=row[5], insight=row[6], logic=row[7], charisma=row[8],
        )


@dataclass
class Rival:
    """影子对手实体：卷王的等级、经验、属性与上次结算时间"""
    level: int = 1
    xp: int = 0
    next_level_xp: int = 100
    perception: float = 5.0
    insight: float = 5.0
    logic: float = 5.0
    charisma: float = 5.0
    last_login_date: str = "" # ISO 格式时间字符串，用于计算离线成长
    id: Optional[int] = None

    def to_db_row(self) -> tuple:
        """转为数据库行（不含 id）"""
        return (
            self.level, self.xp, self.next_level_xp,
            self.perception, self.insight, self.logic, self.charisma,
            self.last_login_date
        )

    @classmethod
    def from_db_row(cls, row: tuple) -> "Rival":
        """从数据库行构造"""
        return cls(
            id=row[0],
            level=row[1], xp=row[2], next_level_xp=row[3],
            perception=row[4], insight=row[5], logic=row[6], charisma=row[7],
            last_login_date=row[8]
        )


@dataclass
class Quest:
    """任务实体"""
    name: str
    description: str
    quest_type: QuestType
    attribute: QuestAttribute
    difficulty: int  # 1-5
    status: QuestStatus = QuestStatus.INCOMPLETE
    completed_at: Optional[str] = None  # 新增：记录完成/放弃的时间，用于历史卷宗
    id: Optional[int] = None

    def to_db_row(self) -> tuple:
        """转为数据库行（不含 id）"""
        return (
            self.name, self.description, self.quest_type.value,
            self.attribute.value, self.difficulty, self.status.value,
            self.completed_at
        )

    @classmethod
    def from_db_row(cls, row: tuple) -> "Quest":
        """从数据库行构造"""
        return cls(
            id=row[0],
            name=row[1], description=row[2],
            quest_type=QuestType(row[3]), attribute=QuestAttribute(row[4]),
            difficulty=row[5], status=QuestStatus(row[6]),
            completed_at=row[7] if len(row) > 7 else None
        )