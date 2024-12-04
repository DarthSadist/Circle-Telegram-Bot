import telebot
import os
from dotenv import load_dotenv
import moviepy.editor as mp
from telebot import types
import tempfile
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
import glob
import sys
import time
import logging
from collections import defaultdict
from datetime import datetime
import subprocess

# Настройка логирования
logging.basicConfig(
    filename='bot_logs.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('circle_bot')

# Добавляем вывод в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def log_and_print(message, level=logging.INFO):
    """Функция для логирования и вывода в консоль"""
    if level == logging.INFO:
        logger.info(message)
    elif level == logging.WARNING:
        logger.warning(message)
    elif level == logging.ERROR:
        logger.error(message)
    elif level == logging.CRITICAL:
        logger.critical(message)
    
    # Добавляем эмодзи в зависимости от уровня логирования
    emoji = {
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🚨"
    }
    print(f"{emoji.get(level, '')} {message}")

# Загрузка и проверка переменных окружения
if not load_dotenv():
    logger.error("Файл .env не найден!")
    print("❌ Ошибка: Файл .env не найден!")
    print("1. Создайте файл .env на основе .env.example")
    print("2. Добавьте в него ваш токен бота")
    sys.exit(1)

TOKEN = os.getenv('TOKEN')
if not TOKEN:
    logger.error("TOKEN не найден в файле .env!")
    print("❌ Ошибка: TOKEN не найден в файле .env!")
    print("1. Убедитесь, что в файле .env есть строка TOKEN=your_token_here")
    print("2. Замените your_token_here на ваш токен от @BotFather")
    sys.exit(1)

# Константы для анти-флуда
FLOOD_LIMIT = 3  # максимальное количество сообщений
FLOOD_TIME = 60  # временной интервал в секундах
user_messages = defaultdict(list)  # словарь для хранения времени сообщений пользователей

def check_flood(user_id):
    """Проверка на флуд"""
    current_time = time.time()
    # Удаляем устаревшие сообщения
    user_messages[user_id] = [msg_time for msg_time in user_messages[user_id] 
                            if current_time - msg_time < FLOOD_TIME]
    # Добавляем новое сообщение
    user_messages[user_id].append(current_time)
    # Проверяем количество сообщений
    return len(user_messages[user_id]) > FLOOD_LIMIT

try:
    bot = telebot.TeleBot(TOKEN)
    executor = ThreadPoolExecutor(max_workers=3)
    logger.info("Бот успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации бота: {str(e)}")
    print(f"❌ Ошибка при инициализации бота: {str(e)}")
    sys.exit(1)

# Настройки пользователей
user_settings = defaultdict(lambda: {
    "video_size": 384,
    "video_quality": "medium"  # новая настройка качества
})
user_stats = defaultdict(lambda: {"processed_videos": 0, "total_size_mb": 0})

def get_user_stats(user_id):
    """Получение статистики пользователя"""
    stats = user_stats[user_id]
    stats_text = (f"📊 Ваша статистика:\n"
                f"Обработано видео: {stats['processed_videos']}\n"
                f"Общий размер: {stats['total_size_mb']:.2f} МБ")
    
    log_and_print(f"Запрошена статистика для пользователя (ID: {user_id}):\n{stats_text}")
    return stats_text

@bot.message_handler(commands=['stats'])
def stats_command(message):
    user = message.from_user
    user_id = user.id
    username = user.username or "Unknown"
    
    log_and_print(f"Пользователь {username} (ID: {user_id}) запросил статистику")
    
    if user_id not in user_stats:
        log_and_print(f"Статистика не найдена для пользователя {username} (ID: {user_id})")
        stats_text = "У вас пока нет статистики. Отправьте мне видео для обработки!"
    else:
        stats = user_stats[user_id]
        stats_text = get_user_stats(user_id)
        log_and_print(
            f"Статистика пользователя {username} (ID: {user_id}):\n"
            f"- Обработано видео: {stats['processed_videos']}\n"
            f"- Общий размер: {stats['total_size_mb']:.2f} МБ"
        )
    
    bot.reply_to(message, stats_text)

@bot.callback_query_handler(func=lambda call: call.data == "show_sizes")
def show_sizes(call):
    """Показать меню выбора размера видео"""
    user = call.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) открыл меню выбора размера")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    sizes = [384, 480, 568, 640]
    size_buttons = []
    
    current_size = user_settings[call.from_user.id]["video_size"]
    
    for size in sizes:
        marker = "✅" if size == current_size else ""
        btn = types.InlineKeyboardButton(
            f"{marker} {size}x{size}", 
            callback_data=f"size_{size}"
        )
        size_buttons.append(btn)
    
    back_btn = types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_settings")
    markup.add(*size_buttons, back_btn)
    
    bot.edit_message_text(
        f"🎯 Выберите размер видео\n"
        f"Текущий размер: {current_size}x{current_size}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "show_quality")
def show_quality(call):
    """Показать меню выбора качества видео"""
    user = call.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) открыл меню выбора качества")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    qualities = {
        'high': '🎯 Высокое',
        'medium': '🎯 Среднее',
        'low': '🎯 Низкое'
    }
    
    current_quality = user_settings[call.from_user.id]["video_quality"]
    quality_buttons = []
    
    for quality_key, quality_name in qualities.items():
        marker = "✅" if quality_key == current_quality else ""
        btn = types.InlineKeyboardButton(
            f"{marker} {quality_name}", 
            callback_data=f"quality_{quality_key}"
        )
        quality_buttons.append(btn)
    
    back_btn = types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_settings")
    markup.add(*quality_buttons, back_btn)
    
    # Получаем текстовое описание текущего качества
    current_quality_text = {
        'high': 'высокое',
        'medium': 'среднее',
        'low': 'низкое'
    }.get(current_quality, 'среднее')
    
    bot.edit_message_text(
        f"🎨 Выберите качество видео\n"
        f"Текущее качество: {current_quality_text}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("size_"))
def change_size(call):
    """Изменить размер видео"""
    try:
        user = call.from_user
        new_size = int(call.data.split('_')[1])
        old_size = user_settings[user.id]["video_size"]
        
        log_and_print(f"Пользователь {user.username} (ID: {user.id}) меняет размер видео: {old_size}x{old_size} → {new_size}x{new_size}")
        
        user_settings[user.id]["video_size"] = new_size
        
        # Показываем меню размеров с обновленным значением
        show_sizes(call)
        
        # Отправляем уведомление
        bot.answer_callback_query(
            call.id,
            f"✅ Размер видео изменен на {new_size}x{new_size}",
            show_alert=True
        )
        
        log_and_print(f"Размер видео успешно изменен для пользователя {user.username} (ID: {user.id})")
        
    except Exception as e:
        error_msg = f"Ошибка при изменении размера видео: {str(e)}"
        log_and_print(error_msg, logging.ERROR)
        bot.answer_callback_query(call.id, f"❌ {error_msg}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("quality_"))
def change_quality(call):
    """Изменить качество видео"""
    try:
        user = call.from_user
        new_quality = call.data.split('_')[1]
        old_quality = user_settings[user.id]["video_quality"]
        
        # Получаем текстовые описания для логов
        quality_text = {
            'high': 'высокое',
            'medium': 'среднее',
            'low': 'низкое'
        }
        old_quality_text = quality_text.get(old_quality, 'среднее')
        new_quality_text = quality_text.get(new_quality, 'среднее')
        
        log_and_print(f"Пользователь {user.username} (ID: {user.id}) меняет качество видео: {old_quality_text} → {new_quality_text}")
        
        user_settings[user.id]["video_quality"] = new_quality
        
        # Показываем меню качества с обновленным значением
        show_quality(call)
        
        # Отправляем уведомление
        bot.answer_callback_query(
            call.id,
            f"✅ Качество видео изменено на {new_quality_text}",
            show_alert=True
        )
        
        log_and_print(f"Качество видео успешно изменено для пользователя {user.username} (ID: {user.id})")
        
    except Exception as e:
        error_msg = f"Ошибка при изменении качества видео: {str(e)}"
        log_and_print(error_msg, logging.ERROR)
        bot.answer_callback_query(call.id, f"❌ {error_msg}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_settings")
def back_to_settings(call):
    """Вернуться в главное меню настроек"""
    user = call.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) вернулся в главное меню настроек")
    settings_command(call.message)

@bot.message_handler(commands=['settings'])
def settings_command(message):
    """Показать главное меню настроек"""
    user = message.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) открыл настройки")
    
    # Проверяем существование настроек пользователя
    if user.id not in user_settings:
        user_settings[user.id] = {
            "video_size": 384,
            "video_quality": "medium"
        }
        log_and_print(f"Созданы настройки по умолчанию для пользователя {user.username} (ID: {user.id})")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Кнопки для размера
    sizes_btn = types.InlineKeyboardButton(
        "🎯 Размер видео", 
        callback_data="show_sizes"
    )
    
    # Кнопки для качества
    quality_btn = types.InlineKeyboardButton(
        "🎨 Качество видео", 
        callback_data="show_quality"
    )
    
    markup.add(sizes_btn, quality_btn)
    
    current_size = user_settings[user.id]["video_size"]
    current_quality = user_settings[user.id]["video_quality"]
    
    # Получаем текстовое описание качества
    quality_text = {
        'high': 'высокое',
        'medium': 'среднее',
        'low': 'низкое'
    }.get(current_quality, 'среднее')
    
    bot.send_message(
        message.chat.id,
        f"⚙️ Настройки обработки видео\n\n"
        f"Текущие настройки:\n"
        f"📐 Размер: {current_size}x{current_size}\n"
        f"🎨 Качество: {quality_text}\n\n"
        f"Выберите параметр для настройки:",
        reply_markup=markup
    )
    
    log_and_print(
        f"Текущие настройки пользователя {user.username} (ID: {user.id}):\n"
        f"- Размер: {current_size}x{current_size}\n"
        f"- Качество: {quality_text}"
    )

