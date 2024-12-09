# Импортируем необходимые библиотеки
import telebot
import os
from dotenv import load_dotenv
from moviepy.editor import VideoFileClip
from telebot import types
import tempfile
from concurrent.futures import ThreadPoolExecutor
import time
import logging
import shutil
import cv2
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
from logging.handlers import RotatingFileHandler

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

# Максимальный размер лог-файла (5 МБ)
MAX_LOG_SIZE = 5 * 1024 * 1024
# Максимальное количество файлов логов
MAX_LOG_FILES = 3

# Настройка логирования с ротацией
handler = RotatingFileHandler(
    'bot_logs.log',
    maxBytes=MAX_LOG_SIZE,
    backupCount=MAX_LOG_FILES
)
handler.setFormatter(formatter)
logger.addHandler(handler)

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
    """Проверка на флуд
    Возвращает True если сообщение можно обработать, False если обнаружен флуд"""
    current_time = time.time()
    
    if user_id not in user_messages:
        user_messages[user_id] = []
    
    # Удаляем устаревшие сообщения
    user_messages[user_id] = [msg_time for msg_time in user_messages[user_id] 
                            if current_time - msg_time < FLOOD_TIME]
    
    # Проверяем количество сообщений
    if len(user_messages[user_id]) >= FLOOD_LIMIT:
        return False
    
    # Добавляем новое сообщение
    user_messages[user_id].append(current_time)
    return True

try:
    bot = telebot.TeleBot(TOKEN)
    executor = ThreadPoolExecutor(max_workers=3)
    logger.info("Бот успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации бота: {str(e)}")
    print(f"❌ Ошибка при инициализации бота: {str(e)}")
    sys.exit(1)

# Настройки видео
DEFAULT_SETTINGS = {
    "video_size": 640,  # размер видео по умолчанию
    "video_quality": "medium"  # качество по умолчанию
}

QUALITY_SETTINGS = {
    'high': {'bitrate': '2000k', 'preset': 'medium'},
    'medium': {'bitrate': '1000k', 'preset': 'faster'},
    'low': {'bitrate': '500k', 'preset': 'veryfast'}
}

# Хранение настроек пользователей
user_settings = defaultdict(lambda: DEFAULT_SETTINGS.copy())

def get_user_settings(user_id):
    """Получение настроек пользователя"""
    return user_settings[user_id]

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

# Константы для обработки видео
MAX_VIDEO_SIZE_MB = 12
MAX_VIDEO_DURATION = 60  # максимальная длительность в секундах
ALLOWED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.mkv']

# Утилиты для обработки ошибок Telegram API
# =========================================
def safe_reply_to(message, text):
    """Безопасный ответ на сообщение с обработкой ошибок"""
    try:
        return bot.reply_to(message, text)
    except Exception as e:
        log_and_print(f"Ошибка при ответе на сообщение: {str(e)}", level=logging.ERROR)
        return None

def safe_send_message(chat_id, text, reply_markup=None):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        log_and_print(f"Ошибка при отправке сообщения: {str(e)}", level=logging.ERROR)
        return None

def safe_edit_message(chat_id, message_id, text, reply_markup=None):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        return bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
    except Exception as e:
        log_and_print(f"Ошибка при редактировании сообщения: {str(e)}", level=logging.ERROR)
        return None

def safe_answer_callback(callback_id, text, show_alert=False):
    """Безопасный ответ на callback с обработкой ошибок"""
    try:
        bot.answer_callback_query(callback_id, text, show_alert=show_alert)
    except Exception as e:
        log_and_print(f"Ошибка при ответе на callback: {str(e)}", level=logging.ERROR)

# Утилиты для работы с файлами
# ============================
def ensure_temp_dir():
    """Создание и проверка временной директории"""
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def cleanup_temp_files(max_age_hours=24):
    """Улучшенная очистка временных файлов с учетом времени их создания"""
    try:
        temp_dir = ensure_temp_dir()
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                # Проверяем время создания файла
                file_age = current_time - os.path.getctime(file_path)
                if file_age > max_age_seconds:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                    log_and_print(f"Удален старый временный файл: {filename}")
            except Exception as e:
                log_and_print(f"Ошибка при удалении {filename}: {str(e)}", level=logging.ERROR)
    except Exception as e:
        log_and_print(f"Ошибка при очистке временных файлов: {str(e)}", level=logging.ERROR)

# Утилиты для обработки видео
# ============================
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
        log_and_print(f"Ошибка при получении информации о видео: {str(e)}", level=logging.ERROR)
        return None

