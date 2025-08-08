# bot.py
import os
import sys
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)

# Имитация открытия порта для удовлетворения Render (на случай, если переменная окружения не сработает)
try:
    import threading
    import time
    import socket

    def open_and_close_port():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('0.0.0.0', 0))
            port = s.getsockname()[1]
            print(f"INFO:render: Temporarily bound to port {port} to satisfy Render port scan.")
            s.listen(1)
            time.sleep(2)  # Ждем немного
            s.close()
            print(f"INFO:render: Port {port} closed.")
        except Exception as e:
            print(f"INFO:render: Could not temporarily bind port: {e}")

    port_thread = threading.Thread(target=open_and_close_port, daemon=True)
    port_thread.start()
except Exception as e:
    pass  # Игнорируем ошибки, если не удалось


# --- 🔒 Блокировка повторного запуска ---
LOCK_FILE = "bot.lock"

if os.path.exists(LOCK_FILE):
    print("❌ Бот уже запущен или предыдущий процесс не завершился.")
    print("Удалите файл 'bot.lock', если уверены, что бот не работает.")
    sys.exit(1)

# Создаём файл блокировки
with open(LOCK_FILE, "w", encoding="utf-8") as f:
    f.write(str(os.getpid()))

# Удаляем файл при выходе
import atexit
atexit.register(lambda: os.path.exists(LOCK_FILE) and os.remove(LOCK_FILE))
# ---------------------------------------

# Попытка импортировать базу данных
try:
    from database import (
        init_db,
        save_application,
        get_stats,
        get_all_applications,
        reset_applications,
        delete_application_by_id,
    )
    DATABASE_AVAILABLE = True
except ImportError as e:
    DATABASE_AVAILABLE = False
    logging.warning(f"Модуль database.py не найден: {e}")

# Получаем токен и ID админов из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logging.error("❌ Не задан BOT_TOKEN в переменных окружения!")
    sys.exit(1)

ADMIN_IDS_STR = os.environ.get('ADMIN_IDS', '')
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(',') if x.strip().isdigit()]

# Состояния
NICKNAME, RANK, NAME, CONTACT, TEAM = range(5)
WAITING_DELETE_ID, CONFIRM_DELETE = range(100, 102)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def initialize_database():
    if DATABASE_AVAILABLE:
        try:
            init_db()
            logger.info("✅ База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
    else:
        logger.info("⚠️ Работа с базой данных отключена")

# Функция для создания основного админ-меню
def get_admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Все участники", callback_data="list_all")],
        [InlineKeyboardButton("🗑 Удалить профиль", callback_data="delete_profile")],
        [InlineKeyboardButton("♻️ Сбросить всё", callback_data="reset_all")],
    ])

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        reply_markup = get_admin_menu_keyboard()
        await update.message.reply_text("👑 Админ-панель", reply_markup=reply_markup)
        return ConversationHandler.END

    await update.message.reply_text(
        "🏆 Добро пожаловать на регистрацию турнира!\n"
        "Пожалуйста, ответьте на несколько вопросов:"
    )
    await update.message.reply_text("1. Введите ваш никнейм в игре:")
    return NICKNAME

# === ОБРАБОТКА РЕГИСТРАЦИИ ===
async def nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nickname'] = update.message.text
    await update.message.reply_text("2. Какое у вас звание/ранг?")
    return RANK

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['rank']…