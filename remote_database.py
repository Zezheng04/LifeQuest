from __future__ import annotations

from typing import Any, Optional

import requests

from models import Player, Quest, QuestAttribute, QuestFrequency, QuestStatus, QuestType, Reward, Rival


class RemoteApiError(Exception):
    pass


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("detail") or payload.get("message") or response.text)
    except ValueError:
        pass
    return response.text or f"HTTP {response.status_code}"


def register_user(base_url: str, username: str, password: str) -> None:
    response = requests.post(
        f"{normalize_base_url(base_url)}/auth/register",
        json={"username": username, "password": password},
        timeout=15,
    )
    if response.status_code >= 400:
        raise RemoteApiError(_extract_error_message(response))


def login_user(base_url: str, username: str, password: str) -> str:
    response = requests.post(
        f"{normalize_base_url(base_url)}/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    if response.status_code >= 400:
        raise RemoteApiError(_extract_error_message(response))
    return response.json()["access_token"]


def validate_token(base_url: str, token: str) -> dict[str, Any]:
    response = requests.get(
        f"{normalize_base_url(base_url)}/users/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if response.status_code >= 400:
        raise RemoteApiError(_extract_error_message(response))
    return response.json()


def build_sync_state(local_db, config: dict[str, Any]) -> dict[str, Any]:
    player = local_db.get_player()
    rival = local_db.get_rival()
    quests = local_db.list_quests(status=None)
    rewards = local_db.list_rewards()

    return {
        "player": {
            "id": player.id,
            "level": player.level,
            "xp": player.xp,
            "next_level_xp": player.next_level_xp,
            "gold": player.gold,
            "perception": player.perception,
            "insight": player.insight,
            "logic": player.logic,
            "charisma": player.charisma,
            "streak_days": getattr(player, "streak_days", 0),
            "last_active_date": getattr(player, "last_active_date", ""),
            "streak_freeze_cards": getattr(player, "streak_freeze_cards", 0),
        },
        "rival": {
            "id": rival.id,
            "level": rival.level,
            "xp": rival.xp,
            "next_level_xp": rival.next_level_xp,
            "perception": rival.perception,
            "insight": rival.insight,
            "logic": rival.logic,
            "charisma": rival.charisma,
            "last_login_date": rival.last_login_date,
            "tier": rival.tier,
        },
        "quests": [
            {
                "id": q.id,
                "name": q.name,
                "description": q.description,
                "quest_type": q.quest_type.value,
                "attribute": q.attribute.value,
                "difficulty": q.difficulty,
                "status": q.status.value,
                "completed_at": q.completed_at,
                "duration": q.duration,
                "frequency": q.frequency.value,
                "active_days": q.active_days,
            }
            for q in quests
        ],
        "rewards": [
            {
                "id": r.id,
                "name": r.name,
                "cost": r.cost,
                "description": r.description,
            }
            for r in rewards
        ],
        "config": {
            "target_name": config["target_name"],
            "target_date": config["target_date"],
            "attr1": config["attr1"],
            "attr2": config["attr2"],
            "attr3": config["attr3"],
            "attr4": config["attr4"],
        },
    }


class RemoteDatabaseManager:
    def __init__(self, base_url: str, token: str):
        self.base_url = normalize_base_url(base_url)
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _request(self, method: str, path: str, **kwargs):
        try:
            response = self.session.request(method, f"{self.base_url}{path}", timeout=15, **kwargs)
        except requests.RequestException as exc:
            raise RemoteApiError(f"无法连接服务器：{exc}") from exc

        if response.status_code >= 400:
            raise RemoteApiError(_extract_error_message(response))

        if response.content:
            return response.json()
        return None

    def create_tables(self) -> None:
        return None

    def init_player_if_missing(self) -> None:
        self._request("GET", "/player")

    def check_daily_reset(self):
        self._request("POST", "/maintenance/daily-reset")

    def get_user_config(self) -> dict[str, Any]:
        return self._request("GET", "/config")

    def update_user_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", "/config", json=config)

    def get_player(self) -> Optional[Player]:
        payload = self._request("GET", "/player")
        player = Player(
            id=payload["id"],
            level=payload["level"],
            xp=payload["xp"],
            next_level_xp=payload["next_level_xp"],
            gold=payload["gold"],
            perception=payload["perception"],
            insight=payload["insight"],
            logic=payload["logic"],
            charisma=payload["charisma"],
        )
        setattr(player, "streak_days", payload.get("streak_days", 0))
        setattr(player, "last_active_date", payload.get("last_active_date", ""))
        setattr(player, "streak_freeze_cards", payload.get("streak_freeze_cards", 0))
        return player

    def get_rival(self) -> Optional[Rival]:
        payload = self._request("GET", "/rival")
        return Rival(
            id=payload["id"],
            level=payload["level"],
            xp=payload["xp"],
            next_level_xp=payload["next_level_xp"],
            perception=payload["perception"],
            insight=payload["insight"],
            logic=payload["logic"],
            charisma=payload["charisma"],
            last_login_date=payload["last_login_date"],
            tier=payload["tier"],
        )

    def update_rival(self, rival: Rival) -> None:
        self._request("PUT", "/rival", json={"tier": rival.tier})

    def rival_random_growth(self):
        payload = self._request("POST", "/rival/random-growth")
        return payload["leveled_up"], payload["xp_gained"]

    def _quest_from_payload(self, payload: dict[str, Any]) -> Quest:
        return Quest(
            id=payload["id"],
            name=payload["name"],
            description=payload["description"],
            quest_type=QuestType(payload["quest_type"]),
            attribute=QuestAttribute(payload["attribute"]) if payload["attribute"] in [item.value for item in QuestAttribute] else QuestAttribute.OTHER,
            difficulty=payload["difficulty"],
            status=QuestStatus(payload["status"]),
            completed_at=payload.get("completed_at"),
            duration=payload.get("duration", 0),
            frequency=QuestFrequency(payload.get("frequency", QuestFrequency.ONCE.value)),
            active_days=payload.get("active_days", ""),
        )

    def list_quests(self, status: Optional[QuestStatus] = None):
        params = {}
        if status:
            params["status"] = status.value
        payload = self._request("GET", "/quests", params=params)
        return [self._quest_from_payload(item) for item in payload]

    def insert_quest(self, quest: Quest) -> int:
        payload = self._request(
            "POST",
            "/quests",
            json={
                "name": quest.name,
                "description": quest.description,
                "quest_type": quest.quest_type.value,
                "attribute": quest.attribute.value,
                "difficulty": quest.difficulty,
                "frequency": quest.frequency.value,
                "active_days": quest.active_days,
            },
        )
        return payload["id"]

    def update_quest(self, quest: Quest) -> None:
        self._request(
            "PUT",
            f"/quests/{quest.id}",
            json={
                "name": quest.name,
                "description": quest.description,
                "quest_type": quest.quest_type.value,
                "attribute": quest.attribute.value,
                "difficulty": quest.difficulty,
                "frequency": quest.frequency.value,
                "active_days": quest.active_days,
            },
        )

    def complete_quest(self, quest_id: int, duration_mins: int = 0):
        payload = self._request("POST", f"/quests/{quest_id}/complete", json={"duration_mins": duration_mins})
        player_payload = payload["player"]
        player = Player(
            id=player_payload["id"],
            level=player_payload["level"],
            xp=player_payload["xp"],
            next_level_xp=player_payload["next_level_xp"],
            gold=player_payload["gold"],
            perception=player_payload["perception"],
            insight=player_payload["insight"],
            logic=player_payload["logic"],
            charisma=player_payload["charisma"],
        )
        setattr(player, "streak_days", player_payload.get("streak_days", 0))
        setattr(player, "last_active_date", player_payload.get("last_active_date", ""))
        setattr(player, "streak_freeze_cards", player_payload.get("streak_freeze_cards", 0))
        return player, payload["xp_gain"], payload["gold_gain"], payload["leveled_up"], payload["cards_used"]

    def abandon_quest(self, quest_id: int):
        payload = self._request("POST", f"/quests/{quest_id}/abandon")
        return payload["penalty_gold"], payload["rival_gain"]

    def list_rewards(self):
        payload = self._request("GET", "/rewards")
        return [Reward(item["id"], item["name"], item["cost"], item.get("description", "")) for item in payload]

    def add_reward(self, name: str, cost: int, desc: str = ""):
        self._request("POST", "/rewards", json={"name": name, "cost": cost, "description": desc})

    def delete_reward(self, rid: int):
        self._request("DELETE", f"/rewards/{rid}")

    def buy_reward(self, reward_id: int):
        payload = self._request("POST", f"/rewards/{reward_id}/buy")
        return payload["success"], payload["message"]

    def buy_freeze_card(self):
        payload = self._request("POST", "/rewards/freeze-card/buy")
        return payload["success"], payload["message"]

    def get_today_study_time(self) -> int:
        payload = self._request("GET", "/stats/today-study-time")
        return payload["total_minutes"]

    def export_state(self) -> dict[str, Any]:
        return self._request("GET", "/sync/export")

    def import_state(self, state: dict[str, Any]):
        return self._request("POST", "/sync/import", json=state)

    def is_fresh_account(self) -> bool:
        state = self.export_state()
        player = state["player"]
        config = state["config"]
        return (
            player["level"] == 1
            and player["xp"] == 0
            and player["gold"] == 0
            and player.get("streak_days", 0) == 0
            and not state["quests"]
            and not state["rewards"]
            and config["target_name"] == "雅思 8.0 竞速对决"
            and config["target_date"] == "2024-12-31"
            and config["attr1"] == "听力(感知)"
            and config["attr2"] == "阅读(洞察)"
            and config["attr3"] == "写作(逻辑)"
            and config["attr4"] == "口语(魅力)"
        )
