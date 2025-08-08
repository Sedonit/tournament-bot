# bot.py
import os
import sys
import logging
# Имитация открытия порта для удовлетворения Render (на случай, если переменная окружения не сработает)
# Делаем это ДО любых других импортов
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
            time.sleep(2) # Ждем немного
            s.close()
            print(f"INFO:render: Port {port} closed.")
        except Exception as e:
            print(f"INFO:render: Could not temporarily bind port: {e}")

    port_thread = threading.Thread(target=open_and_close_port, daemon=True)
    port_thread.start()
except Exception as e:
    pass # Игнорируем ошибки, если не удалось


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
    context.user_data['rank'] = update.message.text
    await update.message.reply_text("3. Ваше имя (не обязательно):")
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("4. Способ связи (Telegram, Discord и т.д.):")
    return CONTACT

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['contact'] = update.message.text
    await update.message.reply_text("5. Команда (или 'Нет'):")
    return TEAM

async def team(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Отправляем админам с кнопкой перехода в меню
    keyboard = [
        [InlineKeyboardButton("⚙️ Админ-меню", callback_data="back_to_admin_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=form_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")

    # <<< Изменённое сообщение пользователю
    response = "✅ Заявка отправлена!\n"
    if app_id:
        response += f"Ваш ID: #{app_id}\n"
    response += "С вами свяжутся по указанному контакту."
    await update.message.reply_text(response)
    return ConversationHandler.END

# Отмена
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
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ База данных недоступна.", reply_markup=reply_markup)
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
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка статистики: {e}")
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Ошибка.", reply_markup=reply_markup)

    elif data == "list_all":
        if not DATABASE_AVAILABLE:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ База данных недоступна.", reply_markup=reply_markup)
            return
        try:
            apps = get_all_applications() # Получаем все записи
            if not apps:
                message = "📭 Нет заявок."
            else:
                message = "📋 Участники:\n"
                # Отображаем ID из БД, имя и контакт
                for i, app in enumerate(apps, 1):
                    # Показываем ID из БД в скобках для ясности
                    message += f"{i}. #{app['id']} {app['nickname']} ({app['rank']})\n"
                    # Добавляем имя и контакт на отдельной строке
                    name_str = app['name'] if app['name'] else "Не указано"
                    contact_str = app['contact'] if app['contact'] else "Не указан"
                    message += f"   Имя: {name_str}, Контакт: {contact_str}\n"
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка списка: {e}")
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Ошибка.", reply_markup=reply_markup)

    elif data == "delete_profile":
        # Добавляем кнопку "Назад" на экран ввода номера
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Введите номер профиля из списка (номер слева от #ID):", reply_markup=reply_markup)
        context.user_data['awaiting_delete_id'] = True
        # Не возвращаем WAITING_DELETE_ID, так как это CallbackQueryHandler

    elif data == "reset_all":
        keyboard = [
            [InlineKeyboardButton("✅ Да, сбросить всё", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_action")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚠️ Внимание! Это удалит ВСЕ заявки.\nПодтвердите действие:", reply_markup=reply_markup)

    elif data == "back_to_admin_menu":
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

# === УДАЛЕНИЕ ПРОФИЛЯ ===
async def waiting_delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем флаг, установленный в button_handler
    if not context.user_data.get('awaiting_delete_id'):
        return

    try:
        profile_num = int(update.message.text.strip())
    except ValueError:
        # Добавляем кнопку "Назад" при ошибке ввода
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Введите число.", reply_markup=reply_markup)
        # Не сбрасываем флаг, чтобы пользователь мог попробовать снова
        return

    try:
        # Для удаления нужно получить полный список, чтобы найти запись по номеру
        apps = get_all_applications()
        # Проверка диапазона: profile_num от 1 до len(apps)
        if profile_num < 1 or profile_num > len(apps):
            # Добавляем кнопку "Назад" при ошибке ввода номера
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"❌ Нет профиля с номером {profile_num}. Введите число от 1 до {len(apps)}.", reply_markup=reply_markup)
            # Не сбрасываем флаг, чтобы пользователь мог попробовать снова
            return

        app = apps[profile_num - 1] # Получаем запись по порядковому номеру
        app_id_to_delete = app['id'] # ID записи в БД
        context.user_data['delete_app_id'] = app_id_to_delete
        context.user_data['delete_nickname'] = app['nickname']

        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data="confirm_delete")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_action")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"❓ Действительно удалить профиль #{profile_num}?\n"
            f"ID: #{app_id_to_delete}\n"
            f"Ник: {app['nickname']}\n"
            f"Ранг: {app['rank']}",
            reply_markup=reply_markup
        )
        # Сбрасываем флаг, так как теперь ждем подтверждения через кнопки
        context.user_data['awaiting_delete_id'] = False
        return CONFIRM_DELETE
    except Exception as e:
        logger.error(f"Ошибка при получении профиля: {e}")
        # Добавляем кнопку "Назад" при ошибке
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ Ошибка при поиске профиля.", reply_markup=reply_markup)
        # Сбрасываем флаг в случае ошибки
        context.user_data['awaiting_delete_id'] = False
        return ConversationHandler.END # Завершаем в случае ошибки

# Обработчик подтверждения/отмены удаления
async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Проверяем, что это админ
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        return

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
    elif query.data in ["cancel_action", "back_to_admin_menu"]: # Обрабатываем обе кнопки
        if query.data == "cancel_action":
             await query.edit_message_text("❌ Удаление отменено.")
        # В любом случае, если нажата "Назад" или "Отмена", возвращаемся в меню
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

    # Сброс состояния
    context.user_data.pop('delete_app_id', None)
    context.user_data.pop('delete_nickname', None)
    return ConversationHandler.END

# === СБРОС ВСЕХ ЗАЯВОК ===
async def confirm_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Проверяем, что это админ
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        return

    if query.data == "confirm_reset":
        try:
            deleted_count = reset_applications()
            await query.edit_message_text(f"✅ Все заявки удалены. Удалено: {deleted_count}")
        except Exception as e:
            logger.error(f"Ошибка сброса: {e}")
            await query.edit_message_text("❌ Ошибка при сбросе.")
    elif query.data in ["cancel_action", "back_to_admin_menu"]: # Обрабатываем обе кнопки
        if query.data == "cancel_action":
             await query.edit_message_text("❌ Сброс отменён.")
        # В любом случае, если нажата "Назад" или "Отмена", возвращаемся в меню
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

# Основная функция
def main():
    initialize_database()

    application = Application.builder().token(BOT_TOKEN).build()

    # === Обработчики колбэков (кнопок) ДОБАВЛЯЕМ ПЕРВЫМИ ===
    # Это важно для правильной работы кнопок вне диалога

    # Обработчики админских кнопок
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(stats|list_all|delete_profile|reset_all|back_to_admin_menu)$"))
    # Обработчики подтверждения/отмены удаления и сброса
    application.add_handler(CallbackQueryHandler(confirm_delete_handler, pattern="^(confirm_delete|cancel_action|back_to_admin_menu)$"))
    application.add_handler(CallbackQueryHandler(confirm_reset_handler, pattern="^(confirm_reset|cancel_action|back_to_admin_menu)$"))

    # === Диалог регистрации ===
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, nickname)],
            RANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rank)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
            TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, team)],
            # WAITING_DELETE_ID и CONFIRM_DELETE теперь обрабатываются отдельно
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)

    # Обработчик текстовых сообщений для удаления профиля
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_delete_id), group=1)

    logger.info("🚀 Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()
