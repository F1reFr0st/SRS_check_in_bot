import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Инициализация доступа к Google Sheets через API
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("srs-counter-bot-2ec9a679aadc.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Test location SRS").sheet1

# Параметры тренировок
monday_time_range = ("19:45", "20:15")
thursday_time_range = ("18:45", "19:15")
monday_location = (42.69111552118943, 23.33724196498975)  # Орлов Мост
thursday_location = (42.644958198794846, 23.348024207313852)  # Стадион НСА
check_in_days = {"Monday": monday_time_range, "Thursday": thursday_time_range}

# Проверка, находится ли пользователь на тренировке в правильное время и месте
def check_time_and_location(current_time, current_day, user_location):
    if current_day in check_in_days:
        start_time, end_time = check_in_days[current_day]
        if start_time <= current_time <= end_time:
            if current_day == "Monday":
                target_location = monday_location
            elif current_day == "Thursday":
                target_location = thursday_location

            # Проверка локации (в радиусе 500 метров)
            if (abs(user_location.latitude - target_location[0]) <= 0.005 and
                    abs(user_location.longitude - target_location[1]) <= 0.005):
                return True
    return False

# Функция для старта бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name

    # Кнопка для отправки геолокации
    location_button = KeyboardButton(text="Check-in", request_location=True)

    # Кнопка "Моя статистика" всегда добавляется
    stats_button = KeyboardButton(text="Моя статистика")
    keyboard = ReplyKeyboardMarkup([[location_button, stats_button]], resize_keyboard=True)

    # Путь к вашему JPG-файлу
    png_path = 'SRS words.png'  # Замените на путь к вашему JPG-файлу

    # Отправка JPG-файла
    with open(png_path, 'rb') as photo:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo)

    # Отправка сообщения с кнопками
    await update.message.reply_text('Привет! Я помогу вам зачекиниться на тренировку или посмотреть вашу статистику посещений.', reply_markup=keyboard)

# Функция для обработки геолокации и отметки тренировки
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.username
    user_name = update.message.from_user.full_name
    user_location = update.message.location

    # Чтение данных из Google Sheets
    users_data = sheet.get_all_records()

    # Получаем текущие день и время
    now = datetime.now().date()
    current_day = datetime.now().strftime("%A")
    current_time = datetime.now().strftime("%H:%M")

    # Ищем пользователя в данных
    user_data = next((user for user in users_data if user['user_id'] == str(user_id)), None)
    if user_data is None and check_time_and_location(current_time, current_day, user_location):
        # Добавляем нового пользователя в базу, если его нет
        sheet.append_row([user_name, str(user_id), 1, now.isoformat()])  # Новый пользователь с нулевыми посещениями
        await update.message.reply_text(f"Отлично, {user_name}! Вы отметились на своей первой тренировке. Удачи!")
        await update.message.delete()
        return


    # Проверяем, может ли пользователь отметиться
    if check_time_and_location(current_time, current_day, user_location):
        # Проверка, не отмечался ли пользователь уже сегодня
        user_check_in_time = user_data['last_checkin']
        if user_check_in_time == now.isoformat():
            await update.message.reply_text("Вы уже отметились на тренировке сегодня.")
        else:
            # Обновляем посещения
            new_visits = int(user_data['visits']) + 1
            sheet.update_cell(users_data.index(user_data) + 2, 3, new_visits)  # Обновляем количество посещений
            sheet.update_cell(users_data.index(user_data) + 2, 4, now.isoformat())  # Обновляем дату посещения

            await update.message.reply_text(f"Отлично, {user_name}! Вы отметились на тренировке. Количество посещений: {new_visits}.")
    else:
        await update.message.reply_text("Сейчас не время для чекина или вы находитесь далеко от места тренировки.")

    await update.message.delete()
        #user_data = {'user_id': str(user_id), 'visits': 1, 'last_checkin': now.isoformat()}

# Функция для проверки статистики
async def check_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.username
    user_name = update.message.from_user.full_name

    # Чтение данных из Google Sheets
    users_data = sheet.get_all_records()

    # Поиск пользователя и подсчет его посещений
    user_visits = 0
    for user in users_data:
        if user['user_id'] == str(user_id):  # Сравниваем ID пользователя
            user_visits = user['visits']
            break

    # Если пользователь не найден, он ещё не был на тренировках
    if user_visits == 0:
        await update.message.reply_text(f"Вы пока не были на тренировках.")
        return

    # Сортировка пользователей по количеству посещений для ранжирования
    sorted_users = sorted(users_data, key=lambda x: x['visits'], reverse=True)
    user_rank = next((i + 1 for i, user in enumerate(sorted_users) if user['user_id'] == str(user_id)), None)

    # Ответ пользователю с количеством посещений и его местом
    await update.message.reply_text(f"Вы были на {user_visits} тренировках.\nПо количеству посещений ваше место: {user_rank} среди всех участников.")

# Основная функция для запуска бота
def main():
    # Инициализация приложения
    application = Application.builder().token("7826186279:AAGnA2Dz3Tx8TekQwZclV5L_o9LF4LEjSfo").build()

    # Регистрация команд и обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))

    # Обработчик для кнопки "Моя статистика"
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("Моя статистика"), check_stats))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()

