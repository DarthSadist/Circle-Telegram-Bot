import telebot
import os
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import logging

class CircleBot:
    def __init__(self, token):
        self.token = token
        self.bot = telebot.TeleBot(self.token)
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.user_messages = defaultdict(list)
        self.logger = self.setup_logger()

    def setup_logger(self):
        # Настройка логирования
        logger = logging.getLogger('circle_bot')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def start(self):
        self.logger.info("Бот успешно инициализирован")
        self.bot.polling()  # Запуск бота

    # Добавьте сюда методы для обработки сообщений и видео
    
