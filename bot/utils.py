# Здесь будут утилиты и вспомогательные функции

def safe_send_message(bot, chat_id, text, reply_markup=None):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        # Логирование ошибки
        print(f"Ошибка при отправке сообщения: {str(e)}")
        return None

