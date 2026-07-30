from typing import List, Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str

    class Config:
        orm_mode = True


class ConfigPayload(BaseModel):
    target_name: str
    target_date: str
    attr1: str
    attr2: str
    attr3: str
    attr4: str


class PlayerResponse(BaseModel):
    id: int
    level: int
    xp: int
    next_level_xp: int
    gold: int
    perception: float
    insight: float
    logic: float
    charisma: float
    streak_days: int = 0
    last_active_date: str = ""
    streak_freeze_cards: int = 0


class RivalResponse(BaseModel):
    id: int
    level: int
    xp: int
    next_level_xp: int
    perception: float
    insight: float
    logic: float
    charisma: float
    last_login_date: str
    tier: str

    class Config:
        orm_mode = True


class RivalUpdate(BaseModel):
    tier: str


class QuestBase(BaseModel):
    name: str
    description: str
    quest_type: str
    attribute: str
    difficulty: int
    frequency: str = "一次性"
    active_days: str = ""


class QuestCreate(QuestBase):
    pass


class QuestUpdate(QuestBase):
    pass


class QuestResponse(QuestBase):
    id: int
    status: str
    completed_at: Optional[str] = None
    duration: int = 0

    class Config:
        orm_mode = True


class CompleteQuestRequest(BaseModel):
    duration_mins: int = 0


class CompleteQuestResponse(BaseModel):
    player: PlayerResponse
    xp_gain: int
    gold_gain: int
    leveled_up: bool
    cards_used: int


class AbandonQuestResponse(BaseModel):
    penalty_gold: int
    rival_gain: int


class RewardCreate(BaseModel):
    name: str
    cost: int
    description: str = ""


class RewardResponse(BaseModel):
    id: int
    name: str
    cost: int
    description: str = ""

    class Config:
        orm_mode = True


class ActionResult(BaseModel):
    success: bool
    message: str


class RivalGrowthResponse(BaseModel):
    leveled_up: bool
    xp_gained: int


class SyncState(BaseModel):
    player: PlayerResponse
    rival: RivalResponse
    quests: List[QuestResponse]
    rewards: List[RewardResponse]
    config: ConfigPayload
