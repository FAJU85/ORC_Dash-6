"""إشعارات تيليجرام مشتركة."""
import httpx, os, logging
log = logging.getLogger(__name__)

ICONS = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌", "critical": "🚨"}

async def notify(message: str, level: str = "info", project: str = "") -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ADMIN_ID")
    if not token or not chat_id:
        return False
    icon = ICONS.get(level, "ℹ️")
    prefix = f"[{project}] " if project else ""
    text = f"{icon} {prefix}\n{message}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text}
            )
            return r.status_code == 200
    except Exception as e:
        log.error(f"Notify failed: {e}")
        return False
