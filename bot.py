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
        get_application_by_id, # <<< Новая функция
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
(
    NICKNAME, RANK, NAME, CONTACT, TEAM,
    WAITING_DELETE_ID, CONFIRM_DELETE
) = range(7)

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

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("📋 Все участники", callback_data="list_all")],
            [InlineKeyboardButton("🗑 Удалить профиль", callback_data="delete_profile")],
            [InlineKeyboardButton("♻️ Сбросить всё", callback_data="reset_all")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("👑 Админ-панель", reply_markup=reply_markup)
        return ConversationHandler.END

    await update.message.reply_text(
        "🏆 Добро пожаловать на регистрацию турнира!\n"
        "Пожалуйста, ответьте на несколько вопросов:"
    )
    # Кнопки для пользователя в процессе регистрации
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("1. Введите ваш никнейм в игре:", reply_markup=reply_markup)
    return NICKNAME

# === ОБРАБОТКА РЕГИСТРАЦИИ ===
async def nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка на команду отмены через сообщение (на случай, если кнопка не сработала)
    if update.message.text and update.message.text.startswith('/'):
         await update.message.reply_text('Регистрация отменена.')
         return ConversationHandler.END

    context.user_data['nickname'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_nickname")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("2. Какое у вас звание/ранг?", reply_markup=reply_markup)
    return RANK

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.startswith('/'):
         await update.message.reply_text('Регистрация отменена.')
         return ConversationHandler.END

    context.user_data['rank'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_rank")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("3. Ваше имя (не обязательно):", reply_markup=reply_markup)
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.startswith('/'):
         await update.message.reply_text('Регистрация отменена.')
         return ConversationHandler.END

    context.user_data['name'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_name")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("4. Способ связи (Telegram, Discord и т.д.):", reply_markup=reply_markup)
    return CONTACT

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.startswith('/'):
         await update.message.reply_text('Регистрация отменена.')
         return ConversationHandler.END

    context.user_data['contact'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_contact")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("5. Команда (или 'Нет'):", reply_markup=reply_markup)
    return TEAM

async def team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.startswith('/'):
         await update.message.reply_text('Регистрация отменена.')
         return ConversationHandler.END

    context.user_data['team'] = update.message.text
    nickname_val = context.user_data.get('nickname', 'Не указан')
    rank_val = context.user_data.get('rank', 'Не указан')
    name_val = context.user_data.get('name', 'Не указан')
    contact_val = context.user_data.get('contact', 'Не указан')
    team_val = context.user_data.get('team', 'Не указан')

    app_id = None
    if DATABASE_AVAILABLE:
        try:
            app_id = save_application(nickname_val, rank_val, name_val, contact_val, team_val)
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")

    form_text = f"🎮 Новая заявка!\n"
    if app_id:
        form_text += f"ID: #{app_id}\n"
    form_text += (
        f"Ник: {nickname_val}\nРанг: {rank_val}\nИмя: {name_val}\n"
        f"Связь: {contact_val}\nКоманда: {team_val}"
    )

    # Отправляем админам с кнопкой просмотра
    if DATABASE_AVAILABLE and app_id:
        keyboard = [
            [InlineKeyboardButton("👀 Просмотреть заявку", callback_data=f"view_application_{app_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=form_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка отправки админу {admin_id}: {e}")
    else:
        # Если БД недоступна, отправляем без кнопки
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=form_text)
            except Exception as e:
                logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    response = "✅ Заявка отправлена!\n"
    if app_id:
        response += f"Ваш ID: #{app_id}\n"
    response += "Ожидайте подтверждения."
    await update.message.reply_text(response)
    return ConversationHandler.END

# === ОБРАБОТЧИКИ КНОПОК "НАЗАД" И "ОТМЕНА" В РЕГИСТРАЦИИ ===
async def handle_registration_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_registration":
        await query.edit_message_text("Регистрация отменена.")
        return ConversationHandler.END

    elif query.data == "back_to_nickname":
        # Удаляем предыдущие данные
        context.user_data.pop('nickname', None)
        keyboard = [
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("1. Введите ваш никнейм в игре:", reply_markup=reply_markup)
        return NICKNAME

    elif query.data == "back_to_rank":
        context.user_data.pop('rank', None)
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_nickname")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("2. Какое у вас звание/ранг?", reply_markup=reply_markup)
        return RANK

    elif query.data == "back_to_name":
        context.user_data.pop('name', None)
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_rank")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("3. Ваше имя (не обязательно):", reply_markup=reply_markup)
        return NAME

    elif query.data == "back_to_contact":
        context.user_data.pop('contact', None)
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_name")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_registration")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("4. Способ связи (Telegram, Discord и т.д.):", reply_markup=reply_markup)
        return CONTACT

    # Если неизвестная кнопка, просто игнорируем
    return ConversationHandler.END

# Отмена через команду /cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Регистрация отменена.')
    return ConversationHandler.END

# === КНОПКИ ДЛЯ АДМИНОВ ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Доступ запрещён.")
        return

    data = query.data

    if data == "stats":
        if not DATABASE_AVAILABLE:
            await query.edit_message_text("❌ База данных недоступна.")
            return
        try:
            total, teams = get_stats()
            message = f"📊 Статистика\nВсего: {total}\n"
            if teams:
                message += "Команды:\n"
                for t in teams:
                    message += f"  {t['team']}: {t['count']}\n"
            else:
                message += "Нет команд."
            await query.edit_message_text(message)
        except Exception as e:
            logger.error(f"Ошибка статистики: {e}")
            await query.edit_message_text("❌ Ошибка.")

    elif data == "list_all":
        if not DATABASE_AVAILABLE:
            await query.edit_message_text("❌ База данных недоступна.")
            return
        try:
            apps = get_all_applications() # Сортировка по created_at DESC
            if not apps:
                await query.edit_message_text("📭 Нет заявок.")
                return
            message = "📋 Участники:\n"
            # Используем enumerate с 1 для удобства пользователя
            # Отображаем ID из БД для однозначного удаления
            for i, app in enumerate(apps, 1):
                message += f"{i}. #{app['id']} {app['nickname']} ({app['rank']})\n"
            await query.edit_message_text(message)
        except Exception as e:
            logger.error(f"Ошибка списка: {e}")
            await query.edit_message_text("❌ Ошибка.")

    elif data == "delete_profile":
        await query.edit_message_text("Введите номер профиля из списка (номер слева от #ID):")
        context.user_data['awaiting_delete_id'] = True
        return WAITING_DELETE_ID

    elif data == "reset_all":
        keyboard = [
            [InlineKeyboardButton("✅ Да, сбросить всё", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_action")]
        ]
        await query.edit_message_text("⚠️ Внимание! Это удалит ВСЕ заявки.\nПодтвердите действие:", reply_markup=InlineKeyboardMarkup(keyboard))

    # <<< НОВОЕ: Обработка кнопки "Просмотреть заявку"
    elif data.startswith("view_application_"):
        if not DATABASE_AVAILABLE:
            await query.edit_message_text("❌ База данных недоступна.")
            return
        try:
            app_id = int(data.split("_")[-1])
            app = get_application_by_id(app_id)
            if not app:
                 await query.edit_message_text("❌ Заявка не найдена.")
                 return

            message = (
                f"📄 Заявка #{app['id']}\n"
                f"Ник: {app['nickname']}\n"
                f"Ранг: {app['rank']}\n"
                f"Имя: {app['name'] or 'Не указано'}\n"
                f"Связь: {app['contact']}\n"
                f"Команда: {app['team'] or 'Не указана'}\n"
                f"Дата: {app['created_at']}"
            )
            # Кнопка для возврата в админ-панель
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_admin_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
            # Сохраняем ID заявки в контексте для возможного удаления отсюда
            context.user_data['current_viewed_app_id'] = app_id
        except (ValueError, Exception) as e:
            logger.error(f"Ошибка просмотра заявки: {e}")
            await query.edit_message_text("❌ Ошибка при просмотре заявки.")

    elif data == "back_to_admin_menu":
        # Возврат в главное меню админа
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("📋 Все участники", callback_data="list_all")],
            [InlineKeyboardButton("🗑 Удалить профиль", callback_data="delete_profile")],
            [InlineKeyboardButton("♻️ Сбросить всё", callback_data="reset_all")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

# === УДАЛЕНИЕ ПРОФИЛЯ ===
async def waiting_delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_delete_id'):
        return ConversationHandler.END

    try:
        profile_num = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return WAITING_DELETE_ID

    try:
        apps = get_all_applications() # Получаем список, отсортированный так же, как в list_all
        # Проверка диапазона: profile_num от 1 до len(apps)
        if profile_num < 1 or profile_num > len(apps):
            await update.message.reply_text(f"❌ Нет профиля с номером {profile_num}. Введите число от 1 до {len(apps)}.")
            return WAITING_DELETE_ID

        app = apps[profile_num - 1] # Получаем запись по порядковому номеру
        app_id_to_delete = app['id'] # ID записи в БД
        context.user_data['delete_app_id'] = app_id_to_delete
        context.user_data['delete_nickname'] = app['nickname']

        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_delete")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_action_delete")]
        ]
        await update.message.reply_text(
            f"❓ Действительно удалить профиль #{profile_num}?\n"
            f"ID: #{app_id_to_delete}\n"
            f"Ник: {app['nickname']}\n"
            f"Ранг: {app['rank']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка при получении профиля: {e}")
        await update.message.reply_text("❌ Ошибка при поиске профиля.")
    return CONFIRM_DELETE

async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_delete":
        app_id = context.user_data.get('delete_app_id')
        nickname_val = context.user_data.get('delete_nickname')
        try:
            # Используем функцию из database.py
            deleted = delete_application_by_id(app_id)
            if deleted > 0:
                await query.edit_message_text(f"✅ Профиль '{nickname_val}' (ID: #{app_id}) удалён.")
            else:
                await query.edit_message_text("❌ Профиль не найден.")
        except Exception as e:
            logger.error(f"Ошибка удаления профиля: {e}")
            await query.edit_message_text("❌ Ошибка при удалении.")
    elif query.data in ["cancel_action", "cancel_action_delete"]: # <<< Обработка отмены удаления
        await query.edit_message_text("❌ Удаление отменено.")

    # Сброс состояния
    context.user_data.pop('awaiting_delete_id', None)
    context.user_data.pop('delete_app_id', None)
    context.user_data.pop('delete_nickname', None)
    return ConversationHandler.END

# === СБРОС ВСЕХ ЗАЯВОК ===
async def confirm_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_reset":
        try:
            deleted_count = reset_applications()
            await query.edit_message_text(f"✅ Все заявки удалены. Удалено: {deleted_count}")
        except Exception as e:
            logger.error(f"Ошибка сброса: {e}")
            await query.edit_message_text("❌ Ошибка при сбросе.")
    elif query.data in ["cancel_action", "cancel_action_delete"]: # <<< Обработка отмены сброса
        await query.edit_message_text("❌ Сброс отменён.")

# Основная функция
def main():
    initialize_database()

    application = Application.builder().token(BOT_TOKEN).build()

    # === Обработчики колбэков (кнопок) ДОБАВЛЯЕМ ПЕРВЫМИ ===
    # Это важно для правильной работы кнопок вне диалога
    # Обработчики админских кнопок и просмотра заявок
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(stats|list_all|delete_profile|reset_all|view_application_|back_to_admin_menu)$"))
    # Обработчики подтверждения/отмены удаления и сброса
    application.add_handler(CallbackQueryHandler(confirm_delete_handler, pattern="^(confirm_delete|cancel_action|cancel_action_delete)$"))
    application.add_handler(CallbackQueryHandler(confirm_reset_handler, pattern="^(confirm_reset|cancel_action|cancel_action_delete)$"))
    # Обработчики кнопок "Назад" и "Отмена" в регистрации
    application.add_handler(CallbackQueryHandler(handle_registration_buttons, pattern="^(cancel_registration|back_to_.*)$"))

    # === Диалог регистрации ===
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, nickname)],
            RANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rank)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
            TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, team)],
            WAITING_DELETE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_delete_id)],
            CONFIRM_DELETE: [CallbackQueryHandler(confirm_delete_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)

    logger.info("🚀 Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()