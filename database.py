"""
LifeQuest - SQLite 数据库层
负责建表、玩家/假想敌与任务的 CRUD，离线成长计算，以及任务奖惩逻辑。
"""
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from models import Player, Rival, Quest, QuestType, QuestAttribute, QuestStatus


# 升级所需经验公式：基础值 * (等级 ^ 指数)，可调
def calc_next_level_xp(level: int, base: int = 100, exponent: float = 1.2) -> int:
    """计算升至下一级所需经验"""
    return max(base, int(base * (level ** exponent)))


class DatabaseManager:
    """SQLite 数据库管理：建表、玩家、假想敌、任务、完成/放弃任务逻辑"""

    def __init__(self, db_path: str = "lifequest.db"):
        self.db_path = Path(db_path)
        self._ensure_connection()

    def _ensure_connection(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def create_tables(self) -> None:
        """创建玩家表、假想敌表与任务表"""
        with self.get_connection() as conn:
            conn.executescript("""
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
                    last_login_date TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS quest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    quest_type TEXT NOT NULL,
                    attribute TEXT NOT NULL,
                    difficulty INTEGER NOT NULL CHECK (difficulty >= 1 AND difficulty <= 5),
                    status TEXT NOT NULL DEFAULT '未完成',
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_quest_status ON quest(status);
                CREATE INDEX IF NOT EXISTS idx_quest_type ON quest(quest_type);
            """)

    def init_player_if_missing(self) -> None:
        """初始化玩家和假想敌，并计算假想敌的离线自动成长"""
        with self.get_connection() as conn:
            # 1. 初始化玩家
            cur = conn.execute("SELECT 1 FROM player WHERE id = 1")
            if cur.fetchone() is None:
                conn.execute(
                    """INSERT INTO player (id, level, xp, next_level_xp, gold,
                       perception, insight, logic, charisma)
                       VALUES (1, 1, 0, ?, 0, 5.0, 5.0, 5.0, 5.0)""",
                    (calc_next_level_xp(1),),
                )
            
            # 2. 初始化假想敌 & 计算离线成长
            now_str = datetime.now().isoformat()
            cur_rival = conn.execute("SELECT last_login_date FROM rival WHERE id = 1")
            row = cur_rival.fetchone()
            
            if row is None:
                # 首次创建假想敌 (稍微给点压力，初始属性5.5)
                conn.execute(
                    """INSERT INTO rival (id, level, xp, next_level_xp,
                       perception, insight, logic, charisma, last_login_date)
                       VALUES (1, 1, 0, ?, 5.5, 5.5, 5.5, 5.5, ?)""",
                    (calc_next_level_xp(1), now_str),
                )
            else:
                # 存在假想敌，计算离线天数
                last_date_str = row[0]
                if last_date_str:
                    last_date = datetime.fromisoformat(last_date_str)
                    days_diff = (datetime.now() - last_date).total_seconds() / 86400.0
                    
                    if days_diff > 0.01:  # 超过约15分钟才计算成长
                        rival = self.get_rival()
                        if rival:
                            # 卷王每天固定得 150 经验，各项属性涨 0.8
                            rival.xp += int(150 * days_diff)
                            rival.perception += 0.8 * days_diff
                            rival.insight += 0.8 * days_diff
                            rival.logic += 0.8 * days_diff
                            rival.charisma += 0.8 * days_diff
                            
                            # 卷王升级逻辑
                            while rival.xp >= rival.next_level_xp:
                                rival.xp -= rival.next_level_xp
                                rival.level += 1
                                rival.next_level_xp = calc_next_level_xp(rival.level)
                            
                            rival.last_login_date = now_str
                            self.update_rival(rival)

    def get_player(self) -> Optional[Player]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
            if row is None: return None
            return Player.from_db_row(tuple(row))

    def update_player(self, player: Player) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE player SET level=?, xp=?, next_level_xp=?, gold=?,
                   perception=?, insight=?, logic=?, charisma=?
                   WHERE id = 1""",
                (player.level, player.xp, player.next_level_xp, player.gold,
                 player.perception, player.insight, player.logic, player.charisma),
            )

    def get_rival(self) -> Optional[Rival]:
        """获取影子对手数据"""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM rival WHERE id = 1").fetchone()
            if row is None: return None
            return Rival.from_db_row(tuple(row))

    def update_rival(self, rival: Rival) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE rival SET level=?, xp=?, next_level_xp=?,
                   perception=?, insight=?, logic=?, charisma=?, last_login_date=?
                   WHERE id = 1""",
                (rival.level, rival.xp, rival.next_level_xp,
                 rival.perception, rival.insight, rival.logic, rival.charisma, rival.last_login_date),
            )

    def insert_quest(self, quest: Quest) -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO quest (name, description, quest_type, attribute, difficulty, status, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                quest.to_db_row(),
            )
            return cur.lastrowid

    def get_quest(self, quest_id: int) -> Optional[Quest]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM quest WHERE id = ?", (quest_id,)).fetchone()
            if row is None: return None
            return Quest.from_db_row(tuple(row))

    def list_quests(
        self,
        status: Optional[QuestStatus] = None,
        quest_type: Optional[QuestType] = None,
    ) -> List[Quest]:
        with self.get_connection() as conn:
            sql = "SELECT * FROM quest WHERE 1=1"
            params: list = []
            if status is not None:
                sql += " AND status = ?"
                params.append(status.value)
            if quest_type is not None:
                sql += " AND quest_type = ?"
                params.append(quest_type.value)
            sql += " ORDER BY id"
            rows = conn.execute(sql, params).fetchall()
            return [Quest.from_db_row(tuple(r)) for r in rows]

    def set_quest_status(self, quest_id: int, status: QuestStatus) -> None:
        with self.get_connection() as conn:
            conn.execute("UPDATE quest SET status = ? WHERE id = ?", (status.value, quest_id))

    def delete_quest(self, quest_id: int) -> bool:
        """硬删除任务（保留给UI，但不推荐作为常态）"""
        with self.get_connection() as conn:
            cur = conn.execute("DELETE FROM quest WHERE id = ?", (quest_id,))
            return cur.rowcount > 0

    def _xp_reward_for_quest(self, difficulty: int) -> int:
        return 20 + difficulty * 15

    def _gold_reward_for_quest(self, difficulty: int) -> int:
        return 10 + difficulty * 5

    def _attribute_gain_for_quest(self, difficulty: int) -> int:
        return 1 if difficulty >= 3 else 0

    def complete_quest(self, quest_id: int) -> Tuple[Optional[Player], int, int]:
        """
        完成任务的核心逻辑。
        返回: (更新后的Player, 获得的XP, 获得的Gold)。若失败返回 (None, 0, 0)
        """
        quest = self.get_quest(quest_id)
        if quest is None or quest.status == QuestStatus.COMPLETE:
            return None, 0, 0

        player = self.get_player()
        if player is None: return None, 0, 0

        xp_gain = self._xp_reward_for_quest(quest.difficulty)
        gold_gain = self._gold_reward_for_quest(quest.difficulty)
        attr_gain = self._attribute_gain_for_quest(quest.difficulty)

        player.xp += xp_gain
        player.gold += gold_gain

        # 雅思四维成长
        if quest.attribute == QuestAttribute.PERCEPTION: player.perception += attr_gain
        elif quest.attribute == QuestAttribute.INSIGHT: player.insight += attr_gain
        elif quest.attribute == QuestAttribute.LOGIC: player.logic += attr_gain
        elif quest.attribute == QuestAttribute.CHARISMA: player.charisma += attr_gain

        # 连升逻辑
        while player.xp >= player.next_level_xp:
            player.xp -= player.next_level_xp
            player.level += 1
            player.next_level_xp = calc_next_level_xp(player.level)

        self.update_player(player)
        
        # 记录完成时间与状态
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.get_connection() as conn:
            conn.execute("UPDATE quest SET status = ?, completed_at = ? WHERE id = ?", 
                         (QuestStatus.COMPLETE.value, now_str, quest_id))
            
        return player, xp_gain, gold_gain

    def abandon_quest(self, quest_id: int) -> Tuple[int, int]:
        """
        放弃任务惩罚机制！
        返回: (扣除的金币, 对手白嫖的经验)。若失败返回 (0, 0)
        """
        quest = self.get_quest(quest_id)
        if quest is None or quest.status != QuestStatus.INCOMPLETE:
            return 0, 0
            
        penalty_gold = quest.difficulty * 5
        rival_gain_xp = quest.difficulty * 10
        
        # 1. 扣除玩家金币 (不扣成负数)
        player = self.get_player()
        if player:
            player.gold = max(0, player.gold - penalty_gold)
            self.update_player(player)
            
        # 2. 对手狂喜 (加经验升级)
        rival = self.get_rival()
        if rival:
            rival.xp += rival_gain_xp
            while rival.xp >= rival.next_level_xp:
                rival.xp -= rival.next_level_xp
                rival.level += 1
                rival.next_level_xp = calc_next_level_xp(rival.level)
            self.update_rival(rival)
            
        # 3. 标记为已放弃，并记录时间
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.get_connection() as conn:
            conn.execute("UPDATE quest SET status = ?, completed_at = ? WHERE id = ?", 
                         (QuestStatus.ABANDONED.value, now_str, quest_id))
                         
        return penalty_gold, rival_gain_xp