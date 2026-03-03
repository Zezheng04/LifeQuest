from dataclasses import dataclass
from enum import Enum
from typing import Optional

class QuestStatus(Enum):
    INCOMPLETE = "未完成"
    COMPLETE = "已完成"
    ABANDONED = "已放弃"

class QuestType(Enum):
    DAILY = "日常"
    MAIN = "主线"

class QuestAttribute(Enum):
    PERCEPTION = "Perception" # 听力
    INSIGHT = "Insight"       # 阅读
    LOGIC = "Logic"           # 写作
    CHARISMA = "Charisma"     # 口语
    OTHER = "Other"           # 新增：其他 (不加属性)

class RivalTier(Enum):
    SLACKER = "摸鱼怪 (0.5x)"
    NORMAL = "普通人 (1.0x)"
    TRYHARD = "卷王 (1.5x)"
    GODLIKE = "神 (2.0x)"

@dataclass
class Player:
    id: int
    level: int
    xp: int
    next_level_xp: int
    gold: int
    perception: float
    insight: float
    logic: float
    charisma: float
    
    @classmethod
    def from_db_row(cls, row):
        return cls(*row)

@dataclass
class Rival:
    id: int
    level: int
    xp: int
    next_level_xp: int
    perception: float
    insight: float
    logic: float
    charisma: float
    last_login_date: str
    tier: str = RivalTier.NORMAL.value

    @classmethod
    def from_db_row(cls, row):
        row_list = list(row)
        if len(row_list) == 9: 
            return cls(*row_list, tier=RivalTier.NORMAL.value)
        return cls(*row_list)

@dataclass
class Quest:
    # 1. 必填字段
    name: str
    description: str
    quest_type: QuestType
    attribute: QuestAttribute
    difficulty: int
    
    # 2. 选填字段
    id: Optional[int] = None
    status: QuestStatus = QuestStatus.INCOMPLETE
    completed_at: Optional[str] = None
    duration: int = 0 

    def to_db_row(self):
        return (self.name, self.description, self.quest_type.value, 
                self.attribute.value, self.difficulty, self.status.value, 
                self.completed_at, self.duration)

    @classmethod
    def from_db_row(cls, row):
        row_list = list(row)
        q_id = row_list[0]; name = row_list[1]; desc = row_list[2]
        type_str = row_list[3]; attr_str = row_list[4]; diff = row_list[5]
        status_str = row_list[6]; completed_at = row_list[7]
        
        duration = 0
        if len(row_list) > 8:
            duration = row_list[8] if row_list[8] is not None else 0

        try: q_type_enum = QuestType(type_str)
        except ValueError: q_type_enum = QuestType.DAILY

        try: q_attr_enum = QuestAttribute(attr_str)
        except ValueError: q_attr_enum = QuestAttribute.OTHER # 默认回退到Other

        try: q_status_enum = QuestStatus(status_str)
        except ValueError: q_status_enum = QuestStatus.INCOMPLETE

        return cls(
            id=q_id, name=name, description=desc, quest_type=q_type_enum,
            attribute=q_attr_enum, difficulty=diff, status=q_status_enum,
            completed_at=completed_at, duration=duration
        )

@dataclass
class Reward:
    id: Optional[int]
    name: str
    cost: int
    description: str = ""