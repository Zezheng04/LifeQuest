import sqlite3
import random
import os
import platform
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from models import Player, Rival, Quest, QuestStatus, QuestType, QuestAttribute, Reward, RivalTier, QuestFrequency

def calc_next_level_xp(level: int, base: int = 100, exponent: float = 1.2) -> int:
    return max(base, int(base * (level ** exponent)))

class DatabaseManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = self._get_system_db_path()
        else:
            self.db_path = Path(db_path)
        
        self._ensure_connection()

    def _get_system_db_path(self) -> Path:
        app_name = "LifeQuest"
        if platform.system() == "Windows":
            base_path = os.getenv("APPDATA")
        else:
            base_path = os.path.expanduser("~")
        
        data_dir = os.path.join(base_path, app_name)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        return Path(os.path.join(data_dir, "lifequest.db"))

    def _ensure_connection(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate_schema(self):
        with self.get_connection() as conn:
            try: conn.execute("SELECT duration FROM quest LIMIT 1")
            except: 
                try: conn.execute("ALTER TABLE quest ADD COLUMN duration INTEGER DEFAULT 0")
                except: pass
            
            try: conn.execute("SELECT tier FROM rival LIMIT 1")
            except: 
                try: conn.execute(f"ALTER TABLE rival ADD COLUMN tier TEXT DEFAULT '{RivalTier.NORMAL.value}'")
                except: pass
            
            try: conn.execute("SELECT frequency FROM quest LIMIT 1")
            except:
                try: 
                    conn.execute(f"ALTER TABLE quest ADD COLUMN frequency TEXT DEFAULT '{QuestFrequency.ONCE.value}'")
                except: pass

            try: conn.execute("SELECT active_days FROM quest LIMIT 1")
            except:
                try: conn.execute("ALTER TABLE quest ADD COLUMN active_days TEXT DEFAULT ''")
                except: pass
            
            try: conn.execute("SELECT streak_days FROM player LIMIT 1")
            except:
                try: conn.execute("ALTER TABLE player ADD COLUMN streak_days INTEGER DEFAULT 0")
                except: pass
            
            try: conn.execute("SELECT last_active_date FROM player LIMIT 1")
            except:
                try: conn.execute("ALTER TABLE player ADD COLUMN last_active_date TEXT DEFAULT ''")
                except: pass

            # V3.1+ 新增：断电保护卡字段
            try: conn.execute("SELECT streak_freeze_cards FROM player LIMIT 1")
            except:
                try: conn.execute("ALTER TABLE player ADD COLUMN streak_freeze_cards INTEGER DEFAULT 0")
                except: pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS reward (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, cost INTEGER NOT NULL, description TEXT
                )
            """)

    def create_tables(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(f"""
                CREATE TABLE IF NOT EXISTS player (
                    id INTEGER PRIMARY KEY CHECK (id = 1), 
                    level INTEGER NOT NULL DEFAULT 1, 
                    xp INTEGER NOT NULL DEFAULT 0, 
                    next_level_xp INTEGER NOT NULL DEFAULT 100, 
                    gold INTEGER NOT NULL DEFAULT 0, 
                    perception REAL NOT NULL DEFAULT 5.0, 
                    insight REAL NOT NULL DEFAULT 5.0, 
                    logic REAL NOT NULL DEFAULT 5.0, 
                    charisma REAL NOT NULL DEFAULT 5.0,
                    streak_days INTEGER DEFAULT 0,
                    last_active_date TEXT DEFAULT '',
                    streak_freeze_cards INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS rival (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
                    next_level_xp INTEGER NOT NULL DEFAULT 100,
                    perception REAL NOT NULL DEFAULT 5.0, insight REAL NOT NULL DEFAULT 5.0,
                    logic REAL NOT NULL DEFAULT 5.0, charisma REAL NOT NULL DEFAULT 5.0,
                    last_login_date TEXT NOT NULL, tier TEXT DEFAULT '{RivalTier.NORMAL.value}'
                );
                CREATE TABLE IF NOT EXISTS quest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, description TEXT NOT NULL, quest_type TEXT NOT NULL,
                    attribute TEXT NOT NULL, difficulty INTEGER NOT NULL, status TEXT NOT NULL DEFAULT '未完成',
                    completed_at TEXT, duration INTEGER DEFAULT 0,
                    frequency TEXT DEFAULT '{QuestFrequency.ONCE.value}',
                    active_days TEXT DEFAULT ''
                );
            """)
        self._migrate_schema()

    def check_daily_reset(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM quest WHERE frequency = ?", (QuestFrequency.RECURRING.value,))
            quests = [Quest.from_db_row(row) for row in cursor.fetchall()]
            
            for q in quests:
                last_date = "1970-01-01"
                if q.completed_at:
                    last_date = q.completed_at.split(" ")[0]
                
                if last_date != today_str:
                    if q.status == QuestStatus.COMPLETE:
                        conn.execute(
                            """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at, duration, frequency, active_days)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (q.name, q.description, q.quest_type.value, q.attribute.value, q.difficulty, 
                             QuestStatus.COMPLETE.value, q.completed_at, q.duration, 
                             QuestFrequency.ONCE.value, "")
                        )
                    elif q.status == QuestStatus.INCOMPLETE:
                        conn.execute(
                            """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at, duration, frequency, active_days)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (q.name, q.description, q.quest_type.value, q.attribute.value, q.difficulty, 
                             QuestStatus.EXPIRED.value, f"{last_date} 23:59", 0, 
                             QuestFrequency.ONCE.value, "")
                        )

                    conn.execute(
                        "UPDATE quest SET status = ?, completed_at = NULL, duration = 0 WHERE id = ?",
                        (QuestStatus.INCOMPLETE.value, q.id)
                    )

    def init_player_if_missing(self) -> None:
        self.check_daily_reset()
        with self.get_connection() as conn:
            if conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone() is None:
                conn.execute(
                    """INSERT INTO player (id, level, xp, next_level_xp, gold, perception, insight, logic, charisma, streak_days, last_active_date, streak_freeze_cards)
                       VALUES (1, 1, 0, ?, 0, 5.0, 5.0, 5.0, 5.0, 0, '', 0)""", (calc_next_level_xp(1),)
                )
            
            now = datetime.now()
            now_str = now.isoformat()
            row = conn.execute("SELECT * FROM rival WHERE id = 1").fetchone()
            
            if row is None:
                conn.execute(
                    """INSERT INTO rival (id, level, xp, next_level_xp, perception, insight, logic, charisma, last_login_date, tier)
                       VALUES (1, 1, 0, ?, 5.5, 5.5, 5.5, 5.5, ?, ?)""",
                    (calc_next_level_xp(1), now_str, RivalTier.NORMAL.value),
                )
            else:
                last_date = datetime.fromisoformat(row["last_login_date"])
                tier_val = row["tier"]
                multiplier = 1.0
                if "0.5x" in tier_val: multiplier = 0.5
                elif "1.5x" in tier_val: multiplier = 1.5
                elif "2.0x" in tier_val: multiplier = 2.0
                
                days_diff = (now.date() - last_date.date()).days
                if days_diff > 0:
                    rival = Rival.from_db_row(tuple(row))
                    total_xp = 0
                    for _ in range(days_diff):
                        events = random.randint(2, 4)
                        for _ in range(events):
                            total_xp += int(random.randint(30, 50) * multiplier)
                    rival.xp += total_xp
                    while rival.xp >= rival.next_level_xp:
                        rival.xp -= rival.next_level_xp
                        rival.level += 1
                        rival.next_level_xp = calc_next_level_xp(rival.level)
                    rival.last_login_date = now_str
                    self.update_rival(rival)
                else:
                    conn.execute("UPDATE rival SET last_login_date = ? WHERE id = 1", (now_str,))

    def rival_random_growth(self) -> Tuple[bool, int]:
        r = self.get_rival()
        if not r: return False, 0
        
        multiplier = 1.0
        if "0.5x" in r.tier: multiplier = 0.5
        elif "1.5x" in r.tier: multiplier = 1.5
        elif "2.0x" in r.tier: multiplier = 2.0

        xp_gain = int(random.randint(5, 15) * multiplier)
        r.xp += xp_gain
        leveled = False
        while r.xp >= r.next_level_xp:
            r.xp -= r.next_level_xp
            r.level += 1
            r.next_level_xp = calc_next_level_xp(r.level)
            leveled = True
        
        r.last_login_date = datetime.now().isoformat()
        self.update_rival(r)
        return leveled, xp_gain

    def get_player(self) -> Optional[Player]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
            if not row: return None
            
            p_data = dict(row)
            p = Player(
                id=p_data['id'], level=p_data['level'], xp=p_data['xp'],
                next_level_xp=p_data['next_level_xp'], gold=p_data['gold'],
                perception=p_data['perception'], insight=p_data['insight'],
                logic=p_data['logic'], charisma=p_data['charisma']
            )
            
            setattr(p, "streak_days", p_data.get("streak_days", 0))
            setattr(p, "last_active_date", p_data.get("last_active_date", ""))
            setattr(p, "streak_freeze_cards", p_data.get("streak_freeze_cards", 0))
            return p

    def update_player(self, p: Player) -> None:
        s_days = getattr(p, "streak_days", 0)
        l_date = getattr(p, "last_active_date", "")
        f_cards = getattr(p, "streak_freeze_cards", 0)
        
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE player SET level=?, xp=?, next_level_xp=?, gold=?,
                   perception=?, insight=?, logic=?, charisma=?, streak_days=?, last_active_date=?, streak_freeze_cards=?
                   WHERE id = 1""",
                (p.level, p.xp, p.next_level_xp, p.gold, p.perception, p.insight, 
                 p.logic, p.charisma, s_days, l_date, f_cards)
            )

    def get_rival(self) -> Optional[Rival]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM rival WHERE id = 1").fetchone()
            return Rival.from_db_row(tuple(row)) if row else None

    def update_rival(self, r: Rival) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE rival SET level=?, xp=?, next_level_xp=?,
                   perception=?, insight=?, logic=?, charisma=?, last_login_date=?, tier=?
                   WHERE id = 1""",
                (r.level, r.xp, r.next_level_xp, r.perception, r.insight, r.logic, 
                 r.charisma, r.last_login_date, r.tier)
            )

    def insert_quest(self, q: Quest) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at, duration, frequency, active_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", q.to_db_row())
            return cur.lastrowid

    def update_quest(self, q: Quest) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE quest SET name=?, description=?, quest_type=?, attribute=?, difficulty=?, frequency=?, active_days=?
                   WHERE id=?""",
                (q.name, q.description, q.quest_type.value, q.attribute.value, q.difficulty, q.frequency.value, q.active_days, q.id)
            )

    def get_quest(self, qid: int) -> Optional[Quest]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM quest WHERE id = ?", (qid,)).fetchone()
            return Quest.from_db_row(tuple(row)) if row else None

    def list_quests(self, status: Optional[QuestStatus] = None) -> List[Quest]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM quest WHERE 1=1"
            params = []
            if status:
                sql += " AND status = ?"
                params.append(status.value)
            
            rows = conn.execute(sql, params).fetchall()
            all_quests = [Quest.from_db_row(tuple(r)) for r in rows]
            
            final_quests = []
            weekday_now = str(datetime.now().isoweekday())
            
            for q in all_quests:
                if status == QuestStatus.INCOMPLETE and q.frequency == QuestFrequency.RECURRING:
                    if q.active_days and weekday_now not in q.active_days:
                        continue
                final_quests.append(q)
            return final_quests

    def add_reward(self, name: str, cost: int, desc: str = ""):
        with self.get_connection() as conn:
            conn.execute("INSERT INTO reward (name, cost, description) VALUES (?, ?, ?)", (name, cost, desc))

    def list_rewards(self) -> List[Reward]:
        with self.get_connection() as conn:
            try:
                rows = conn.execute("SELECT * FROM reward").fetchall()
                return [Reward(r["id"], r["name"], r["cost"], r["description"]) for r in rows]
            except: return []

    def delete_reward(self, rid: int):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM reward WHERE id = ?", (rid,))

    def buy_reward(self, reward_id: int) -> Tuple[bool, str]:
        with self.get_connection() as conn:
            p = self.get_player()
            r_row = conn.execute("SELECT * FROM reward WHERE id = ?", (reward_id,)).fetchone()
            if not r_row: return False, "商品不存在"
            if p.gold < r_row["cost"]: return False, f"金币不足 (需 {r_row['cost']})"
            p.gold -= r_row["cost"]
            self.update_player(p)
            return True, f"购买成功：{r_row['name']}"

    # 新增：购买断电保护卡
    def buy_freeze_card(self) -> Tuple[bool, str]:
        with self.get_connection() as conn:
            p = self.get_player()
            if p.gold < 500: return False, "金币不足，购买保护卡需要 500 🪙"
            p.gold -= 500
            cards = getattr(p, "streak_freeze_cards", 0)
            setattr(p, "streak_freeze_cards", cards + 1)
            self.update_player(p)
            return True, "购买成功：🛡️ 连击断电保护卡 +1"

    def complete_quest(self, quest_id: int, duration_mins: int = 0) -> Tuple[Optional[Player], int, int, bool, int]:
        """ 返回：(玩家对象, 获得XP, 获得金币, 是否升级, 消耗的断电保护卡数量) """
        quest = self.get_quest(quest_id)
        if not quest or quest.status == QuestStatus.COMPLETE: return None, 0, 0, False, 0
        
        player = self.get_player()
        
        today_date = datetime.now()
        today_str = today_date.strftime("%Y-%m-%d")
        
        current_streak = getattr(player, "streak_days", 0)
        last_active = getattr(player, "last_active_date", "")
        freeze_cards = getattr(player, "streak_freeze_cards", 0)
        
        cards_used = 0

        # --- 包含保护卡机制的连击判定 ---
        if last_active != today_str:
            if last_active:
                last_date = datetime.strptime(last_active, "%Y-%m-%d")
                days_diff = (today_date.date() - last_date.date()).days
                
                if days_diff == 1:
                    current_streak += 1 # 正常连击
                elif days_diff > 1:
                    missed_days = days_diff - 1
                    # 检查是否有足够的断电保护卡来填补空缺
                    if freeze_cards >= missed_days:
                        freeze_cards -= missed_days
                        cards_used = missed_days
                        current_streak += 1 # 消耗卡片，连击得以延续！
                        setattr(player, "streak_freeze_cards", freeze_cards)
                    else:
                        current_streak = 1 # 卡片不够，无情重置
            else:
                current_streak = 1
            
            setattr(player, "streak_days", current_streak)
            setattr(player, "last_active_date", today_str)

        bonus_ratio = min(0.5, getattr(player, "streak_days", 0) * 0.01)
        base_xp = 20 + quest.difficulty * 15
        base_gold = 10 + quest.difficulty * 5
        
        xp_gain = int(base_xp * (1 + bonus_ratio))
        gold_gain = int(base_gold * (1 + bonus_ratio))
        attr_gain = 1 if quest.difficulty >= 3 else 0

        player.xp += xp_gain
        player.gold += gold_gain
        
        if quest.attribute != QuestAttribute.OTHER:
            if quest.attribute == QuestAttribute.PERCEPTION: player.perception += attr_gain
            elif quest.attribute == QuestAttribute.INSIGHT: player.insight += attr_gain
            elif quest.attribute == QuestAttribute.LOGIC: player.logic += attr_gain
            elif quest.attribute == QuestAttribute.CHARISMA: player.charisma += attr_gain
        
        leveled_up = False
        while player.xp >= player.next_level_xp:
            player.xp -= player.next_level_xp
            player.level += 1
            player.next_level_xp = calc_next_level_xp(player.level)
            leveled_up = True
            
        self.update_player(player)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.get_connection() as conn:
            conn.execute("UPDATE quest SET status = ?, completed_at = ?, duration = ? WHERE id = ?", 
                (QuestStatus.COMPLETE.value, now_str, duration_mins, quest_id))
            
        return player, xp_gain, gold_gain, leveled_up, cards_used

    def abandon_quest(self, quest_id: int) -> Tuple[int, int]:
        quest = self.get_quest(quest_id)
        if not quest: return 0, 0
        penalty_gold = quest.difficulty * 5
        rival_gain = quest.difficulty * 10
        
        p = self.get_player()
        p.gold = max(0, p.gold - penalty_gold)
        self.update_player(p)
        
        r = self.get_rival()
        r.xp += rival_gain
        while r.xp >= r.next_level_xp:
            r.xp -= r.next_level_xp
            r.level += 1
            r.next_level_xp = calc_next_level_xp(r.level)
        self.update_rival(r)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.get_connection() as conn:
            conn.execute("UPDATE quest SET status = ?, completed_at = ? WHERE id = ?", 
                         (QuestStatus.ABANDONED.value, now_str, quest_id))
        return penalty_gold, rival_gain

    def get_today_study_time(self) -> int:
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            try:
                row = conn.execute("SELECT SUM(duration) as total FROM quest WHERE completed_at LIKE ? AND status = ?", 
                    (f"{today_prefix}%", QuestStatus.COMPLETE.value)).fetchone()
                return row["total"] if row["total"] else 0
            except: return 0