def validate_video(message, file_path):
    """Проверка параметров видео"""
    try:
        # Проверка размера файла
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > MAX_VIDEO_SIZE_MB:
            log_and_print(f"⚠️ Видео превышает лимит размера: {file_size_mb:.1f}MB")
            safe_reply_to(message, f"⚠️ Видео превышает лимит {MAX_VIDEO_SIZE_MB}MB. Начинаю сжатие...")
            
            # Сжимаем видео
            compressed_file = compress_video(file_path, MAX_VIDEO_SIZE_MB)
            if compressed_file and compressed_file != file_path:
                new_size = os.path.getsize(compressed_file) / (1024 * 1024)
                safe_reply_to(message, f"✅ Видео успешно сжато до {new_size:.1f}MB")
                return compressed_file
            
        # Проверка длительности
        video = cv2.VideoCapture(file_path)
        duration = int(video.get(cv2.CAP_PROP_FRAME_COUNT) / video.get(cv2.CAP_PROP_FPS))
        video.release()
        
        if duration > MAX_VIDEO_DURATION:
            log_and_print(f"❌ Видео слишком длинное: {duration} секунд")
            safe_reply_to(message, f"❌ Видео слишком длинное. Максимальная длительность: {MAX_VIDEO_DURATION} секунд")
            return None
            
        return file_path
        
    except Exception as e:
        log_and_print(f"❌ Ошибка при валидации видео: {str(e)}", level=logging.ERROR)
        safe_reply_to(message, "❌ Ошибка при проверке видео")
        return None

def compress_video(input_file, max_size_mb=12):
    """Сжимает видео до указанного размера"""
    try:
        current_size = os.path.getsize(input_file) / (1024 * 1024)  # размер в МБ
        if current_size <= max_size_mb:
            return input_file

        log_and_print(f"🔄 Сжатие видео с {current_size:.1f}MB до {max_size_mb}MB...")
        
        # Создаем временный файл для сжатого видео
        temp_dir = ensure_temp_dir()
        compressed_file = os.path.join(temp_dir, f"compressed_{os.path.basename(input_file)}")
        
        # Загружаем видео
        clip = VideoFileClip(input_file)
        
        # Рассчитываем целевой битрейт (немного меньше максимального размера для гарантии)
        target_size = max_size_mb * 1024 * 1024 * 0.95  # 95% от максимального размера в байтах
        target_bitrate = int((target_size * 8) / clip.duration)  # конвертируем в биты и делим на длительность
        
        # Сжимаем видео с пониженным битрейтом
        clip.write_videofile(
            compressed_file,
            codec='libx264',
            bitrate=f"{target_bitrate//1000}k",
            preset='ultrafast',  # используем самый быстрый пресет
            audio=False,  # отключаем аудио для уменьшения размера
            threads=2,  # ограничиваем количество потоков для экономии памяти
            logger=None  # отключаем логи moviepy
        )
        
        # Закрываем клип для освобождения ресурсов
        clip.close()
        
        # Проверяем результат
        new_size = os.path.getsize(compressed_file) / (1024 * 1024)
        log_and_print(f"✅ Видео успешно сжато до {new_size:.1f}MB")
        
        # Если размер все еще превышает лимит, пробуем еще раз с более агрессивным сжатием
        if new_size > max_size_mb:
            log_and_print("⚠️ Размер все еще превышает лимит, применяю дополнительное сжатие...")
            clip = VideoFileClip(compressed_file)
            target_bitrate = int(target_bitrate * 0.8)  # уменьшаем битрейт на 20%
            
            # Создаем новый файл для второй попытки
            final_file = os.path.join(temp_dir, f"final_{os.path.basename(input_file)}")
            
            clip.write_videofile(
                final_file,
                codec='libx264',
                bitrate=f"{target_bitrate//1000}k",
                preset='ultrafast',
                audio=False,
                threads=2,
                logger=None
            )
            
            clip.close()
            
            # Удаляем промежуточный файл
            try:
                os.remove(compressed_file)
            except:
                pass
                
            compressed_file = final_file
            new_size = os.path.getsize(compressed_file) / (1024 * 1024)
            log_and_print(f"✅ Дополнительное сжатие завершено. Новый размер: {new_size:.1f}MB")
        
        return compressed_file
        
    except Exception as e:
        log_and_print(f"❌ Ошибка при сжатии видео: {str(e)}", level=logging.ERROR)
        if 'clip' in locals():
            clip.close()
        raise

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
        log_and_print(error_msg, level=logging.ERROR)
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
        log_and_print(error_msg, level=logging.ERROR)
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
        log_and_print(f"🎥 Начинаем обработку видео от пользователя {user.username} (ID: {user.id})")
        
        # Получаем информацию о видео
        video_info = get_video_info(input_file)
        if not video_info:
            raise Exception("Не удалось получить информацию о видео")
        
        # Проверка размера видео
        file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
        if file_size_mb > MAX_VIDEO_SIZE_MB:
            log_and_print(f"⚠️ Видео слишком большое: {file_size_mb:.2f} MB")
            safe_send_message(message.chat.id, f"Видео превышает допустимый размер {MAX_VIDEO_SIZE_MB} MB")
            return False
        
        # Получаем настройки пользователя
        settings = get_user_settings(user.id)
        target_size = 384  # Фиксированный размер для video note (384x384)
        quality = settings["video_quality"]
        
        log_and_print(f"⚙️ Применяем настройки: размер={target_size}x{target_size}, качество={quality}")
        
        try:
            # Открываем исходное видео
            cap = cv2.VideoCapture(input_file)
            if not cap.isOpened():
                raise Exception("Не удалось открыть видео файл")
            
            # Создаем выходной файл
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(
                output_file,
                fourcc,
                video_info['fps'],
                (target_size, target_size)
            )
            
            if not out.isOpened():
                raise Exception("Не удалось создать выходной файл")
            
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frames_processed = 0
            start_time = time.time()
            last_progress = 0
            
            log_and_print(f"🎬 Начало обработки кадров. Всего кадров: {frame_count}")
            
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
                        f"⏳ Прогресс: {frames_processed}/{frame_count} кадров "
                        f"({current_progress:.1f}%), {fps:.1f} FPS"
                    )
                    last_progress = current_progress
                
                # Обрабатываем кадр
                h, w = frame.shape[:2]
                if h > w:
                    new_h = int(h * target_size / w)
                    frame = cv2.resize(frame, (target_size, new_h))
                    start = (new_h - target_size) // 2
                    frame = frame[start:start + target_size, :target_size]
                else:
                    new_w = int(w * target_size / h)
                    frame = cv2.resize(frame, (new_w, target_size))
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
            
            log_and_print("✅ Обработка кадров завершена")
            
            # Освобождаем ресурсы
            cap.release()
            out.release()
            
            # Конвертируем в формат, поддерживаемый Telegram для video note
            temp_dir = ensure_temp_dir()
            final_output = os.path.join(temp_dir, f"final_{os.path.basename(output_file)}")
            
            clip = VideoFileClip(output_file)
            original_clip = VideoFileClip(input_file)
            
            # Если в оригинальном видео есть звук, добавляем его
            if original_clip.audio is not None:
                clip = clip.set_audio(original_clip.audio)
            
            clip.write_videofile(
                final_output,
                codec='libx264',
                audio=True,  # Включаем звук
                audio_codec='aac',  # Используем AAC кодек для звука
                preset='ultrafast'
            )
            clip.close()
            original_clip.close()
            
            # Перемещаем финальное видео
            shutil.move(final_output, output_file)
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                log_and_print("✅ Видео успешно сохранено")
                return True
            else:
                raise Exception("Ошибка при сохранении видео")
            
        except Exception as e:
            log_and_print(f"❌ Ошибка при обработке видео: {str(e)}", level=logging.ERROR)
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except:
                    pass
            raise
            
        finally:
            # Освобождаем ресурсы
            if 'cap' in locals():
                cap.release()
            if 'out' in locals():
                out.release()
                
    except Exception as e:
        error_message = f"❌ Ошибка при обработке видео: {str(e)}"
        log_and_print(error_message, level=logging.ERROR)
        return False

