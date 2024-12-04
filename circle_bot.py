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
import shutil

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

# Константы для сообщений об ошибках
ERROR_MESSAGES = {
    'file_too_large': "Видео слишком большое. Максимальный размер - 12 МБ",
    'processing_error': "Ошибка при обработке видео",
    'empty_file': "Ошибка: пустой файл",
    'flood_control': "Пожалуйста, подождите минуту перед отправкой следующего видео",
    'telegram_error': "Ошибка при отправке сообщения в Telegram",
    'download_error': "Ошибка при скачивании видео",
    'conversion_error': "Ошибка при конвертации видео",
}

# Константы для настроек
DEFAULT_SETTINGS = {
    "video_size": 384,
    "video_quality": "medium"
}

QUALITY_SETTINGS = {
    'high': {'bitrate': '2M', 'preset': 'medium'},
    'medium': {'bitrate': '1M', 'preset': 'faster'},
    'low': {'bitrate': '500k', 'preset': 'veryfast'}
}

# Утилиты для обработки ошибок Telegram API
def safe_edit_message(bot, message_id, chat_id, text, reply_markup=None):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            log_and_print(f"Ошибка при редактировании сообщения: {str(e)}", logging.WARNING)

def safe_send_message(bot, chat_id, text, reply_markup=None):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except telebot.apihelper.ApiTelegramException as e:
        log_and_print(f"Ошибка при отправке сообщения: {str(e)}", logging.ERROR)
        return None

def safe_reply_to(bot, message, text):
    """Безопасный ответ на сообщение с обработкой ошибок"""
    try:
        return bot.reply_to(message, text)
    except telebot.apihelper.ApiTelegramException as e:
        log_and_print(f"Ошибка при ответе на сообщение: {str(e)}", logging.ERROR)
        return None

def safe_answer_callback(bot, callback_id, text, show_alert=False):
    """Безопасный ответ на callback с обработкой ошибок"""
    try:
        bot.answer_callback_query(callback_id, text, show_alert=show_alert)
    except telebot.apihelper.ApiTelegramException as e:
        log_and_print(f"Ошибка при ответе на callback: {str(e)}", logging.ERROR)

# Утилиты для работы с файлами
def ensure_temp_dir():
    """Создание и проверка временной директории"""
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def cleanup_temp_files():
    """Улучшенная очистка временных файлов"""
    try:
        temp_dir = ensure_temp_dir()
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                log_and_print(f"Ошибка при удалении {file_path}: {str(e)}", logging.WARNING)
        log_and_print("Временные файлы успешно очищены")
    except Exception as e:
        log_and_print(f"Ошибка при очистке временных файлов: {str(e)}", logging.ERROR)

# Утилиты для обработки видео
def get_video_info(video_path):
    """Получение информации о видео"""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("Не удалось открыть видео файл")
            
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        
        cap.release()
        return {
            'width': width,
            'height': height,
            'fps': fps,
            'frame_count': frame_count,
            'duration': duration
        }
    except Exception as e:
        log_and_print(f"Ошибка при получении информации о видео: {str(e)}", logging.ERROR)
        return None

def validate_video(message):
    """Проверка видео на соответствие требованиям"""
    try:
        file_size_mb = message.video.file_size / (1024 * 1024)
        if file_size_mb > 12:
            safe_reply_to(bot, message, ERROR_MESSAGES['file_too_large'])
            log_and_print(f"Файл слишком большой: {file_size_mb:.2f} МБ", logging.WARNING)
            return False
            
        duration = message.video.duration
        if duration > 60:
            safe_reply_to(bot, message, "Видео слишком длинное. Максимальная длительность - 60 секунд")
            log_and_print(f"Видео слишком длинное: {duration} секунд", logging.WARNING)
            return False
            
        return True
    except Exception as e:
        log_and_print(f"Ошибка при проверке видео: {str(e)}", logging.ERROR)
        return False

def get_user_settings(user_id):
    """Получение настроек пользователя с созданием по умолчанию при необходимости"""
    if user_id not in user_settings:
        user_settings[user_id] = DEFAULT_SETTINGS.copy()
        log_and_print(f"Созданы настройки по умолчанию для пользователя ID: {user_id}")
    return user_settings[user_id]

# Настройки пользователей
user_settings = defaultdict(lambda: DEFAULT_SETTINGS.copy())
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
        user_settings[user.id] = DEFAULT_SETTINGS.copy()
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

