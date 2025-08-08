import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Получаем токен и ID админов из переменных окружения
BOT_TOKEN = os.environ.get('8162425911:AAHAoataP_W84txlOp-6h9r66tdQdUr_U4M')
ADMIN_IDS_STR = os.environ.get('951964149', '1862994550')
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(',') if x.strip().isdigit()]

# Состояния разговора
NICKNAME, RANK, NAME, CONTACT, TEAM = range(5)

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await update.message.reply_text(
            "👑 Админ-панель\n\n"
            "Доступные команды:\n"
            "/stats - Статистика заявок\n"
            "/list - Список всех участников"
        )
        return
    
    await update.message.reply_text(
        "🏆 Добро пожаловать на регистрацию турнира!\n\n"
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
    
    # Формируем анкету
    nickname = context.user_data.get('nickname', 'Не указан')
    rank = context.user_data.get('rank', 'Не указан')
    name = context.user_data.get('name', 'Не указан')
    contact = context.user_data.get('contact', 'Не указан')
    team = context.user_data.get('team', 'Не указан')
    
    form_text = (
        f"🎮 Новая заявка на турнир!\n\n"
        f"Никнейм: {nickname}\n"
        f"Ранг: {rank}\n"
        f"Имя: {name}\n"
        f"Связь: {contact}\n"
        f"Команда: {team}"
    )
    
    # Отправляем всем админам
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=form_text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
    
    # Ответ пользователю
    await update.message.reply_text(
        "✅ Спасибо! Ваша заявка отправлена организаторам турнира.\n"
        "Ожидайте подтверждения участия!"
    )
    
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
    await update.message.reply_text("📊 Пока что счетчик заявок хранится локально и недоступен на Render.")

async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    await update.message.reply_text("📋 Список участников временно недоступен на Render.")

# Основная функция запуска
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Создаем ConversationHandler
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

    # Добавляем команды для админов
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('list', list_participants))
    
    application.add_handler(conv_handler)

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()