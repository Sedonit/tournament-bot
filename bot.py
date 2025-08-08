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
        # get_db_connection, # Не импортируем, так как она внутри database.py
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

# Константы для пагинации
ITEMS_PER_PAGE = 10

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
        [InlineKeyboardButton("📋 Все участники", callback_data="list_all_page_1")],
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
    logger.info(f"Получен callback_query с data: {query.data}") # <<< Лог для диагностики

    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Доступ запрещён.")
        return

    data = query.data

    if data == "stats":
        logger.info("Обработка stats") # <<< Лог
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
            logger.error(f"Ошибка статистики: {e}", exc_info=True)
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Ошибка.", reply_markup=reply_markup)

    elif data.startswith("list_all_page_"):
        logger.info(f"Начало обработки list_all_page для {data}") # <<< Лог
        if not DATABASE_AVAILABLE:
            logger.warning("База данных недоступна при попытке показать список") # <<< Лог
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ База данных недоступна.", reply_markup=reply_markup)
            return
        try:
            page = int(data.split("_")[-1])
            logger.info(f"Запрошена страница: {page}") # <<< Лог
            offset = (page - 1) * ITEMS_PER_PAGE

            # Получаем записи для текущей страницы
            apps = get_all_applications(limit=ITEMS_PER_PAGE, offset=offset)
            logger.info(f"Получено {len(apps)} записей для страницы {page}") # <<< Лог

            # Получаем общее количество записей для вычисления страниц
            all_apps_for_count = get_all_applications() # Получаем все для подсчета
            total_count = len(all_apps_for_count)
            logger.info(f"Всего записей в БД: {total_count}") # <<< Лог

            if not apps:
                message = "📭 Нет заявок."
            else:
                message = f"📋 Участники (страница {page}):\n"
                # Отображаем ID из БД, имя и контакт
                for i, app in enumerate(apps, offset + 1):
                    message += f"{i}. #{app['id']} {app['nickname']} ({app['rank']})\n"
                    name_str = app['name'] if app['name'] else "Не указано"
                    contact_str = app['contact'] if app['contact'] else "Не указан"
                    message += f"   Имя: {name_str}, Контакт: {contact_str}\n"

            # Создаем кнопки навигации
            navigation_buttons = []
            if page > 1:
                navigation_buttons.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"list_all_page_{page - 1}"))
            # Проверяем, есть ли следующая страница
            if offset + len(apps) < total_count:
                navigation_buttons.append(InlineKeyboardButton("➡️ Следующая", callback_data=f"list_all_page_{page + 1}"))

            keyboard = [navigation_buttons, [InlineKeyboardButton("🏠 В меню", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
            logger.info("Сообщение со списком успешно отправлено") # <<< Лог
        except Exception as e:
            logger.error(f"Ошибка списка: {e}", exc_info=True)
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Ошибка.", reply_markup=reply_markup)

    elif data == "delete_profile":
        logger.info("Обработка delete_profile") # <<< Лог
        # Добавляем кнопку "Назад" на экран ввода номера
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Введите номер профиля из списка (номер слева от #ID):", reply_markup=reply_markup)
        context.user_data['awaiting_delete_id'] = True
        # Не возвращаем WAITING_DELETE_ID, так как это CallbackQueryHandler, не ConversationHandler state
        # Но устанавливаем флаг для следующего текстового сообщения

    elif data == "reset_all":
        logger.info("Обработка reset_all") # <<< Лог
        keyboard = [
            [InlineKeyboardButton("✅ Да, сбросить всё", callback_data="confirm_reset")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_action")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚠️ Внимание! Это удалит ВСЕ заявки.\nПодтвердите действие:", reply_markup=reply_markup)

    elif data == "back_to_admin_menu":
        logger.info("Обработка back_to_admin_menu") # <<< Лог
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

    # Обработка кнопки "⚙️ Админ-меню" из уведомления о новой заявке
    elif data == "back_to_admin_menu_from_notification":
        logger.info("Обработка back_to_admin_menu_from_notification") # <<< Лог
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

# === УДАЛЕНИЕ ПРОФИЛЯ ===
# Обработчик текстового сообщения для ввода номера профиля
async def waiting_delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Начало обработки waiting_delete_id") # <<< Лог
    # Проверяем флаг, установленный в button_handler
    if not context.user_data.get('awaiting_delete_id'):
        logger.info("Флаг awaiting_delete_id не установлен, игнорируем сообщение") # <<< Лог
        # Если флаг не установлен, это обычное сообщение, не связанное с удалением.
        # Можно ничего не делать или обработать как новую команду.
        return

    try:
        profile_num = int(update.message.text.strip())
        logger.info(f"Введён номер профиля: {profile_num}") # <<< Лог
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
        logger.info(f"Всего заявок для поиска: {len(apps)}") # <<< Лог
        # Проверка диапазона: profile_num от 1 до len(apps)
        if profile_num < 1 or profile_num > len(apps):
            logger.info(f"Номер {profile_num} вне диапазона 1-{len(apps)}") # <<< Лог
            # Добавляем кнопку "Назад" при ошибке ввода номера
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"❌ Нет профиля с номером {profile_num}. Введите число от 1 до {len(apps)}.", reply_markup=reply_markup)
            # Не сбрасываем флаг, чтобы пользователь мог попробовать снова
            return

        app = apps[profile_num - 1] # Получаем запись по порядковому номеру
        logger.info(f"Найден профиль для удаления: ID={app['id']}, Nickname={app['nickname']}") # <<< Лог
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
        # Переходим в состояние подтверждения
        return CONFIRM_DELETE
    except Exception as e:
        logger.error(f"Ошибка при получении профиля для удаления: {e}", exc_info=True)
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
    logger.info(f"Начало обработки confirm_delete_handler с data: {query.data}") # <<< Лог

    # Проверяем, что это админ
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        logger.info("Попытка подтверждения удаления не админом") # <<< Лог
        return

    if query.data == "confirm_delete":
        app_id = context.user_data.get('delete_app_id')
        nickname_val = context.user_data.get('delete_nickname')
        logger.info(f"Подтверждение удаления: ID={app_id}, Nickname={nickname_val}") # <<< Лог
        if not app_id:
             await query.edit_message_text("❌ Ошибка: ID профиля не найден.")
             return
        try:
            # Используем функцию из database.py
            deleted = delete_application_by_id(app_id)
            logger.info(f"Результат удаления: удалено {deleted} записей") # <<< Лог
            if deleted > 0:
                await query.edit_message_text(f"✅ Профиль '{nickname_val}' (ID: #{app_id}) удалён.")
            else:
                await query.edit_message_text("❌ Профиль не найден.")
        except Exception as e:
            logger.error(f"Ошибка удаления профиля: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка при удалении.")
    elif query.data in ["cancel_action", "back_to_admin_menu"]:
        logger.info(f"Отмена/назад при удалении: action={query.data}") # <<< Лог
        if query.data == "cancel_action":
             await query.edit_message_text("❌ Удаление отменено.")
        # В любом случае, если нажата "Назад" или "Отмена", возвращаемся в меню
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

    # Сброс состояния
    context.user_data.pop('delete_app_id', None)
    context.user_data.pop('delete_nickname', None)
    logger.info("Состояние для удаления сброшено") # <<< Лог
    # Не возвращаем ConversationHandler.END здесь, так как это обработчик CallbackQuery
    return ConversationHandler.END

# === СБРОС ВСЕХ ЗАЯВОК ===
async def confirm_reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Начало обработки confirm_reset_handler с data: {query.data}") # <<< Лог

    # Проверяем, что это админ
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        logger.info("Попытка сброса не админом") # <<< Лог
        return

    if query.data == "confirm_reset":
        logger.info("Подтверждение сброса") # <<< Лог
        try:
            deleted_count = reset_applications()
            logger.info(f"Сброс выполнен: удалено {deleted_count} записей") # <<< Лог
            await query.edit_message_text(f"✅ Все заявки удалены. Удалено: {deleted_count}")
        except Exception as e:
            logger.error(f"Ошибка сброса: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка при сбросе.")
    elif query.data in ["cancel_action", "back_to_admin_menu"]:
        logger.info(f"Отмена/назад при сбросе: action={query.data}") # <<< Лог
        if query.data == "cancel_action":
             await query.edit_message_text("❌ Сброс отменён.")
        # В любом случае, если нажата "Назад" или "Отмена", возвращаемся в меню
        reply_markup = get_admin_menu_keyboard()
        await query.edit_message_text("👑 Админ-панель", reply_markup=reply_markup)

# Основная функция
def main():
    logger.info("Инициализация базы данных...")
    initialize_database()

    logger.info("Создание Application...")
    application = Application.builder().token(BOT_TOKEN).build()

    # === Обработчики колбэков (кнопок) ДОБАВЛЯЕМ ПЕРВЫМИ ===
    # Это важно для правильной работы кнопок вне диалога

    # Обработчики админских кнопок (включая пагинацию и кнопку "Назад")
    # Добавлены дополнительные паттерны для новых кнопок
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(stats|list_all_page_|delete_profile|reset_all|back_to_admin_menu|back_to_admin_menu_from_notification)$"))
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
            # CONFIRM_DELETE теперь обрабатывается отдельным CallbackQueryHandler
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)

    # Обработчик текстовых сообщений для удаления профиля
    # Он будет срабатывать только если context.user_data['awaiting_delete_id'] == True
    # и пользователь находится в состоянии разговора (что не обязательно для текстовых сообщений вне диалога)
    # Но для корректной работы с ConversationHandler, когда он активен, добавим его с группой приоритета.
    # На практике, так как мы не используем ConversationHandler для этого состояния напрямую,
    # можно добавить его без группы, но для избежания конфликтов с другими MessageHandler'ами
    # (например, если бы у нас был общий обработчик текста), добавим с группой.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, waiting_delete_id), group=1)

    logger.info("🚀 Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()
