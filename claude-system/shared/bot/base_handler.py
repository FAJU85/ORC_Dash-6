"""Handler base مشترك لكل البوتات."""
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import logging
log = logging.getLogger(__name__)

def require_auth(allowed_users: list[int], admin_id: int):
    """Decorator للتحقق من الصلاحية."""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            if user_id != admin_id and user_id not in allowed_users:
                await update.message.reply_text("❌ غير مصرح لك.")
                return
            return await func(update, context)
        return wrapper
    return decorator

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء العام — أضفه لكل بوت."""
    log.error(f"Bot error: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ خطأ مؤقت — حاول مرة أخرى")
