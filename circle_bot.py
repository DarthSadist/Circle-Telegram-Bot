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

# Настройка логирования
logging.basicConfig(
    filename='bot_logs.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('circle_bot')

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
    return (f"📊 Ваша статистика:\n"
            f"Обработано видео: {stats['processed_videos']}\n"
            f"Общий размер: {stats['total_size_mb']:.2f} МБ")

@bot.message_handler(commands=['settings'])
def settings_command(message):
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
    
    current_size = user_settings[message.from_user.id]["video_size"]
    current_quality = user_settings[message.from_user.id]["video_quality"]
    
    bot.send_message(
        message.chat.id,
        f"⚙️ Настройки обработки видео\n\n"
        f"Текущие настройки:\n"
        f"📐 Размер: {current_size}x{current_size}\n"
        f"🎨 Качество: {current_quality}\n\n"
        f"Выберите параметр для настройки:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "show_sizes")
def show_sizes(call):
    markup = types.InlineKeyboardMarkup()
    sizes = [
        (384, "384x384 (компактный)"), 
        (480, "480x480 (оптимальный)"),
        (640, "640x640 (максимальный)")
    ]
    
    for size, text in sizes:
        callback_data = f"size_{size}"
        btn = types.InlineKeyboardButton(text=text, callback_data=callback_data)
        markup.add(btn)
    
    back_btn = types.InlineKeyboardButton("↩️ Назад", callback_data="back_to_settings")
    markup.add(back_btn)
    
    current_size = user_settings[call.from_user.id]["video_size"]
    bot.edit_message_text(
        f"🎯 Настройка размера видеозаметки\n\n"
        f"Текущий размер: {current_size}x{current_size}\n\n"
        f"Выберите желаемый размер кружка:\n"
        f"• Чем больше размер, тем лучше качество\n"
        f"• Чем меньше размер, тем быстрее обработка",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "show_quality")
def show_quality(call):
    markup = types.InlineKeyboardMarkup()
    qualities = [
        ("high", "🎯 Высокое (большой размер)"),
        ("medium", "✨ Среднее (рекомендуется)"),
        ("low", "🚀 Низкое (маленький размер)")
    ]
    
    for quality, text in qualities:
        callback_data = f"quality_{quality}"
        btn = types.InlineKeyboardButton(text=text, callback_data=callback_data)
        markup.add(btn)
    
    back_btn = types.InlineKeyboardButton("↩️ Назад", callback_data="back_to_settings")
    markup.add(back_btn)
    
    current_quality = user_settings[call.from_user.id]["video_quality"]
    bot.edit_message_text(
        f"🎨 Настройка качества видео\n\n"
        f"Текущее качество: {current_quality}\n\n"
        f"Выберите желаемое качество:\n"
        f"• Высокое - лучшее качество, большой размер\n"
        f"• Среднее - оптимальный баланс\n"
        f"• Низкое - быстрая обработка, малый размер",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('size_'))
def handle_size_selection(call):
    size = int(call.data.split('_')[1])
    user_settings[call.from_user.id]["video_size"] = size
    bot.answer_callback_query(
        call.id,
        f"✅ Установлен размер {size}x{size} для выходной видеозаметки",
        show_alert=True
    )
    bot.edit_message_text(
        f"✅ Новый размер видеозаметки: {size}x{size}\n\n"
        "Теперь отправьте мне видео, и я создам из него кружок с выбранным размером.",
        call.message.chat.id,
        call.message.message_id
    )
    logger.info(f"Пользователь {call.from_user.username} (ID: {call.from_user.id}) изменил размер выходной видеозаметки на {size}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_quality_selection(call):
    quality = call.data.split('_')[1]
    user_settings[call.from_user.id]["video_quality"] = quality
    bot.answer_callback_query(
        call.id,
        f"✅ Установлено качество: {quality}",
        show_alert=True
    )
    settings_command(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_settings")
def back_to_settings(call):
    settings_command(call.message)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    stats_text = get_user_stats(message.from_user.id)
    bot.reply_to(message, stats_text)

def help_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('❓ Помощь')
    btn2 = types.KeyboardButton('⚙️ Настройки')
    btn3 = types.KeyboardButton('📊 Статистика')
    markup.add(btn1, btn2, btn3)
    return markup

def help_message(message):
    bot.send_message(message.chat.id, 'Необходимо прислать видео, бот обработает его и пришлет вам кружок.\n'
                                      '1. Если длительность больше 60 секунд, бот его обрежет\n'
                                      '2. Видео весит не более 12 МБ\n'
                                      '3. Если видео больше 640x640 пикселей, бот его обрежет\n'
                                      '4. Видео должно быть отправлено как видео, а не документ\n\n'
                                      'Доступные команды:\n'
                                      '⚙️ Настройки - изменить размер кружка\n'
                                      '📊 Статистика - посмотреть вашу статистику\n'
                                      '❓ Помощь - показать это сообщение')

@bot.message_handler(commands=['start'])
def start_message(message):
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

@bot.message_handler(commands=['help'])
def help_command(message):
    help_message(message)

@bot.message_handler(content_types=['text'])
def analyze_text(message):
    text = message.text.lower()
    if 'помощь' in text:
        help_message(message)
    elif 'настройки' in text:
        settings_command(message)
    elif 'статистика' in text:
        stats_command(message)

def fast_resize_video(input_path, output_path, target_size, quality='medium'):
    """Быстрое изменение размера видео с использованием OpenCV"""
    cap = cv2.VideoCapture(input_path)
    
    # Получаем параметры видео
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"Параметры исходного видео:")
    print(f"- Ширина: {width}px")
    print(f"- Высота: {height}px")
    print(f"- FPS: {fps}")
    print(f"- Количество кадров: {frame_count}")
    
    # Для видеозаметки нужен квадратный размер
    target_size = min(target_size, 640)  # Максимальный размер для видеозаметки
    new_size = target_size
    
    print(f"Создаем квадратное видео {new_size}x{new_size}")
    
    # Настройки качества кодирования
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    
    # Создаем временный файл для первичной обработки
    temp_output = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    
    # Создаем видеописатель
    out = cv2.VideoWriter(temp_output, fourcc, fps, (new_size, new_size))
    
    if not out.isOpened():
        raise Exception("Не удалось создать выходной файл для видео")
    
    frames_processed = 0
    progress_step = max(1, frame_count // 10)  # Обновляем прогресс каждые 10%
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Создаем квадратный кадр
            h, w = frame.shape[:2]
            size = min(h, w)
            x = (w - size) // 2
            y = (h - size) // 2
            frame = frame[y:y+size, x:x+size]
            
            # Оптимизированное изменение размера
            if size != new_size:
                # Используем INTER_AREA для уменьшения и INTER_CUBIC для увеличения
                interpolation = cv2.INTER_AREA if size > new_size else cv2.INTER_CUBIC
                frame = cv2.resize(frame, (new_size, new_size), interpolation=interpolation)
            
            # Применяем настройки качества через постобработку
            if quality == 'high':
                # Минимальное сжатие для высокого качества
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
            elif quality == 'medium':
                # Среднее сжатие
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            else:  # low
                # Максимальное сжатие
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            
            # Применяем сжатие к кадру
            _, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
            frame = cv2.imdecode(encoded_frame, 1)
            
            out.write(frame)
            frames_processed += 1
            
            # Обновляем прогресс
            if frames_processed % progress_step == 0:
                progress = (frames_processed / frame_count) * 100
                print(f"Прогресс обработки: {progress:.1f}%")
        
        # Закрываем видеописатель
        out.release()
        
        # Конвертируем видео в финальный формат с помощью ffmpeg
        print("Выполняем финальную конвертацию...")
        import subprocess
        
        # Настройки качества для ffmpeg
        if quality == 'high':
            crf = "18"  # Высокое качество
        elif quality == 'medium':
            crf = "23"  # Среднее качество
        else:  # low
            crf = "28"  # Низкое качество
        
        # Используем ffmpeg для финальной конвертации
        command = [
            'ffmpeg', '-i', temp_output,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', crf,
            '-y',  # Перезаписывать существующий файл
            output_path
        ]
        
        subprocess.run(command, check=True, capture_output=True)
        
        # Проверяем размер выходного файла
        output_size = os.path.getsize(output_path) / (1024 * 1024)  # в МБ
        print(f"Размер выходного файла: {output_size:.2f} МБ")
        
        return frames_processed
        
    finally:
        cap.release()
        out.release()
        # Удаляем временный файл
        if os.path.exists(temp_output):
            os.unlink(temp_output)

def process_video(input_path, output_path, target_size=384, quality='medium'):
    """Оптимизированная обработка видео для создания видеозаметки"""
    try:
        print(f"Начинаем обработку видео...")
        print(f"Настройки: размер={target_size}x{target_size}, качество={quality}")
        
        # Проверяем длительность видео
        clip = mp.VideoFileClip(input_path)
        duration = clip.duration
        print(f"Длительность видео: {duration:.2f} секунд")
        clip.close()

        # Если видео длиннее 60 секунд, обрезаем его
        temp_cut = None
        if duration > 60:
            print("Видео длиннее 60 секунд, обрезаем...")
            temp_cut = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
            ffmpeg_extract_subclip(input_path, 0, 60, targetname=temp_cut)
            current_input = temp_cut
            print("Обрезка видео завершена")
        else:
            current_input = input_path

        # Изменяем размер видео с помощью OpenCV
        print("Начинаем создание видеозаметки...")
        frames_processed = fast_resize_video(current_input, output_path, target_size, quality)
        print(f"Создание видеозаметки завершено. Обработано кадров: {frames_processed}")

        # Удаляем временный файл если он был создан
        if temp_cut:
            os.unlink(temp_cut)
            print("Временные файлы удалены")

    except Exception as e:
        print(f"❌ Ошибка при обработке видео: {str(e)}")
        raise Exception(f"Ошибка при обработке видео: {str(e)}")

def cleanup_temp_files():
    """Очистка всех временных файлов"""
    try:
        # Удаляем все временные файлы moviepy
        temp_files = glob.glob("*TEMP_MPY_*")
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
                print(f"Удален временный файл: {temp_file}")
            except Exception as e:
                print(f"Ошибка при удалении {temp_file}: {str(e)}")
        
        # Удаляем файлы с определенными паттернами
        patterns = ["*_resized.mp4", "sigma_video.mp4"]
        for pattern in patterns:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    print(f"Удален файл: {file}")
                except Exception as e:
                    print(f"Ошибка при удалении {file}: {str(e)}")
    except Exception as e:
        print(f"Ошибка при очистке временных файлов: {str(e)}")

@bot.message_handler(content_types=['video'])
def video(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or "Unknown"
        
        # Проверка на флуд
        if check_flood(user_id):
            logger.warning(f"Обнаружен флуд от пользователя {username} (ID: {user_id})")
            bot.reply_to(message, "Пожалуйста, подождите минуту перед отправкой следующего видео.")
            return

        file_size_mb = message.video.file_size / (1024 * 1024)
        logger.info(f"Получено видео от пользователя {username} (ID: {user_id}), размер: {file_size_mb:.2f} МБ")
        print(f"\nПолучено новое видео от пользователя {username} (ID: {user_id})")
        print(f"Размер файла: {file_size_mb:.2f} МБ")

        # Обновляем статистику
        user_stats[user_id]["processed_videos"] += 1
        user_stats[user_id]["total_size_mb"] += file_size_mb

        # Проверка размера файла
        if message.video.file_size > 12 * 1024 * 1024:  # 12 МБ
            logger.warning(f"Попытка загрузки большого файла от пользователя {username} (ID: {user_id})")
            print("❌ Видео слишком большое, отправляем сообщение об ошибке")
            bot.reply_to(message, "Видео слишком большое. Максимальный размер - 12 МБ")
            return

        # Получаем настройки пользователя
        target_size = user_settings[user_id]["video_size"]
        quality = user_settings[user_id]["video_quality"]
        
        bot.send_message(
            message.chat.id, 
            f'⚙️ Начинаю обработку видео\n'
            f'Выбранный размер кружка: {target_size}x{target_size}\n'
            f'Качество: {quality}\n'
            f'Пожалуйста, подождите...'
        )
        print("Начинаем обработку видео...")
        logger.info(f"Начало обработки видео от пользователя {username} (ID: {user_id})")
        
        try:
            # Создаем временные файлы
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as input_file, \
                 tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                
                # Скачиваем видео
                print("Скачиваем видео...")
                file_info = bot.get_file(message.video.file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                input_file.write(downloaded_file)
                input_file.flush()
                print("Видео успешно скачано")
                logger.info(f"Видео успешно скачано от пользователя {username}")
                
                # Обрабатываем видео в отдельном потоке
                print("Запускаем обработку видео в отдельном потоке...")
                future = executor.submit(process_video, input_file.name, output_file.name, target_size, quality)
                future.result()
                
                # Отправляем результат
                print("Отправляем обработанное видео пользователю...")
                with open(output_file.name, 'rb') as result_file:
                    bot.send_video_note(message.chat.id, result_file)
                print("Видео успешно отправлено")
                logger.info(f"Видео успешно обработано и отправлено пользователю {username}")
        
        finally:
            # Удаляем временные файлы
            try:
                os.unlink(input_file.name)
                os.unlink(output_file.name)
                print("Временные файлы удалены")
                # Очищаем все оставшиеся временные файлы
                cleanup_temp_files()
                print("Очистка временных файлов завершена")
                logger.info(f"Временные файлы очищены для пользователя {username}")
            except Exception as e:
                error_msg = f"Ошибка при удалении файлов: {str(e)}"
                print(error_msg)
                logger.error(error_msg)
            
    except Exception as e:
        error_message = str(e)
        logger.error(f"Ошибка при обработке видео от пользователя {username}: {error_message}")
        print(f"❌ Ошибка при обработке видео: {error_message}")
        bot.send_message(message.chat.id, f'Произошла ошибка при обработке видео: {error_message}')
        # Пытаемся очистить временные файлы даже в случае ошибки
        cleanup_temp_files()

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