def send_video_with_retry(chat_id, video_path, reply_to_message_id, max_retries=3, timeout=60):
    """Отправка видео с повторными попытками"""
    for attempt in range(max_retries):
        try:
            with open(video_path, 'rb') as video:
                log_and_print(f"📤 Попытка отправки видео {attempt + 1}/{max_retries}...")
                return bot.send_video_note(
                    chat_id,
                    video,
                    reply_to_message_id=reply_to_message_id,
                    timeout=timeout
                )
        except Exception as e:
            if attempt < max_retries - 1:
                delay = (attempt + 1) * 5  # увеличиваем задержку с каждой попыткой
                log_and_print(f"⚠️ Ошибка при отправке видео: {str(e)}. Повторная попытка через {delay} сек...")
                time.sleep(delay)
            else:
                raise

@bot.message_handler(content_types=['video'])
def video(message):
    """Обработчик видео с расширенной валидацией"""
    try:
        user = message.from_user
        log_and_print(f"📥 Получено видео от пользователя {user.username} (ID: {user.id})")
        
        # Проверяем флуд
        if not check_flood(message.from_user.id):
            log_and_print(f"⚠️ Обнаружен флуд от пользователя {user.username}")
            safe_reply_to(message, f"⚠️ Пожалуйста, подождите {FLOOD_TIME} секунд перед отправкой следующего видео")
            return

        # Сообщаем о начале обработки
        processing_msg = safe_reply_to(message, "🎥 Начинаю обработку вашего видео...")
        
        log_and_print("🔍 Проверка параметров видео...")
        safe_edit_message(message.chat.id, processing_msg.message_id, "🔍 Проверяю параметры видео...")
        
        # Очистка старых файлов
        log_and_print("🧹 Очистка временных файлов...")
        cleanup_temp_files()
        
        # Создание временной директории
        temp_dir = ensure_temp_dir()
        log_and_print("📁 Временная директория создана")
        
        # Загрузка видео
        log_and_print("⬇️ Загрузка видео...")
        safe_edit_message(message.chat.id, processing_msg.message_id, "⬇️ Загружаю видео...")
        
        file_info = bot.get_file(message.video.file_id)
        input_file = os.path.join(temp_dir, f"input_{file_info.file_id}.mp4")
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(input_file, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Получаем информацию о загруженном файле
        file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
        duration = message.video.duration
        width = message.video.width
        height = message.video.height
        
        # Формируем сообщение с информацией о загруженном файле
        file_info_text = (
            "📁 Информация о загруженном файле:\n"
            f"▫️ Размер: {file_size_mb:.1f} MB\n"
            f"▫️ Длительность: {duration} сек\n"
            f"▫️ Разрешение: {width}x{height}\n"
            f"▫️ Имя файла: {message.video.file_name if message.video.file_name else 'Без имени'}"
        )
        
        # Отправляем информацию пользователю
        safe_reply_to(message, file_info_text)
        
        log_and_print("✅ Видео успешно загружено")
        safe_edit_message(message.chat.id, processing_msg.message_id, "✅ Видео загружено\n⚙️ Проверяю размер и длительность...")
        
        # Валидация видео
        validated_file = validate_video(message, input_file)
        if not validated_file:
            log_and_print("❌ Видео не прошло валидацию")
            safe_edit_message(message.chat.id, processing_msg.message_id, "❌ Видео не соответствует требованиям")
            return
            
        # Вывод информации о видео
        video_info = get_video_info(validated_file)
        if video_info:
            info_text = (
                "📊 Параметры видео:\n"
                f"▫️ Размер: {os.path.getsize(validated_file) / (1024 * 1024):.1f} MB\n"
                f"▫️ Длительность: {video_info['duration']:.1f} сек\n"
                "🎬 Начинаю создание кругового видео..."
            )
            safe_edit_message(message.chat.id, processing_msg.message_id, info_text)
            log_and_print(
                "📊 Параметры исходного видео:\n"
                f"- Размер: {os.path.getsize(validated_file) / (1024 * 1024):.2f} MB\n"
                f"- Ширина: {video_info['width']}px\n"
                f"- Высота: {video_info['height']}px\n"
                f"- FPS: {video_info['fps']}\n"
                f"- Длительность: {video_info['duration']:.1f} сек"
            )
        
        # Обработка видео
        log_and_print("🔄 Начало обработки видео...")
        output_file = os.path.join(temp_dir, f"output_{file_info.file_id}.mp4")
        
        if process_video(message, validated_file, output_file):
            # Отправка обработанного видео
            log_and_print("⬆️ Отправка обработанного видео...")
            safe_edit_message(message.chat.id, processing_msg.message_id, "⬆️ Отправляю обработанное видео...")
            
            try:
                send_video_with_retry(
                    message.chat.id,
                    output_file,
                    message.message_id
                )
                log_and_print("✅ Видео успешно отправлено")
                safe_edit_message(message.chat.id, processing_msg.message_id, "✨ Готово! Ваше круговое видео отправлено")
            except Exception as e:
                error_message = f"❌ Ошибка при отправке видео: {str(e)}"
                log_and_print(error_message, level=logging.ERROR)
                safe_edit_message(
                    message.chat.id,
                    processing_msg.message_id,
                    "❌ Не удалось отправить видео. Попробуйте еще раз или отправьте видео меньшего размера."
                )
        
    except Exception as e:
        error_message = f"❌ Ошибка при обработке видео: {str(e)}"
        log_and_print(error_message, level=logging.ERROR)
        if 'processing_msg' in locals():
            safe_edit_message(message.chat.id, processing_msg.message_id, "❌ Произошла ошибка при обработке видео")
        else:
            safe_reply_to(message, "❌ Произошла ошибка при обработке видео")
        
    finally:
        # Очистка временных файлов
        log_and_print("🧹 Очистка временных файлов...")
        cleanup_temp_files()

def safe_edit_message(chat_id, message_id, text):
    """Безопасное редактирование сообщения"""
    try:
        return bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id
        )
    except Exception as e:
        log_and_print(f"⚠️ Ошибка при редактировании сообщения: {str(e)}", level=logging.WARNING)
        return None

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
