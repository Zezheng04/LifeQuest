import random
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from .auth import authenticate_user, create_access_token, get_current_user, get_password_hash
from .database import Base, engine, get_db
from .models import Quest, Reward, Rival, User
from .schemas import (
    AbandonQuestResponse,
    ActionResult,
    CompleteQuestRequest,
    CompleteQuestResponse,
    ConfigPayload,
    LoginRequest,
    PlayerResponse,
    QuestCreate,
    QuestResponse,
    QuestUpdate,
    RewardCreate,
    RewardResponse,
    RivalGrowthResponse,
    RivalResponse,
    RivalUpdate,
    SyncState,
    Token,
    UserCreate,
    UserResponse,
)


app = FastAPI(title="LifeQuest API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def calc_next_level_xp(level: int, base: int = 100, exponent: float = 1.2) -> int:
    return max(base, int(base * (level ** exponent)))


def get_rival_multiplier(tier: str) -> float:
    if "0.5x" in tier:
        return 0.5
    if "1.5x" in tier:
        return 1.5
    if "2.0x" in tier:
        return 2.0
    return 1.0


def player_from_user(user: User) -> PlayerResponse:
    return PlayerResponse(
        id=user.id,
        level=user.level,
        xp=user.xp,
        next_level_xp=user.next_level_xp,
        gold=user.gold,
        perception=user.perception,
        insight=user.insight,
        logic=user.logic,
        charisma=user.charisma,
        streak_days=user.streak_days,
        last_active_date=user.last_active_date,
        streak_freeze_cards=user.streak_freeze_cards,
    )


def config_from_user(user: User) -> ConfigPayload:
    return ConfigPayload(
        target_name=user.target_name,
        target_date=user.target_date,
        attr1=user.attr1,
        attr2=user.attr2,
        attr3=user.attr3,
        attr4=user.attr4,
    )


def user_response_from_user(user: User) -> UserResponse:
    return UserResponse(id=user.id, username=user.username)


def rival_response_from_rival(rival: Rival) -> RivalResponse:
    return RivalResponse(
        id=rival.id,
        level=rival.level,
        xp=rival.xp,
        next_level_xp=rival.next_level_xp,
        perception=rival.perception,
        insight=rival.insight,
        logic=rival.logic,
        charisma=rival.charisma,
        last_login_date=rival.last_login_date,
        tier=rival.tier,
    )


def quest_response_from_quest(quest: Quest) -> QuestResponse:
    return QuestResponse(
        id=quest.id,
        name=quest.name,
        description=quest.description,
        quest_type=quest.quest_type,
        attribute=quest.attribute,
        difficulty=quest.difficulty,
        status=quest.status,
        completed_at=quest.completed_at,
        duration=quest.duration,
        frequency=quest.frequency,
        active_days=quest.active_days,
    )


def reward_response_from_reward(reward: Reward) -> RewardResponse:
    return RewardResponse(
        id=reward.id,
        name=reward.name,
        cost=reward.cost,
        description=reward.description,
    )


def get_or_create_rival(db: Session, user: User) -> Rival:
    rival = db.query(Rival).filter(Rival.user_id == user.id).first()
    if rival is None:
        rival = Rival(
            user_id=user.id,
            level=1,
            xp=0,
            next_level_xp=calc_next_level_xp(1),
            perception=5.5,
            insight=5.5,
            logic=5.5,
            charisma=5.5,
            last_login_date=datetime.now().isoformat(),
            tier="普通人 (1.0x)",
        )
        db.add(rival)
        db.commit()
        db.refresh(rival)
    return rival


def apply_daily_reset(db: Session, user: User) -> None:
    today_str = datetime.now().strftime("%Y-%m-%d")
    recurring_quests = (
        db.query(Quest)
        .filter(Quest.user_id == user.id, Quest.frequency == "长期循环")
        .all()
    )

    changed = False
    for quest in recurring_quests:
        last_date = "1970-01-01"
        if quest.completed_at:
            last_date = quest.completed_at.split(" ")[0]

        if last_date == today_str:
            continue

        if quest.status == "已完成":
            db.add(
                Quest(
                    user_id=user.id,
                    name=quest.name,
                    description=quest.description,
                    quest_type=quest.quest_type,
                    attribute=quest.attribute,
                    difficulty=quest.difficulty,
                    status="已完成",
                    completed_at=quest.completed_at,
                    duration=quest.duration,
                    frequency="一次性",
                    active_days="",
                )
            )
            changed = True
        elif quest.status == "未完成":
            db.add(
                Quest(
                    user_id=user.id,
                    name=quest.name,
                    description=quest.description,
                    quest_type=quest.quest_type,
                    attribute=quest.attribute,
                    difficulty=quest.difficulty,
                    status="已过期",
                    completed_at=f"{last_date} 23:59",
                    duration=0,
                    frequency="一次性",
                    active_days="",
                )
            )
            changed = True

        quest.status = "未完成"
        quest.completed_at = None
        quest.duration = 0
        changed = True

    if changed:
        db.commit()


def get_user_quest(db: Session, user: User, quest_id: int) -> Quest:
    quest = (
        db.query(Quest)
        .filter(Quest.id == quest_id, Quest.user_id == user.id)
        .first()
    )
    if quest is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return quest


def get_user_reward(db: Session, user: User, reward_id: int) -> Reward:
    reward = (
        db.query(Reward)
        .filter(Reward.id == reward_id, Reward.user_id == user.id)
        .first()
    )
    if reward is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return reward


def issue_token_for_user(user: User) -> Token:
    return Token(access_token=create_access_token({"sub": str(user.id)}))


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        next_level_xp=calc_next_level_xp(1),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    rival = Rival(
        user_id=user.id,
        level=1,
        xp=0,
        next_level_xp=calc_next_level_xp(1),
        perception=5.5,
        insight=5.5,
        logic=5.5,
        charisma=5.5,
        last_login_date=datetime.now().isoformat(),
        tier="普通人 (1.0x)",
    )
    db.add(rival)
    db.commit()
    return user_response_from_user(user)


@app.post("/auth/login", response_model=Token)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return issue_token_for_user(user)


@app.post("/auth/token", response_model=Token)
def login_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return issue_token_for_user(user)


@app.get("/users/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return user_response_from_user(current_user)


@app.get("/config", response_model=ConfigPayload)
def get_config(current_user: User = Depends(get_current_user)):
    return config_from_user(current_user)


@app.put("/config", response_model=ConfigPayload)
def update_config(payload: ConfigPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.target_name = payload.target_name
    current_user.target_date = payload.target_date
    current_user.attr1 = payload.attr1
    current_user.attr2 = payload.attr2
    current_user.attr3 = payload.attr3
    current_user.attr4 = payload.attr4
    db.commit()
    db.refresh(current_user)
    return config_from_user(current_user)


@app.post("/maintenance/daily-reset", response_model=ActionResult)
def run_daily_reset(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    apply_daily_reset(db, current_user)
    return ActionResult(success=True, message="每日重置检查完成")


@app.get("/player", response_model=PlayerResponse)
def get_player(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apply_daily_reset(db, current_user)
    return player_from_user(current_user)


@app.get("/rival", response_model=RivalResponse)
def get_rival(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    apply_daily_reset(db, current_user)
    return rival_response_from_rival(get_or_create_rival(db, current_user))


@app.put("/rival", response_model=RivalResponse)
def update_rival(payload: RivalUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rival = get_or_create_rival(db, current_user)
    rival.tier = payload.tier
    db.commit()
    db.refresh(rival)
    return rival_response_from_rival(rival)


@app.post("/rival/random-growth", response_model=RivalGrowthResponse)
def rival_random_growth(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rival = get_or_create_rival(db, current_user)
    multiplier = get_rival_multiplier(rival.tier)
    xp_gain = int(random.randint(5, 15) * multiplier)
    rival.xp += xp_gain
    leveled_up = False

    while rival.xp >= rival.next_level_xp:
        rival.xp -= rival.next_level_xp
        rival.level += 1
        rival.next_level_xp = calc_next_level_xp(rival.level)
        leveled_up = True

    rival.last_login_date = datetime.now().isoformat()
    db.commit()
    return RivalGrowthResponse(leveled_up=leveled_up, xp_gained=xp_gain)


@app.get("/stats/today-study-time")
def get_today_study_time(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    total = (
        db.query(func.sum(Quest.duration))
        .filter(
            Quest.user_id == current_user.id,
            Quest.status == "已完成",
            Quest.completed_at.like(f"{today_prefix}%"),
        )
        .scalar()
    )
    return {"total_minutes": int(total or 0)}


@app.get("/quests", response_model=list[QuestResponse])
def list_quests(
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apply_daily_reset(db, current_user)
    query = db.query(Quest).filter(Quest.user_id == current_user.id)
    if status_value:
        query = query.filter(Quest.status == status_value)
    quests = query.order_by(Quest.id.asc()).all()

    if status_value == "未完成":
        weekday_now = str(datetime.now().isoweekday())
        quests = [
            quest for quest in quests
            if quest.frequency != "长期循环" or not quest.active_days or weekday_now in quest.active_days
        ]

    return [quest_response_from_quest(quest) for quest in quests]


@app.post("/quests", response_model=QuestResponse, status_code=status.HTTP_201_CREATED)
def create_quest(payload: QuestCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    quest = Quest(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        quest_type=payload.quest_type,
        attribute=payload.attribute,
        difficulty=payload.difficulty,
        frequency=payload.frequency,
        active_days=payload.active_days,
    )
    db.add(quest)
    db.commit()
    db.refresh(quest)
    return quest_response_from_quest(quest)


@app.put("/quests/{quest_id}", response_model=QuestResponse)
def update_quest(
    quest_id: int,
    payload: QuestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quest = get_user_quest(db, current_user, quest_id)
    quest.name = payload.name
    quest.description = payload.description
    quest.quest_type = payload.quest_type
    quest.attribute = payload.attribute
    quest.difficulty = payload.difficulty
    quest.frequency = payload.frequency
    quest.active_days = payload.active_days
    db.commit()
    db.refresh(quest)
    return quest_response_from_quest(quest)


@app.post("/quests/{quest_id}/complete", response_model=CompleteQuestResponse)
def complete_quest(
    quest_id: int,
    payload: CompleteQuestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    quest = get_user_quest(db, current_user, quest_id)
    if quest.status == "已完成":
        raise HTTPException(status_code=400, detail="任务已完成")

    today_date = datetime.now()
    today_str = today_date.strftime("%Y-%m-%d")
    current_streak = current_user.streak_days
    last_active = current_user.last_active_date
    freeze_cards = current_user.streak_freeze_cards
    cards_used = 0

    if last_active != today_str:
        if last_active:
            last_date = datetime.strptime(last_active, "%Y-%m-%d")
            days_diff = (today_date.date() - last_date.date()).days
            if days_diff == 1:
                current_streak += 1
            elif days_diff > 1:
                missed_days = days_diff - 1
                if freeze_cards >= missed_days:
                    freeze_cards -= missed_days
                    cards_used = missed_days
                    current_streak += 1
                else:
                    current_streak = 1
        else:
            current_streak = 1

        current_user.streak_days = current_streak
        current_user.last_active_date = today_str
        current_user.streak_freeze_cards = freeze_cards

    bonus_ratio = min(0.5, current_user.streak_days * 0.01)
    base_xp = 20 + quest.difficulty * 15
    base_gold = 10 + quest.difficulty * 5
    xp_gain = int(base_xp * (1 + bonus_ratio))
    gold_gain = int(base_gold * (1 + bonus_ratio))
    attr_gain = 1 if quest.difficulty >= 3 else 0

    current_user.xp += xp_gain
    current_user.gold += gold_gain

    if quest.attribute == "Perception":
        current_user.perception += attr_gain
    elif quest.attribute == "Insight":
        current_user.insight += attr_gain
    elif quest.attribute == "Logic":
        current_user.logic += attr_gain
    elif quest.attribute == "Charisma":
        current_user.charisma += attr_gain

    leveled_up = False
    while current_user.xp >= current_user.next_level_xp:
        current_user.xp -= current_user.next_level_xp
        current_user.level += 1
        current_user.next_level_xp = calc_next_level_xp(current_user.level)
        leveled_up = True

    quest.status = "已完成"
    quest.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    quest.duration = payload.duration_mins
    db.commit()
    db.refresh(current_user)

    return CompleteQuestResponse(
        player=player_from_user(current_user),
        xp_gain=xp_gain,
        gold_gain=gold_gain,
        leveled_up=leveled_up,
        cards_used=cards_used,
    )


@app.post("/quests/{quest_id}/abandon", response_model=AbandonQuestResponse)
def abandon_quest(quest_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    quest = get_user_quest(db, current_user, quest_id)
    penalty_gold = quest.difficulty * 5
    rival_gain = quest.difficulty * 10

    current_user.gold = max(0, current_user.gold - penalty_gold)
    rival = get_or_create_rival(db, current_user)
    rival.xp += rival_gain
    while rival.xp >= rival.next_level_xp:
        rival.xp -= rival.next_level_xp
        rival.level += 1
        rival.next_level_xp = calc_next_level_xp(rival.level)

    quest.status = "已放弃"
    quest.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.commit()
    return AbandonQuestResponse(penalty_gold=penalty_gold, rival_gain=rival_gain)


@app.get("/rewards", response_model=list[RewardResponse])
def list_rewards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rewards = (
        db.query(Reward)
        .filter(Reward.user_id == current_user.id)
        .order_by(Reward.id.asc())
        .all()
    )
    return [reward_response_from_reward(reward) for reward in rewards]


@app.post("/rewards", response_model=RewardResponse, status_code=status.HTTP_201_CREATED)
def create_reward(payload: RewardCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reward = Reward(
        user_id=current_user.id,
        name=payload.name,
        cost=payload.cost,
        description=payload.description,
    )
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return reward_response_from_reward(reward)


@app.delete("/rewards/{reward_id}", response_model=ActionResult)
def delete_reward(reward_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reward = get_user_reward(db, current_user, reward_id)
    db.delete(reward)
    db.commit()
    return ActionResult(success=True, message="商品已删除")


@app.post("/rewards/freeze-card/buy", response_model=ActionResult)
def buy_freeze_card(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.gold < 500:
        return ActionResult(success=False, message="金币不足，购买保护卡需要 500 🪙")

    current_user.gold -= 500
    current_user.streak_freeze_cards += 1
    db.commit()
    return ActionResult(success=True, message="购买成功：🛡️ 连击断电保护卡 +1")


@app.post("/rewards/{reward_id}/buy", response_model=ActionResult)
def buy_reward(reward_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reward = get_user_reward(db, current_user, reward_id)
    if current_user.gold < reward.cost:
        return ActionResult(success=False, message=f"金币不足 (需 {reward.cost})")

    current_user.gold -= reward.cost
    db.commit()
    return ActionResult(success=True, message=f"购买成功：{reward.name}")


@app.get("/sync/export", response_model=SyncState)
def export_sync_state(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    apply_daily_reset(db, current_user)
    rival = get_or_create_rival(db, current_user)
    quests = db.query(Quest).filter(Quest.user_id == current_user.id).order_by(Quest.id.asc()).all()
    rewards = db.query(Reward).filter(Reward.user_id == current_user.id).order_by(Reward.id.asc()).all()
    return SyncState(
        player=player_from_user(current_user),
        rival=rival_response_from_rival(rival),
        quests=[quest_response_from_quest(q) for q in quests],
        rewards=[reward_response_from_reward(r) for r in rewards],
        config=config_from_user(current_user),
    )


@app.post("/sync/import", response_model=ActionResult)
def import_sync_state(payload: SyncState, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rival = get_or_create_rival(db, current_user)

    current_user.level = payload.player.level
    current_user.xp = payload.player.xp
    current_user.next_level_xp = payload.player.next_level_xp
    current_user.gold = payload.player.gold
    current_user.perception = payload.player.perception
    current_user.insight = payload.player.insight
    current_user.logic = payload.player.logic
    current_user.charisma = payload.player.charisma
    current_user.streak_days = payload.player.streak_days
    current_user.last_active_date = payload.player.last_active_date
    current_user.streak_freeze_cards = payload.player.streak_freeze_cards

    current_user.target_name = payload.config.target_name
    current_user.target_date = payload.config.target_date
    current_user.attr1 = payload.config.attr1
    current_user.attr2 = payload.config.attr2
    current_user.attr3 = payload.config.attr3
    current_user.attr4 = payload.config.attr4

    rival.level = payload.rival.level
    rival.xp = payload.rival.xp
    rival.next_level_xp = payload.rival.next_level_xp
    rival.perception = payload.rival.perception
    rival.insight = payload.rival.insight
    rival.logic = payload.rival.logic
    rival.charisma = payload.rival.charisma
    rival.last_login_date = payload.rival.last_login_date
    rival.tier = payload.rival.tier

    db.query(Quest).filter(Quest.user_id == current_user.id).delete(synchronize_session=False)
    db.query(Reward).filter(Reward.user_id == current_user.id).delete(synchronize_session=False)

    for quest in payload.quests:
        db.add(
            Quest(
                user_id=current_user.id,
                name=quest.name,
                description=quest.description,
                quest_type=quest.quest_type,
                attribute=quest.attribute,
                difficulty=quest.difficulty,
                status=quest.status,
                completed_at=quest.completed_at,
                duration=quest.duration,
                frequency=quest.frequency,
                active_days=quest.active_days,
            )
        )

    for reward in payload.rewards:
        db.add(
            Reward(
                user_id=current_user.id,
                name=reward.name,
                cost=reward.cost,
                description=reward.description,
            )
        )

    db.commit()
    return ActionResult(success=True, message="本地数据已同步到云端")