def process_video(message, input_file, output_file):
    """Обработка видео с сохранением во временный файл"""
    try:
        user = message.from_user
        log_and_print(f"Начинаем обработку видео от пользователя {user.username} (ID: {user.id})")
        
        # Получаем информацию о видео
        video_info = get_video_info(input_file)
        if not video_info:
            raise Exception("Не удалось получить информацию о видео")
            
        log_and_print(
            f"Параметры исходного видео:\n"
            f"- Ширина: {video_info['width']}px\n"
            f"- Высота: {video_info['height']}px\n"
            f"- FPS: {video_info['fps']}\n"
            f"- Количество кадров: {video_info['frame_count']}"
        )
        
        # Получаем настройки пользователя
        settings = get_user_settings(user.id)
        target_size = settings["video_size"]
        quality = settings["video_quality"]
        quality_params = QUALITY_SETTINGS[quality]
        
        log_and_print(f"Применяем настройки: размер={target_size}x{target_size}, качество={quality}")
        
        # Создаем временные файлы в выделенной директории
        temp_dir = ensure_temp_dir()
        temp_output = os.path.join(temp_dir, f"temp_output_{int(time.time())}.mp4")
        
        try:
            # Открываем исходное видео
            cap = cv2.VideoCapture(input_file)
            if not cap.isOpened():
                raise Exception("Не удалось открыть видео файл")
            
            # Создаем выходной файл
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(
                temp_output,
                fourcc,
                video_info['fps'],
                (target_size, target_size)
            )
            
            if not out.isOpened():
                raise Exception("Не удалось создать выходной файл")
            
            frame_count = video_info['frame_count']
            frames_processed = 0
            start_time = time.time()
            last_progress = 0
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                frames_processed += 1
                current_progress = (frames_processed / frame_count) * 100
                
                # Логируем прогресс каждые 10%
                if current_progress - last_progress >= 10:
                    elapsed_time = time.time() - start_time
                    fps = frames_processed / elapsed_time if elapsed_time > 0 else 0
                    log_and_print(
                        f"Обработано {frames_processed}/{frame_count} кадров "
                        f"({current_progress:.1f}%), {fps:.1f} FPS"
                    )
                    last_progress = current_progress
                
                # Обрабатываем кадр
                # Изменяем размер с сохранением пропорций
                h, w = frame.shape[:2]
                if h > w:
                    new_h = int(h * target_size / w)
                    frame = cv2.resize(frame, (target_size, new_h))
                    # Обрезаем центр
                    start = (new_h - target_size) // 2
                    frame = frame[start:start + target_size, :target_size]
                else:
                    new_w = int(w * target_size / h)
                    frame = cv2.resize(frame, (new_w, target_size))
                    # Обрезаем центр
                    start = (new_w - target_size) // 2
                    frame = frame[:target_size, start:start + target_size]
                
                # Создаем круглую маску
                mask = np.zeros((target_size, target_size), dtype=np.uint8)
                cv2.circle(
                    mask,
                    (target_size // 2, target_size // 2),
                    target_size // 2,
                    255,
                    -1
                )
                
                # Применяем маску
                frame_channels = cv2.split(frame)
                masked_channels = [
                    cv2.bitwise_and(channel, channel, mask=mask)
                    for channel in frame_channels
                ]
                frame = cv2.merge(masked_channels)
                
                # Записываем кадр
                out.write(frame)
            
            # Освобождаем ресурсы
            cap.release()
            out.release()
            
            elapsed_time = time.time() - start_time
            fps = frame_count / elapsed_time if elapsed_time > 0 else 0
            log_and_print(
                f"Обработка OpenCV завершена. "
                f"Обработано {frame_count} кадров за {elapsed_time:.1f} секунд"
            )
            
            # Конвертируем в H.264 с заданным качеством
            log_and_print("Конвертируем видео в H.264...")
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Перезаписывать файл если существует
                '-i', temp_output,  # Входной файл
                '-c:v', 'libx264',  # Кодек H.264
                '-preset', quality_params['preset'],  # Предустановка качества
                '-b:v', quality_params['bitrate'],  # Битрейт
                '-movflags', '+faststart',  # Оптимизация для веб
                output_file  # Выходной файл
            ]
            
            result = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if result.returncode != 0:
                raise Exception(
                    f"Ошибка FFmpeg: {result.stderr.decode('utf-8')}"
                )
            
            log_and_print("Видео успешно конвертировано в H.264")
            
            # Проверяем результат
            if not os.path.exists(output_file):
                raise Exception("Файл не создан")
                
            file_size = os.path.getsize(output_file)
            if file_size == 0:
                raise Exception("Создан пустой файл")
                
            file_size_mb = file_size / (1024 * 1024)
            log_and_print(f"Размер выходного файла: {file_size_mb:.2f} МБ")
            
            return True
            
        finally:
            # Очищаем временные файлы
            try:
                if os.path.exists(temp_output):
                    os.unlink(temp_output)
            except Exception as e:
                log_and_print(f"Ошибка при удалении временного файла: {str(e)}", logging.WARNING)
                
    except Exception as e:
        error_message = f"Ошибка при обработке видео: {str(e)}"
        log_and_print(error_message, logging.ERROR)
        safe_reply_to(bot, message, f"❌ {error_message}")
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
            safe_reply_to(bot, message, ERROR_MESSAGES['flood_control'])
            return

        # Проверяем видео на соответствие требованиям
        if not validate_video(message):
            return
            
        log_and_print(
            f"Получено видео от пользователя {username} (ID: {user_id})\n"
            f"Размер файла: {message.video.file_size / (1024 * 1024):.2f} МБ"
        )

        # Получаем настройки пользователя
        settings = get_user_settings(user_id)
        target_size = settings["video_size"]
        quality = settings["video_quality"]
        
        # Получаем текстовое описание качества
        quality_text = {
            'high': 'высокое',
            'medium': 'среднее',
            'low': 'низкое'
        }.get(quality, 'среднее')
        
        # Отправляем сообщение о начале обработки
        processing_msg = safe_reply_to(
            bot,
            message,
            f"⚙️ Начинаю обработку видео\n\n"
            f"📐 Размер кружка: {target_size}x{target_size}\n"
            f"🎨 Качество: {quality_text}\n\n"
            f"⏳ Пожалуйста, подождите..."
        )
        
        if not processing_msg:
            return
        
        log_and_print(f"Настройки пользователя: размер={target_size}, качество={quality}")
        
        # Создаем временные файлы в выделенной директории
        temp_dir = ensure_temp_dir()
        input_path = os.path.join(temp_dir, f"input_{int(time.time())}.mp4")
        output_path = os.path.join(temp_dir, f"output_{int(time.time())}.mp4")
        
        try:
            # Скачиваем видео
            log_and_print("Скачиваем видео...")
            try:
                file_info = bot.get_file(message.video.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                with open(input_path, 'wb') as f:
                    f.write(downloaded_file)
                log_and_print("Видео успешно скачано")
            except Exception as e:
                raise Exception(f"Ошибка при скачивании видео: {str(e)}")
            
            # Обновляем сообщение о процессе
            safe_edit_message(
                bot,
                processing_msg.message_id,
                processing_msg.chat.id,
                f"⚙️ Обработка видео\n\n"
                f"📐 Размер кружка: {target_size}x{target_size}\n"
                f"🎨 Качество: {quality_text}\n\n"
                f"📥 Видео загружено\n"
                f"🔄 Конвертация..."
            )
            
            # Обрабатываем видео
            log_and_print("Запускаем обработку видео...")
            success = process_video(message, input_path, output_path)
            
            if not success:
                raise Exception(ERROR_MESSAGES['processing_error'])
            
            # Проверяем результат
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception(ERROR_MESSAGES['empty_file'])
            
            # Обновляем сообщение о процессе
            safe_edit_message(
                bot,
                processing_msg.message_id,
                processing_msg.chat.id,
                f"⚙️ Обработка видео\n\n"
                f"📐 Размер кружка: {target_size}x{target_size}\n"
                f"🎨 Качество: {quality_text}\n\n"
                f"📥 Видео загружено\n"
                f"✅ Конвертация завершена\n"
                f"📤 Отправка..."
            )
            
            # Отправляем результат
            log_and_print("Отправляем обработанное видео пользователю...")
            with open(output_path, 'rb') as video:
                sent = bot.send_video_note(message.chat.id, video)
                if not sent:
                    raise Exception(ERROR_MESSAGES['telegram_error'])
            
            log_and_print("Видео успешно отправлено")
            
            # Обновляем статистику
            if user_id not in user_stats:
                user_stats[user_id] = {"processed_videos": 0, "total_size_mb": 0}
            user_stats[user_id]["processed_videos"] += 1
            user_stats[user_id]["total_size_mb"] += message.video.file_size / (1024 * 1024)
            
            # Финальное сообщение об успешной обработке
            safe_edit_message(
                bot,
                processing_msg.message_id,
                processing_msg.chat.id,
                f"✅ Видео успешно обработано\n\n"
                f"📐 Размер кружка: {target_size}x{target_size}\n"
                f"🎨 Качество: {quality_text}\n\n"
                f"📊 Ваша статистика:\n"
                f"🎥 Обработано видео: {user_stats[user_id]['processed_videos']}\n"
                f"💾 Общий размер: {user_stats[user_id]['total_size_mb']:.1f} МБ"
            )
            
        except Exception as e:
            error_message = str(e)
            log_and_print(f"Ошибка при обработке видео: {error_message}", logging.ERROR)
            
            # Обновляем сообщение об ошибке
            if processing_msg:
                safe_edit_message(
                    bot,
                    processing_msg.message_id,
                    processing_msg.chat.id,
                    f"❌ {error_message}"
                )
            
        finally:
            # Удаляем временные файлы
            try:
                for path in [input_path, output_path]:
                    if os.path.exists(path):
                        os.unlink(path)
                log_and_print("Временные файлы удалены")
            except Exception as e:
                log_and_print(f"Ошибка при удалении временных файлов: {str(e)}", logging.WARNING)
            
            # Очищаем все временные файлы
            cleanup_temp_files()
            
    except Exception as e:
        error_message = f"Критическая ошибка при обработке видео: {str(e)}"
        log_and_print(error_message, logging.ERROR)
        safe_reply_to(bot, message, f"❌ {error_message}")

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
