import sqlite3
import random
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from models import Player, Rival, Quest, QuestStatus, QuestType, QuestAttribute, Reward, RivalTier

def calc_next_level_xp(level: int, base: int = 100, exponent: float = 1.2) -> int:
    return max(base, int(base * (level ** exponent)))

class DatabaseManager:
    def __init__(self, db_path: str = "lifequest.db"):
        self.db_path = Path(db_path)
        self._ensure_connection()

    def _ensure_connection(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate_schema(self):
        with self.get_connection() as conn:
            try:
                conn.execute("SELECT duration FROM quest LIMIT 1")
            except sqlite3.OperationalError:
                try: conn.execute("ALTER TABLE quest ADD COLUMN duration INTEGER DEFAULT 0")
                except: pass
            
            try:
                conn.execute("SELECT tier FROM rival LIMIT 1")
            except sqlite3.OperationalError:
                try: conn.execute(f"ALTER TABLE rival ADD COLUMN tier TEXT DEFAULT '{RivalTier.NORMAL.value}'")
                except: pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS reward (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    description TEXT
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
                    charisma REAL NOT NULL DEFAULT 5.0
                );

                CREATE TABLE IF NOT EXISTS rival (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    level INTEGER NOT NULL DEFAULT 1,
                    xp INTEGER NOT NULL DEFAULT 0,
                    next_level_xp INTEGER NOT NULL DEFAULT 100,
                    perception REAL NOT NULL DEFAULT 5.0,
                    insight REAL NOT NULL DEFAULT 5.0,
                    logic REAL NOT NULL DEFAULT 5.0,
                    charisma REAL NOT NULL DEFAULT 5.0,
                    last_login_date TEXT NOT NULL,
                    tier TEXT DEFAULT '{RivalTier.NORMAL.value}'
                );

                CREATE TABLE IF NOT EXISTS quest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    quest_type TEXT NOT NULL,
                    attribute TEXT NOT NULL,
                    difficulty INTEGER NOT NULL CHECK (difficulty >= 1 AND difficulty <= 5),
                    status TEXT NOT NULL DEFAULT '未完成',
                    completed_at TEXT,
                    duration INTEGER DEFAULT 0
                );
            """)
        self._migrate_schema()

    def init_player_if_missing(self) -> None:
        with self.get_connection() as conn:
            if conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone() is None:
                conn.execute(
                    """INSERT INTO player (id, level, xp, next_level_xp, gold, perception, insight, logic, charisma)
                       VALUES (1, 1, 0, ?, 0, 5.0, 5.0, 5.0, 5.0)""", (calc_next_level_xp(1),)
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
                    total_xp_gain = 0
                    total_attr_gain = 0.0
                    for _ in range(days_diff):
                        events = random.randint(2, 4)
                        for _ in range(events):
                            base_xp = random.randint(30, 50)
                            xp_gain = int(base_xp * multiplier)
                            total_xp_gain += xp_gain
                            total_attr_gain += (0.1 * multiplier)

                    rival.xp += total_xp_gain
                    rival.perception += total_attr_gain
                    rival.insight += total_attr_gain
                    rival.logic += total_attr_gain
                    rival.charisma += total_attr_gain
                    
                    while rival.xp >= rival.next_level_xp:
                        rival.xp -= rival.next_level_xp
                        rival.level += 1
                        rival.next_level_xp = calc_next_level_xp(rival.level)
                    
                    rival.last_login_date = now_str
                    self.update_rival(rival)
                else:
                    conn.execute("UPDATE rival SET last_login_date = ? WHERE id = 1", (now_str,))

    def get_player(self) -> Optional[Player]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
            return Player.from_db_row(tuple(row)) if row else None

    def update_player(self, p: Player) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE player SET level=?, xp=?, next_level_xp=?, gold=?,
                   perception=?, insight=?, logic=?, charisma=? WHERE id = 1""",
                (p.level, p.xp, p.next_level_xp, p.gold, p.perception, p.insight, p.logic, p.charisma)
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
                (r.level, r.xp, r.next_level_xp, r.perception, r.insight, r.logic, r.charisma, r.last_login_date, r.tier)
            )

    def insert_quest(self, q: Quest) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at, duration)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", q.to_db_row())
            return cur.lastrowid

    # --- 新增：更新任务信息 ---
    def update_quest(self, q: Quest) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE quest SET name=?, description=?, quest_type=?, attribute=?, difficulty=?
                   WHERE id=?""",
                (q.name, q.description, q.quest_type.value, q.attribute.value, q.difficulty, q.id)
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
            return [Quest.from_db_row(tuple(r)) for r in rows]

    # --- 商店系统逻辑 ---
    def add_reward(self, name: str, cost: int, desc: str = ""):
        with self.get_connection() as conn:
            conn.execute("INSERT INTO reward (name, cost, description) VALUES (?, ?, ?)", (name, cost, desc))

    def list_rewards(self) -> List[Reward]:
        with self.get_connection() as conn:
            try:
                rows = conn.execute("SELECT * FROM reward").fetchall()
                return [Reward(r["id"], r["name"], r["cost"], r["description"]) for r in rows]
            except:
                return []

    def delete_reward(self, rid: int):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM reward WHERE id = ?", (rid,))

    def buy_reward(self, reward_id: int) -> Tuple[bool, str]:
        with self.get_connection() as conn:
            p = self.get_player()
            r_row = conn.execute("SELECT * FROM reward WHERE id = ?", (reward_id,)).fetchone()
            if not r_row: return False, "商品不存在"
            
            cost = r_row["cost"]
            if p.gold < cost:
                return False, f"金币不足！需要 {cost}，你只有 {p.gold}"
            
            p.gold -= cost
            self.update_player(p)
            return True, f"购买成功：{r_row['name']}"

    def complete_quest(self, quest_id: int, duration_mins: int = 0) -> Tuple[Optional[Player], int, int]:
        quest = self.get_quest(quest_id)
        if not quest or quest.status == QuestStatus.COMPLETE:
            return None, 0, 0

        player = self.get_player()
        
        xp_gain = 20 + quest.difficulty * 15
        gold_gain = 10 + quest.difficulty * 5
        attr_gain = 1 if quest.difficulty >= 3 else 0

        player.xp += xp_gain
        player.gold += gold_gain
        
        # 逻辑修改：如果属性是 OTHER，则不加雷达属性
        if quest.attribute != QuestAttribute.OTHER:
            if quest.attribute == QuestAttribute.PERCEPTION: player.perception += attr_gain
            elif quest.attribute == QuestAttribute.INSIGHT: player.insight += attr_gain
            elif quest.attribute == QuestAttribute.LOGIC: player.logic += attr_gain
            elif quest.attribute == QuestAttribute.CHARISMA: player.charisma += attr_gain

        while player.xp >= player.next_level_xp:
            player.xp -= player.next_level_xp
            player.level += 1
            player.next_level_xp = calc_next_level_xp(player.level)

        self.update_player(player)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE quest SET status = ?, completed_at = ?, duration = ? WHERE id = ?", 
                (QuestStatus.COMPLETE.value, now_str, duration_mins, quest_id)
            )
            
        return player, xp_gain, gold_gain

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
                row = conn.execute(
                    "SELECT SUM(duration) as total FROM quest WHERE completed_at LIKE ? AND status = ?", 
                    (f"{today_prefix}%", QuestStatus.COMPLETE.value)
                ).fetchone()
                return row["total"] if row["total"] else 0
            except:
                return 0