@bot.message_handler(commands=['start'])
def start_message(message):
    user = message.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) запустил бота")
    
    bot.send_message(
        message.chat.id,
        'Привет! Я помогу превратить твое видео в видеозаметку (кружок).\n\n'
        'Используй кнопки меню:\n'
        '⚙️ Настройки - изменить размер кружка\n'
        '📊 Статистика - посмотреть вашу статистику\n'
        '❓ Помощь - показать справку\n\n'
        'Или просто отправь мне видео!',
        reply_markup=help_markup()
    )

def help_markup():
    """Создание клавиатуры с кнопками меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('❓ Помощь')
    btn2 = types.KeyboardButton('⚙️ Настройки')
    btn3 = types.KeyboardButton('📊 Статистика')
    markup.add(btn1, btn2, btn3)
    log_and_print("Создана клавиатура с основными кнопками меню")
    return markup

@bot.message_handler(commands=['help'])
def help_command(message):
    """Обработчик команды /help"""
    user = message.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) вызвал команду /help")
    help_message(message)

def help_message(message):
    """Отображение справочной информации"""
    user = message.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) запросил справку")
    
    help_text = ('Необходимо прислать видео, бот обработает его и пришлет вам кружок.\n'
                '1. Если длительность больше 60 секунд, бот его обрежет\n'
                '2. Видео весит не более 12 МБ\n'
                '3. Если видео больше 640x640 пикселей, бот его обрежет\n'
                '4. Видео должно быть отправлено как видео, а не документ\n\n'
                'Доступные команды:\n'
                '⚙️ Настройки - изменить размер кружка\n'
                '📊 Статистика - посмотреть вашу статистику\n'
                '❓ Помощь - показать это сообщение')
    
    bot.send_message(message.chat.id, help_text)
    log_and_print(f"Отправлена справочная информация пользователю {user.username} (ID: {user.id})")

@bot.message_handler(content_types=['text'])
def analyze_text(message):
    """Обработка текстовых сообщений"""
    user = message.from_user
    text = message.text.lower()
    
    log_and_print(f"Получено текстовое сообщение от пользователя {user.username} (ID: {user.id}): {text}")
    
    if 'помощь' in text:
        log_and_print(f"Пользователь {user.username} (ID: {user.id}) запросил помощь через текстовое меню")
        help_message(message)
    elif 'настройки' in text:
        log_and_print(f"Пользователь {user.username} (ID: {user.id}) открыл настройки через текстовое меню")
        settings_command(message)
    elif 'статистика' in text:
        log_and_print(f"Пользователь {user.username} (ID: {user.id}) запросил статистику через текстовое меню")
        stats_command(message)
    else:
        log_and_print(f"Получено неизвестное текстовое сообщение от пользователя {user.username} (ID: {user.id}): {text}")
        help_message(message)  # Показываем справку при неизвестной команде

@bot.message_handler(commands=['start'])
def start_message(message):
    """Обработчик команды /start"""
    user = message.from_user
    log_and_print(f"Пользователь {user.username} (ID: {user.id}) запустил бота")
    
    welcome_text = ('Привет! Я помогу превратить твое видео в видеозаметку (кружок).\n\n'
                   'Используй кнопки меню:\n'
                   '⚙️ Настройки - изменить размер кружка\n'
                   '📊 Статистика - посмотреть вашу статистику\n'
                   '❓ Помощь - показать справку\n\n'
                   'Или просто отправь мне видео!')
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=help_markup()
    )
    log_and_print(f"Отправлено приветственное сообщение пользователю {user.username} (ID: {user.id})")

def resize_frame_with_padding(frame, target_size):
    """Изменение размера кадра с сохранением пропорций и добавлением отступов"""
    height, width = frame.shape[:2]
    
    # Определяем размер стороны для масштабирования
    scale = min(target_size / width, target_size / height)
    new_width = int(width * scale)
    new_height = int(height * scale)
    
    # Изменяем размер с сохранением пропорций
    resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
    
    # Создаем черный квадратный кадр нужного размера
    square = np.zeros((target_size, target_size, 3), dtype=np.uint8)
    
    # Вычисляем отступы для центрирования
    x_offset = (target_size - new_width) // 2
    y_offset = (target_size - new_height) // 2
    
    # Вставляем изображение по центру
    square[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized
    
    return square

def fast_resize_video(input_path, output_path, target_size, quality='medium'):
    """Быстрое изменение размера видео с использованием OpenCV"""
    log_and_print("Начинаем обработку видео...")
    
    try:
        # Открываем видео
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception("Не удалось открыть видео файл")
        
        # Получаем параметры видео
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        log_and_print(f"Параметры исходного видео: {width}x{height}, {fps} FPS, {total_frames} кадров")
        
        # Настраиваем качество видео
        if quality == 'high':
            bitrate = '2M'
            crf = 18
        elif quality == 'medium':
            bitrate = '1M'
            crf = 23
        else:  # low
            bitrate = '500k'
            crf = 28
            
        # Создаем временный файл с помощью OpenCV
        temp_output = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_output, fourcc, fps, (target_size, target_size))
        
        if not out.isOpened():
            raise Exception("Не удалось создать выходной файл")
        
        frames_processed = 0
        start_time = time.time()
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Изменяем размер кадра с сохранением пропорций
            resized_frame = resize_frame_with_padding(frame, target_size)
            out.write(resized_frame)
            
            frames_processed += 1
            if frames_processed % 30 == 0:  # Логируем каждые 30 кадров
                progress = (frames_processed / total_frames) * 100
                elapsed_time = time.time() - start_time
                fps_processing = frames_processed / elapsed_time
                log_and_print(f"Обработано {frames_processed}/{total_frames} кадров ({progress:.1f}%), {fps_processing:.1f} FPS")
        
        # Освобождаем ресурсы OpenCV
        cap.release()
        out.release()
        
        log_and_print(f"Обработка OpenCV завершена. Обработано {frames_processed} кадров за {time.time() - start_time:.1f} секунд")
        
        # Конвертируем в H.264 с помощью ffmpeg для совместимости
        log_and_print("Конвертируем видео в H.264...")
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', temp_output,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', str(crf),
            '-maxrate', bitrate,
            '-bufsize', bitrate,
            '-movflags', '+faststart',
            '-y',
            output_path
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        _, stderr = process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Ошибка при конвертации видео: {stderr.decode()}")
            
        # Удаляем временный файл
        os.unlink(temp_output)
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Итоговый файл пуст или не существует")
            
        log_and_print(f"Видео успешно конвертировано в H.264")
        return True
        
    except Exception as e:
        log_and_print(f"Ошибка при обработке видео: {str(e)}", logging.ERROR)
        # Освобождаем ресурсы в случае ошибки
        if 'cap' in locals():
            cap.release()
        if 'out' in locals():
            out.release()
        if 'temp_output' in locals() and os.path.exists(temp_output):
            try:
                os.unlink(temp_output)
            except:
                pass
        return False

def process_video(message, input_file, output_file):
    """Обработка видео с сохранением во временный файл"""
    try:
        user = message.from_user
        log_and_print(f"Начинаем обработку видео от пользователя {user.username} (ID: {user.id})")
        
        # Получаем настройки пользователя
        user_id = message.from_user.id
        target_size = user_settings[user_id]["video_size"]
        quality = user_settings[user_id]["video_quality"]
        
        # Обрабатываем видео
        success = fast_resize_video(input_file, output_file, target_size, quality)
        if not success:
            raise Exception("Ошибка при обработке видео")
            
        log_and_print(f"Видео успешно обработано и сохранено: {output_file}")
        return True
        
    except Exception as e:
        error_message = f"Ошибка при обработке видео: {str(e)}"
        log_and_print(error_message, logging.ERROR)
        bot.reply_to(message, f"❌ {error_message}")
        return False

@bot.message_handler(content_types=['video'])
def video(message):
    try:
        user = message.from_user
        user_id = user.id
        username = user.username or "Unknown"
        
        # Проверка на флуд
        if check_flood(user_id):
            log_and_print(f"Обнаружен флуд от пользователя {username} (ID: {user_id})", logging.WARNING)
            bot.reply_to(message, "Пожалуйста, подождите минуту перед отправкой следующего видео.")
            return

        # Проверяем размер файла
        file_size_mb = message.video.file_size / (1024 * 1024)
        if file_size_mb > 12:
            log_and_print(f"Файл слишком большой: {file_size_mb:.2f} МБ", logging.WARNING)
            bot.reply_to(message, "Видео слишком большое. Максимальный размер - 12 МБ")
            return
            
        log_and_print(
            f"Получено видео от пользователя {username} (ID: {user_id})\n"
            f"Размер файла: {file_size_mb:.2f} МБ"
        )

        # Получаем настройки пользователя
        target_size = user_settings[user_id]["video_size"]
        quality = user_settings[user_id]["video_quality"]
        
        log_and_print(f"Настройки пользователя: размер={target_size}, качество={quality}")
        
        # Отправляем сообщение о начале обработки
        quality_text = {
            'high': 'высокое',
            'medium': 'среднее',
            'low': 'низкое'
        }.get(quality, 'среднее')
        
        processing_msg = bot.reply_to(
            message,
            f"⚙️ Начинаю обработку видео\n\n"
            f"📐 Размер кружка: {target_size}x{target_size}\n"
            f"🎨 Качество: {quality_text}\n\n"
            f"⏳ Пожалуйста, подождите..."
        )
        
        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file, \
             tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
            
            try:
                # Скачиваем видео
                log_and_print("Скачиваем видео...")
                file_info = bot.get_file(message.video.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                input_file.write(downloaded_file)
                input_file.flush()
                log_and_print("Видео успешно скачано")
                
                # Обновляем сообщение о процессе
                bot.edit_message_text(
                    f"⚙️ Обработка видео\n\n"
                    f"📐 Размер кружка: {target_size}x{target_size}\n"
                    f"🎨 Качество: {quality_text}\n\n"
                    f"📥 Видео загружено\n"
                    f"🔄 Конвертация...",
                    chat_id=processing_msg.chat.id,
                    message_id=processing_msg.message_id
                )
                
                # Обрабатываем видео
                log_and_print("Запускаем обработку видео...")
                success = process_video(message, input_file.name, output_file.name)
                
                if not success:
                    raise Exception("Ошибка при обработке видео")
                
                # Проверяем результат
                if not os.path.exists(output_file.name) or os.path.getsize(output_file.name) == 0:
                    raise Exception("Результирующий файл пуст или не существует")
                
                # Обновляем сообщение о процессе
                bot.edit_message_text(
                    f"⚙️ Обработка видео\n\n"
                    f"📐 Размер кружка: {target_size}x{target_size}\n"
                    f"🎨 Качество: {quality_text}\n\n"
                    f"📥 Видео загружено\n"
                    f"✅ Конвертация завершена\n"
                    f"📤 Отправка...",
                    chat_id=processing_msg.chat.id,
                    message_id=processing_msg.message_id
                )
                
                # Отправляем результат
                log_and_print("Отправляем обработанное видео пользователю...")
                with open(output_file.name, 'rb') as video:
                    bot.send_video_note(message.chat.id, video)
                log_and_print("Видео успешно отправлено")
                
                # Обновляем статистику
                if user_id not in user_stats:
                    user_stats[user_id] = {"processed_videos": 0, "total_size_mb": 0}
                user_stats[user_id]["processed_videos"] += 1
                user_stats[user_id]["total_size_mb"] += file_size_mb
                
                # Финальное сообщение об успешной обработке
                bot.edit_message_text(
                    f"✅ Видео успешно обработано\n\n"
                    f"📐 Размер кружка: {target_size}x{target_size}\n"
                    f"🎨 Качество: {quality_text}\n\n"
                    f"📊 Ваша статистика:\n"
                    f"🎥 Обработано видео: {user_stats[user_id]['processed_videos']}\n"
                    f"💾 Общий размер: {user_stats[user_id]['total_size_mb']:.1f} МБ",
                    chat_id=processing_msg.chat.id,
                    message_id=processing_msg.message_id
                )
                
            except Exception as e:
                error_message = f"Ошибка при обработке видео: {str(e)}"
                log_and_print(error_message, logging.ERROR)
                
                # Обновляем сообщение об ошибке
                try:
                    bot.edit_message_text(
                        f"❌ Ошибка при обработке видео\n\n"
                        f"Причина: {str(e)}",
                        chat_id=processing_msg.chat.id,
                        message_id=processing_msg.message_id
                    )
                except:
                    bot.reply_to(message, f"❌ {error_message}")
            
            finally:
                # Удаляем временные файлы
                try:
                    os.unlink(input_file.name)
                    os.unlink(output_file.name)
                    cleanup_temp_files()
                except Exception as e:
                    log_and_print(f"Ошибка при удалении временных файлов: {str(e)}", logging.ERROR)
    
    except Exception as e:
        error_message = f"Ошибка при обработке видео: {str(e)}"
        log_and_print(error_message, logging.ERROR)
        bot.reply_to(message, f"❌ {error_message}")

def cleanup_temp_files():
    """Очистка всех временных файлов"""
    try:
        # Удаляем все временные файлы moviepy
        temp_files = glob.glob("*TEMP_MPY_*")
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
                log_and_print(f"Удален временный файл: {temp_file}")
            except Exception as e:
                log_and_print(f"Ошибка при удалении {temp_file}: {str(e)}")
        
        # Удаляем файлы с определенными паттернами
        patterns = ["*_resized.mp4", "sigma_video.mp4"]
        for pattern in patterns:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    log_and_print(f"Удален файл: {file}")
                except Exception as e:
                    log_and_print(f"Ошибка при удалении {file}: {str(e)}")
    except Exception as e:
        log_and_print(f"Ошибка при очистке временных файлов: {str(e)}", logging.ERROR)

if __name__ == '__main__':
    try:
        print("Бот запущен...")
        logger.info("Бот запущен")
        # Очищаем временные файлы при запуске
        cleanup_temp_files()
        bot.infinity_polling()
    except Exception as e:
        error_msg = f"Критическая ошибка: {e}"
        print(error_msg)
        logger.critical(error_msg)
        bot.stop_polling()
        executor.shutdown()
