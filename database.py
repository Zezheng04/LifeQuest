import sqlite3
import random
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from models import Player, Rival, Quest, QuestStatus, QuestType, QuestAttribute, Reward, RivalTier, QuestFrequency

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
        """V3.0 数据库自动升级：添加频率和活跃日"""
        with self.get_connection() as conn:
            # 升级1: duration
            try: conn.execute("SELECT duration FROM quest LIMIT 1")
            except: 
                try: conn.execute("ALTER TABLE quest ADD COLUMN duration INTEGER DEFAULT 0")
                except: pass
            
            # 升级2: tier
            try: conn.execute("SELECT tier FROM rival LIMIT 1")
            except: 
                try: conn.execute(f"ALTER TABLE rival ADD COLUMN tier TEXT DEFAULT '{RivalTier.NORMAL.value}'")
                except: pass
            
            # 升级3: frequency (V3)
            try: conn.execute("SELECT frequency FROM quest LIMIT 1")
            except:
                try: 
                    conn.execute(f"ALTER TABLE quest ADD COLUMN frequency TEXT DEFAULT '{QuestFrequency.ONCE.value}'")
                    # 默认让旧任务都变成一次性，防止逻辑混乱，用户可手动改
                except: pass

            # 升级4: active_days (V3)
            try: conn.execute("SELECT active_days FROM quest LIMIT 1")
            except:
                try: conn.execute("ALTER TABLE quest ADD COLUMN active_days TEXT DEFAULT ''")
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
                    level INTEGER NOT NULL DEFAULT 1, xp INTEGER NOT NULL DEFAULT 0,
                    next_level_xp INTEGER NOT NULL DEFAULT 100, gold INTEGER NOT NULL DEFAULT 0,
                    perception REAL NOT NULL DEFAULT 5.0, insight REAL NOT NULL DEFAULT 5.0,
                    logic REAL NOT NULL DEFAULT 5.0, charisma REAL NOT NULL DEFAULT 5.0
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

    # --- V3.0 核心逻辑：每日重置与过期处理 ---
    def check_daily_reset(self):
        """
        每次启动或跨天时调用。
        检查所有 '长期循环' 任务：
        1. 如果上次完成时间不是今天 -> 视为新的一天。
        2. 如果已完成 -> 存档一条副本到历史记录(状态=完成)，然后重置本体为(未完成)。
        3. 如果未完成且日期是昨天以前 -> 存档一条副本到历史记录(状态=过期)，然后重置本体。
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        with self.get_connection() as conn:
            # 获取所有循环任务
            cursor = conn.execute("SELECT * FROM quest WHERE frequency = ?", (QuestFrequency.RECURRING.value,))
            quests = [Quest.from_db_row(row) for row in cursor.fetchall()]
            
            for q in quests:
                last_date = "1970-01-01"
                if q.completed_at:
                    last_date = q.completed_at.split(" ")[0]
                
                # 如果最后更新日期不是今天（说明跨天了）
                if last_date != today_str:
                    # 情况 A: 昨天(或更早)完成了 -> 存档功绩
                    if q.status == QuestStatus.COMPLETE:
                        # 插入历史记录 (副本)
                        conn.execute(
                            """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at, duration, frequency, active_days)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (q.name, q.description, q.quest_type.value, q.attribute.value, q.difficulty, 
                             QuestStatus.COMPLETE.value, q.completed_at, q.duration, 
                             QuestFrequency.ONCE.value, "") # 历史记录本身不再循环
                        )
                    
                    # 情况 B: 昨天没做 -> 记录羞耻的过期 (仅当它是未完成状态时)
                    elif q.status == QuestStatus.INCOMPLETE:
                        # 插入过期记录
                        conn.execute(
                            """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at, duration, frequency, active_days)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (q.name, q.description, q.quest_type.value, q.attribute.value, q.difficulty, 
                             QuestStatus.EXPIRED.value, f"{last_date} 23:59", 0, 
                             QuestFrequency.ONCE.value, "")
                        )

                    # 重置本体任务状态为今天待办
                    conn.execute(
                        "UPDATE quest SET status = ?, completed_at = NULL, duration = 0 WHERE id = ?",
                        (QuestStatus.INCOMPLETE.value, q.id)
                    )

    def init_player_if_missing(self) -> None:
        # 先做每日重置检查
        self.check_daily_reset()
        
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
                # 离线结算逻辑 (保持原有)
                last_date = datetime.fromisoformat(row["last_login_date"])
                tier_val = row["tier"]
                multiplier = 1.0
                if "0.5x" in tier_val: multiplier = 0.5
                elif "1.5x" in tier_val: multiplier = 1.5
                elif "2.0x" in tier_val: multiplier = 2.0
                
                # 如果只是短时间重开(同一天)，不进行大额结算，依靠实时挂机
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
                    # 更新最后登录时间
                    conn.execute("UPDATE rival SET last_login_date = ? WHERE id = 1", (now_str,))

    # --- V3.0 对手实时随机成长 ---
    def rival_random_growth(self) -> Tuple[bool, int]:
        """
        主界面定时调用。
        返回: (是否升级了, 获得的XP)
        """
        r = self.get_rival()
        if not r: return False, 0
        
        # 获取倍率
        multiplier = 1.0
        if "0.5x" in r.tier: multiplier = 0.5
        elif "1.5x" in r.tier: multiplier = 1.5
        elif "2.0x" in r.tier: multiplier = 2.0

        # 随机获得少量经验 (模拟对手正在学习)
        base_xp = random.randint(5, 15)
        xp_gain = int(base_xp * multiplier)
        attr_gain = 0.02 * multiplier

        r.xp += xp_gain
        r.perception += attr_gain
        r.insight += attr_gain
        r.logic += attr_gain
        r.charisma += attr_gain
        
        leveled_up = False
        while r.xp >= r.next_level_xp:
            r.xp -= r.next_level_xp
            r.level += 1
            r.next_level_xp = calc_next_level_xp(r.level)
            leveled_up = True
            
        # 更新最后登录时间，防止下次启动重复计算
        r.last_login_date = datetime.now().isoformat()
        self.update_rival(r)
        return leveled_up, xp_gain

    # --- CRUD ---
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
            # V3 修改：在获取任务列表时，过滤掉“今天休息”的循环任务
            sql = "SELECT * FROM quest WHERE 1=1"
            params = []
            if status:
                sql += " AND status = ?"
                params.append(status.value)
            
            rows = conn.execute(sql, params).fetchall()
            all_quests = [Quest.from_db_row(tuple(r)) for r in rows]
            
            # 过滤逻辑：如果是未完成的任务，且是循环任务，检查今天是否是工作日
            final_quests = []
            weekday_now = str(datetime.now().isoweekday()) # 1-7
            
            for q in all_quests:
                if status == QuestStatus.INCOMPLETE and q.frequency == QuestFrequency.RECURRING:
                    # 如果设置了 active_days (不为空)，且今天不在其中 -> 隐藏
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
            cost = r_row["cost"]
            if p.gold < cost: return False, f"金币不足！需要 {cost}"
            p.gold -= cost
            self.update_player(p)
            return True, f"购买成功：{r_row['name']}"

    def complete_quest(self, quest_id: int, duration_mins: int = 0) -> Tuple[Optional[Player], int, int]:
        quest = self.get_quest(quest_id)
        if not quest or quest.status == QuestStatus.COMPLETE: return None, 0, 0
        player = self.get_player()
        xp_gain = 20 + quest.difficulty * 15
        gold_gain = 10 + quest.difficulty * 5
        attr_gain = 1 if quest.difficulty >= 3 else 0
        player.xp += xp_gain; player.gold += gold_gain
        if quest.attribute != QuestAttribute.OTHER:
            if quest.attribute == QuestAttribute.PERCEPTION: player.perception += attr_gain
            elif quest.attribute == QuestAttribute.INSIGHT: player.insight += attr_gain
            elif quest.attribute == QuestAttribute.LOGIC: player.logic += attr_gain
            elif quest.attribute == QuestAttribute.CHARISMA: player.charisma += attr_gain
        while player.xp >= player.next_level_xp:
            player.xp -= player.next_level_xp; player.level += 1
            player.next_level_xp = calc_next_level_xp(player.level)
        self.update_player(player)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.get_connection() as conn:
            conn.execute("UPDATE quest SET status = ?, completed_at = ?, duration = ? WHERE id = ?", 
                (QuestStatus.COMPLETE.value, now_str, duration_mins, quest_id))
        return player, xp_gain, gold_gain

    def abandon_quest(self, quest_id: int) -> Tuple[int, int]:
        quest = self.get_quest(quest_id)
        if not quest: return 0, 0
        penalty_gold = quest.difficulty * 5
        rival_gain = quest.difficulty * 10
        p = self.get_player(); p.gold = max(0, p.gold - penalty_gold); self.update_player(p)
        r = self.get_rival(); r.xp += rival_gain
        while r.xp >= r.next_level_xp:
            r.xp -= r.next_level_xp; r.level += 1; r.next_level_xp = calc_next_level_xp(r.level)
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