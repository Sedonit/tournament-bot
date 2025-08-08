import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- 🔒 Блокировка повторного запуска ---
LOCK_FILE = "bot.lock"

if os.path.exists(LOCK_FILE):
    print("❌ Бот уже запущен или предыдущий запуск не завершился корректно.")
    print("Удалите файл 'bot.lock' вручную, если уверены, что бот не работает.")
    sys.exit(1)

# Создаём файл блокировки
with open(LOCK_FILE, "w", encoding="utf-8") as f:
    f.write(str(os.getpid()))

# Удаляем файл при выходе
import atexit
atexit.register(lambda: os.path.exists(LOCK_FILE) and os.remove(LOCK_FILE))
# ---------------------------------------

# Попытка импортировать функции базы данных
try:
    from database import init_db, save_application, get_stats, get_all_applications, reset_applications
    DATABASE_AVAILABLE = True
except ImportError as e:
    DATABASE_AVAILABLE = False
    logging.warning(f"Модуль database.py не найден. Работа с базой данных отключена. Ошибка: {e}")

# Получаем токен и ID админов из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS_STR = os.environ.get('ADMIN_IDS', '')
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(',') if x.strip().isdigit()]

# Состояния разговора
NICKNAME, RANK, NAME, CONTACT, TEAM = range(5)

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def initialize_database():
    if DATABASE_AVAILABLE:
        try:
            init_db()
            logger.info("✅ База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации базы данных: {e}")
    else:
        logger.info("⚠️ База данных недоступна, пропускаем инициализацию")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        message = "👑 Админ-панель\nДоступные команды:\n"
        if DATABASE_AVAILABLE:
            message += "/stats - Статистика заявок\n"
            message += "/list - Список всех участников\n"
            message += "/reset - Сбросить все заявки\n"
        else:
            message += "📊 Статистика временно недоступна\n"
        await update.message.reply_text(message)
        return

    await update.message.reply_text(
        "🏆 Добро пожаловать на регистрацию турнира!\n"
        "Пожалуйста, ответьте на несколько вопросов:"
    )
    await update.message.reply_text("1. Введите ваш никнейм в игре:")
    return NICKNAME

# Обработка никнейма
async def nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nickname'] = update.message.text
    await update.message.reply_text("2. Какое у вас звание/ранг?")
    return RANK

# Обработка ранга
async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['rank'] = update.message.text
    await update.message.reply_text("3. Ваше имя (не обязательно, можно пропустить):")
    return NAME

# Обработка имени
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("4. Укажите способ связи (Telegram, Discord, WhatsApp и т.д.):")
    return CONTACT

# Обработка контакта
async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['contact'] = update.message.text
    await update.message.reply_text("5. Команда (если есть, если нет - напишите 'Нет'):")
    return TEAM

# Обработка команды и завершение
async def team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['team'] = update.message.text
    nickname = context.user_data.get('nickname', 'Не указан')
    rank = context.user_data.get('rank', 'Не указан')
    name = context.user_data.get('name', 'Не указан')
    contact = context.user_data.get('contact', 'Не указан')
    team = context.user_data.get('team', 'Не указан')

    app_id = None
    if DATABASE_AVAILABLE:
        try:
            app_id = save_application(nickname, rank, name, contact, team)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в БД: {e}")

    form_text = f"🎮 Новая заявка на турнир!\n"
    if app_id:
        form_text += f"Номер заявки: #{app_id}\n"
    form_text += (
        f"Никнейм: {nickname}\n"
        f"Ранг: {rank}\n"
        f"Имя: {name}\n"
        f"Связь: {contact}\n"
        f"Команда: {team}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=form_text)
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение админу {admin_id}: {e}")

    response_text = "✅ Спасибо! Ваша заявка отправлена организаторам турнира.\n"
    if app_id:
        response_text += f"Номер вашей заявки: #{app_id}\n"
    response_text += "Ожидайте подтверждения участия!"
    await update.message.reply_text(response_text)
    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Регистрация отменена.')
    return ConversationHandler.END

# Команды для админов
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    if not DATABASE_AVAILABLE:
        await update.message.reply_text("❌ Статистика временно недоступна.")
        return
    try:
        total, teams = get_stats()
        message = f"📊 Статистика турнира\n"
        message += f"Всего заявок: {total}\n"
        if teams:
            message += "Команды:\n"
            for team in teams:
                message += f"  {team['team']}: {team['count']} участников\n"
        else:
            message += "Пока нет зарегистрированных команд."
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики.")

async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    if not DATABASE_AVAILABLE:
        await update.message.reply_text("❌ Список участников временно недоступен.")
        return
    try:
        applications = get_all_applications()
        if not applications:
            await update.message.reply_text("📭 Пока нет заявок.")
            return
        message = f"📋 Список участников (всего: {len(applications)}):\n"
        for i, app in enumerate(applications, 1):
            message += f"{i}. {app['nickname']} ({app['rank']})\n"
            message += f"   Связь: {app['contact']}\n"
            if app['team'] and app['team'] != 'Нет':
                message += f"   Команда: {app['team']}\n"
            message += "\n"
            if len(message) > 3000:
                await update.message.reply_text(message)
                message = ""
        if message.strip():
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"❌ Ошибка получения списка участников: {e}")
        await update.message.reply_text("❌ Ошибка получения списка участников.")

async def reset_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    if not DATABASE_AVAILABLE:
        await update.message.reply_text("❌ Сброс временно недоступен.")
        return
    try:
        deleted_count = reset_applications()
        await update.message.reply_text(f"✅ База данных очищена. Удалено заявок: {deleted_count}")
    except Exception as e:
        logger.error(f"❌ Ошибка сброса базы данных: {e}")
        await update.message.reply_text("❌ Ошибка при сбросе базы данных.")

# Основная функция запуска
def main():
    initialize_database()

    if not BOT_TOKEN:
        logger.error("❌ Не задан BOT_TOKEN в переменных окружения!")
        sys.exit(1)

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, nickname)],
            RANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rank)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
            TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, team)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    if DATABASE_AVAILABLE:
        application.add_handler(CommandHandler('stats', stats))
        application.add_handler(CommandHandler('list', list_participants))
        application.add_handler(CommandHandler('reset', reset_counter))

    application.add_handler(conv_handler)

    logger.info("🚀 Запуск бота в режиме polling...")
    application.run_polling()

if __name__ == '__main__':
    main()