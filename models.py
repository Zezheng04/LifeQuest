from dataclasses import dataclass
from enum import Enum
from typing import Optional

class QuestStatus(Enum):
    INCOMPLETE = "未完成"
    COMPLETE = "已完成"
    ABANDONED = "已放弃"
    EXPIRED = "已过期"     # 新增：过期状态(用于历史记录)

class QuestType(Enum):
    DAILY = "日常"         # 这里的定义现在更多代表“生活类”
    MAIN = "主线"         # 代表“攻坚类”

class QuestFrequency(Enum):
    ONCE = "一次性"       # 做完就没了
    RECURRING = "长期循环" # 每天重置

class QuestAttribute(Enum):
    PERCEPTION = "Perception" 
    INSIGHT = "Insight"       
    LOGIC = "Logic"           
    CHARISMA = "Charisma"     
    OTHER = "Other"           

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
    
    # 3. V3.0 新增字段
    # frequency: 决定任务是否第二天重置
    frequency: QuestFrequency = QuestFrequency.ONCE 
    # active_days: 字符串 "1,2,3,4,5" 代表周一到周五出现。空字符串代表每天。
    active_days: str = "" 

    def to_db_row(self):
        # DB顺序: name, desc, type, attr, diff, status, completed_at, duration, frequency, active_days
        return (self.name, self.description, self.quest_type.value, 
                self.attribute.value, self.difficulty, self.status.value, 
                self.completed_at, self.duration, self.frequency.value, self.active_days)

    @classmethod
    def from_db_row(cls, row):
        row_list = list(row)
        # 基础字段读取 (兼容旧版本长度)
        q_id = row_list[0]; name = row_list[1]; desc = row_list[2]
        type_str = row_list[3]; attr_str = row_list[4]; diff = row_list[5]
        status_str = row_list[6]; completed_at = row_list[7]
        
        duration = 0
        if len(row_list) > 8 and row_list[8] is not None: duration = row_list[8]

        # V3 新增字段读取 (带默认值容错)
        freq_enum = QuestFrequency.ONCE
        active_days_str = ""
        
        if len(row_list) > 9 and row_list[9] is not None:
            try: freq_enum = QuestFrequency(row_list[9])
            except: freq_enum = QuestFrequency.ONCE
            
        if len(row_list) > 10 and row_list[10] is not None:
            active_days_str = str(row_list[10])

        # 枚举转换
        try: q_type_enum = QuestType(type_str)
        except: q_type_enum = QuestType.DAILY

        try: q_attr_enum = QuestAttribute(attr_str)
        except: q_attr_enum = QuestAttribute.OTHER

        try: q_status_enum = QuestStatus(status_str)
        except: q_status_enum = QuestStatus.INCOMPLETE

        return cls(
            id=q_id, name=name, description=desc, quest_type=q_type_enum,
            attribute=q_attr_enum, difficulty=diff, status=q_status_enum,
            completed_at=completed_at, duration=duration,
            frequency=freq_enum, active_days=active_days_str
        )

@dataclass
class Reward:
    id: Optional[int]
    name: str
    cost: int
    description: str = ""