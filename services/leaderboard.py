from typing import List, Dict, Any

from db.repo_users import get_leaderboard
from utils.text import medal, safe_username


def build_leaderboard_text(limit: int = 10) -> str:
    rows: List[Dict[str, Any]] = get_leaderboard(limit=limit)
    if not rows:
        return "🏆 هنوز کسی امتیازی ندارد!"

    lines = ["🏆 لیدربورد میولند\n"]
    for i, r in enumerate(rows, 1):
        uname = safe_username(r.get("username"), int(r.get("telegram_id") or 0))
        pts = int(r.get("mew_points") or 0)
        lines.append(f"{medal(i)} {uname} - {pts} امتیاز")
    return "\n".join(lines)
