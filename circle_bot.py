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

load_dotenv()
bot = telebot.TeleBot(os.getenv('TOKEN'))
executor = ThreadPoolExecutor(max_workers=3)

def help_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('help')
    markup.add(btn1)
    return markup

def help_message(message):
    bot.send_message(message.chat.id, 'Необходимо прислать видео, бот обработает его и пришлет вам кружок.\n'
                                      '1. Если длительность больше 60 секунд, бот его обрежет\n'
                                      '2.Видео весит не более 12 МБ\n '
                                      '3. Если видео больше 640x640 пикселей, бот его обрежет.\n4. Видео прислано не документом')

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, 'скиньте сюда видео', reply_markup=help_markup())

@bot.message_handler(commands=['help'])
def help_command(message):
    help_message(message)

@bot.message_handler(content_types=['text'])
def analyze_text(message):
    if message.text == 'help':
        help_message(message)

def fast_resize_video(input_path, output_path, target_size):
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
    
    # Создаем видеописатель
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (new_size, new_size))
    
    frames_processed = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Создаем квадратный кадр
        h, w = frame.shape[:2]
        # Определяем размер меньшей стороны
        size = min(h, w)
        # Вычисляем координаты для обрезки по центру
        x = (w - size) // 2
        y = (h - size) // 2
        # Обрезаем кадр до квадрата
        frame = frame[y:y+size, x:x+size]
        
        # Изменяем размер до целевого
        if size != new_size:
            frame = cv2.resize(frame, (new_size, new_size), interpolation=cv2.INTER_AREA)
            
        out.write(frame)
        frames_processed += 1
        if frames_processed % 100 == 0:
            print(f"Обработано кадров: {frames_processed}/{frame_count}")
    
    print(f"Обработка видео завершена. Всего обработано кадров: {frames_processed}")
    cap.release()
    out.release()

def process_video(input_path, output_path):
    """Оптимизированная обработка видео для создания видеозаметки"""
    try:
        print(f"Начинаем обработку видео...")
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
        # Для видеозаметки используем размер 384x384 (рекомендованный размер для Telegram)
        fast_resize_video(current_input, output_path, 384)
        print("Создание видеозаметки завершено")

        # Удаляем временный файл если он был создан
        if temp_cut:
            os.unlink(temp_cut)
            print("Временные файлы удалены")

    except Exception as e:
        print(f"❌ Ошибка при обработке видео: {str(e)}")
        raise Exception(f"Ошибка при обработке видео: {str(e)}")

@bot.message_handler(content_types=['video'])
def video(message):
    try:
        file_size_mb = message.video.file_size / (1024 * 1024)
        print(f"\nПолучено новое видео от пользователя {message.from_user.username} (ID: {message.from_user.id})")
        print(f"Размер файла: {file_size_mb:.2f} МБ")

        # Проверяем размер файла
        if message.video.file_size > 12 * 1024 * 1024:  # 12 МБ
            print("❌ Видео слишком большое, отправляем сообщение об ошибке")
            bot.reply_to(message, "Видео слишком большое. Максимальный размер - 12 МБ")
            return

        bot.send_message(message.chat.id, 'Пожалуйста, подождите')
        print("Начинаем обработку видео...")
        
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
            
            # Обрабатываем видео в отдельном потоке
            print("Запускаем обработку видео в отдельном потоке...")
            future = executor.submit(process_video, input_file.name, output_file.name)
            future.result()
            
            # Отправляем результат
            print("Отправляем обработанное видео пользователю...")
            with open(output_file.name, 'rb') as result_file:
                bot.send_video_note(message.chat.id, result_file)
            print("Видео успешно отправлено")
            
            # Удаляем временные файлы
            os.unlink(input_file.name)
            os.unlink(output_file.name)
            print("Временные файлы удалены")
            print("Обработка видео завершена успешно\n")
            
    except Exception as e:
        error_message = str(e)
        print(f"❌ Ошибка при обработке видео: {error_message}")
        bot.send_message(message.chat.id, f'Произошла ошибка при обработке видео: {error_message}')

if __name__ == '__main__':
    try:
        print("Бот запущен...")
        bot.infinity_polling()
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        bot.stop_polling()
        executor.shutdown()
