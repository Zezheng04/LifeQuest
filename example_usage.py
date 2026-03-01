"""
LifeQuest 数据层示例：建表、插入任务、完成任务（经验与升级）
"""
from database import DatabaseManager, calc_next_level_xp
from models import Quest, QuestType, QuestAttribute, QuestStatus


def main():
    db = DatabaseManager("lifequest.db")

    # 1. 创建表并初始化玩家
    db.create_tables()
    db.init_player_if_missing()

    # 2. 插入任务
    q1 = Quest(
        name="晨跑 5 公里",
        description="完成一次 5 公里晨跑",
        quest_type=QuestType.DAILY,
        attribute=QuestAttribute.STR,
        difficulty=2,
    )
    q2 = Quest(
        name="阅读 30 页",
        description="今日阅读目标 30 页",
        quest_type=QuestType.DAILY,
        attribute=QuestAttribute.INT,
        difficulty=3,
    )
    id1 = db.insert_quest(q1)
    id2 = db.insert_quest(q2)
    print(f"已插入任务 id={id1}, id={id2}")

    # 3. 查看当前玩家
    player = db.get_player()
    print(f"玩家: Lv.{player.level} XP={player.xp}/{player.next_level_xp} 金币={player.gold}")

    # 4. 完成任务（会加经验、金币、属性，并可能升级）
    player = db.complete_quest(id1)
    if player:
        print(f"完成任务后: Lv.{player.level} XP={player.xp}/{player.next_level_xp} 金币={player.gold} 力量={player.strength}")

    player = db.complete_quest(id2)
    if player:
        print(f"再完成一个: Lv.{player.level} XP={player.xp}/{player.next_level_xp} 智力={player.intelligence}")

    # 5. 列出未完成任务
    for q in db.list_quests(status=QuestStatus.INCOMPLETE):
        print(f"未完成: {q.name} [{q.quest_type.value}] 难度{q.difficulty}")


if __name__ == "__main__":
    main()
