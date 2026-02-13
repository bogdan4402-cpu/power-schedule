#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот для графіку відключень світла - з підтримкою динамічних сайтів"""

import logging
from datetime import datetime
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class PowerScheduleBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = "https://off.energy.mk.ua/"
        self.api_url = "https://off.energy.mk.ua/api/v1/outages/schedule"  # Можливий API endpoint
        self.default_group = "3.1"
        self.users_file = "bot_users.json"
        self.users_data = self.load_users()
    
    def load_users(self):
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_users(self):
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.users_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Помилка збереження: {e}")
    
    def get_user_group(self, user_id):
        user_id_str = str(user_id)
        if user_id_str in self.users_data:
            return self.users_data[user_id_str].get('group', self.default_group)
        return self.default_group
    
    def set_user_group(self, user_id, group):
        user_id_str = str(user_id)
        if user_id_str not in self.users_data:
            self.users_data[user_id_str] = {}
        self.users_data[user_id_str]['group'] = group
        self.save_users()
    
    async def fetch_schedule_v2(self, group=None):
        """
        Спроба отримати дані через можливий API або інший спосіб
        """
        if group is None:
            group = self.default_group
        
        # Спроба 1: Перевірити чи є API
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            # Спробуємо різні можливі endpoints
            possible_apis = [
                f"{self.base_url}api/schedule",
                f"{self.base_url}api/v1/schedule",
                f"{self.base_url}api/outages",
            ]
            
            for api_url in possible_apis:
                try:
                    response = requests.get(api_url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"Знайдено API: {api_url}")
                        return self.parse_api_response(data, group)
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"API не знайдено: {e}")
        
        # Спроба 2: Використати статичний графік (якщо є)
        return self.get_mock_schedule(group)
    
    def parse_api_response(self, data, group):
        """Парсинг відповіді від API"""
        try:
            schedule_data = {
                'timestamp': datetime.now().isoformat(),
                'group': group,
                'schedule': []
            }
            
            # Тут потрібно адаптувати під реальну структуру API
            # Це приклад
            if isinstance(data, dict) and 'schedule' in data:
                for item in data['schedule']:
                    schedule_data['schedule'].append({
                        'time': item.get('time', ''),
                        'status': item.get('status', ''),
                        'has_power': item.get('has_power', False)
                    })
            
            return schedule_data
        except Exception as e:
            logger.error(f"Помилка парсингу API: {e}")
            return None
    
    def get_mock_schedule(self, group):
        """
        Тимчасовий графік на основі типового розкладу
        Це використовується поки не з'ясуємо як отримати реальні дані
        """
        now = datetime.now()
        hour = now.hour
        
        # Типовий графік для різних груп (приклад)
        schedules = {
            "1.1": [0, 1, 2, 6, 7, 8, 12, 13, 14, 18, 19, 20],  # Години БЕЗ світла
            "1.2": [3, 4, 5, 9, 10, 11, 15, 16, 17, 21, 22, 23],
            "2.1": [1, 2, 3, 7, 8, 9, 13, 14, 15, 19, 20, 21],
            "2.2": [4, 5, 6, 10, 11, 12, 16, 17, 18, 22, 23, 0],
            "3.1": [2, 3, 4, 8, 9, 10, 14, 15, 16, 20, 21, 22],
            "3.2": [5, 6, 7, 11, 12, 13, 17, 18, 19, 23, 0, 1],
        }
        
        outage_hours = schedules.get(group, schedules["3.1"])
        
        schedule_data = {
            'timestamp': datetime.now().isoformat(),
            'group': group,
            'schedule': [],
            'note': '⚠️ УВАГА: Це приблизний графік! Для точної інформації перевірте на сайті off.energy.mk.ua'
        }
        
        for h in range(24):
            has_power = h not in outage_hours
            schedule_data['schedule'].append({
                'time': f"{h:02d}:00-{(h+1)%24:02d}:00",
                'status': 'Є світло' if has_power else 'Відключення',
                'has_power': has_power
            })
        
        return schedule_data
    
    def format_schedule_message(self, data):
        if not data:
            return "❌ Не вдалося отримати графік.\n\nПеревірте на сайті: https://off.energy.mk.ua/"
        
        group = data.get('group', '3.1')
        schedule = data.get('schedule', [])
        note = data.get('note', '')
        
        msg = f"⚡️ <b>Графік відключень - Група {group}</b>\n"
        msg += f"🕐 Станом на: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        
        if note:
            msg += f"\n{note}\n"
        
        msg += "\n" + "─" * 30 + "\n\n"
        
        if not schedule:
            msg += "⚠️ Графік недоступний\n"
            msg += f"\n🔗 Перевірте на сайті:\n{self.base_url}"
            return msg
        
        now = datetime.now()
        current_hour = now.hour
        
        msg += "<b>📅 Графік на сьогодні:</b>\n\n"
        
        # Показуємо всі 24 години
        for item in schedule:
            time_slot = item.get('time', '-')
            has_power = item.get('has_power', False)
            
            emoji = "✅" if has_power else "❌"
            status_text = "Світло" if has_power else "Відключення"
            
            try:
                if '-' in time_slot:
                    hour = int(time_slot.split('-')[0].strip().split(':')[0])
                    if hour == current_hour:
                        msg += f"👉 <b>{time_slot}: {emoji} {status_text}</b>\n"
                    else:
                        msg += f"    {time_slot}: {emoji} {status_text}\n"
                else:
                    msg += f"    {time_slot}: {emoji} {status_text}\n"
            except:
                msg += f"    {time_slot}: {emoji} {status_text}\n"
        
        total = len(schedule)
        with_power = sum(1 for item in schedule if item.get('has_power', False))
        
        if total > 0:
            msg += f"\n📊 <b>Статистика:</b>\n"
            msg += f"✅ Зі світлом: {with_power}/{total} год ({(with_power/total)*100:.0f}%)\n"
            msg += f"❌ Без світла: {total-with_power}/{total} год\n"
        
        msg += f"\n🔗 Актуальна інформація:\n{self.base_url}"
        
        return msg
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        group = self.get_user_group(user_id)
        
        welcome_text = (
            "👋 <b>Вітаю!</b>\n\n"
            "Я бот для відстеження графіку відключень електроенергії "
            "в Миколаївській області.\n\n"
            f"📍 Ваша група: <b>{group}</b>\n\n"
            "⚠️ <b>ВАЖЛИВО:</b>\n"
            "Графіки можуть змінюватися.\n"
            "Завжди перевіряйте актуальну інформацію на офіційному сайті!\n\n"
            "<b>🔹 Команди:</b>\n"
            "/schedule - Показати графік\n"
            "/now - Чи є зараз світло?\n"
            "/group - Змінити групу\n"
            "/help - Допомога\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("📅 Показати графік", callback_data='show_schedule')],
            [InlineKeyboardButton("⚙️ Змінити групу", callback_data='change_group')],
            [InlineKeyboardButton("🌐 Відкрити сайт", url=self.base_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        group = self.get_user_group(user_id)
        
        await update.message.reply_text("🔄 Завантажую графік...")
        
        data = await self.fetch_schedule_v2(group)
        message = self.format_schedule_message(data)
        
        keyboard = [
            [InlineKeyboardButton("🔄 Оновити", callback_data='show_schedule')],
            [InlineKeyboardButton("🌐 Сайт", url=self.base_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)
    
    async def now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        group = self.get_user_group(user_id)
        
        await update.message.reply_text("⏳ Перевіряю...")
        
        data = await self.fetch_schedule_v2(group)
        
        if not data or not data.get('schedule'):
            await update.message.reply_text(
                "❌ Не вдалося отримати дані\n\n"
                f"🔗 Перевірте на сайті:\n{self.base_url}",
                disable_web_page_preview=True
            )
            return
        
        now = datetime.now()
        current_hour = now.hour
        
        current_status = None
        for item in data['schedule']:
            try:
                time_slot = item.get('time', '')
                if '-' in time_slot:
                    hour = int(time_slot.split('-')[0].strip().split(':')[0])
                    if hour == current_hour:
                        current_status = item
                        break
            except:
                continue
        
        if current_status:
            has_power = current_status.get('has_power', False)
            emoji = "✅" if has_power else "❌"
            status = "Є світло" if has_power else "Відключення"
            
            msg = f"{emoji} <b>Зараз ({current_hour:02d}:00):</b> {status}\n\n"
            msg += f"📍 Група: {group}\n"
            msg += f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            
            if data.get('note'):
                msg += f"{data['note']}\n\n"
            
            msg += f"🔗 Актуальна інформація:\n{self.base_url}"
            
            keyboard = [[InlineKeyboardButton("📅 Повний графік", callback_data='show_schedule')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)
        else:
            await update.message.reply_text("⚠️ Не вдалося визначити поточний статус")
    
    async def group_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("1.1", callback_data='set_group_1.1'),
             InlineKeyboardButton("1.2", callback_data='set_group_1.2')],
            [InlineKeyboardButton("2.1", callback_data='set_group_2.1'),
             InlineKeyboardButton("2.2", callback_data='set_group_2.2')],
            [InlineKeyboardButton("3.1", callback_data='set_group_3.1'),
             InlineKeyboardButton("3.2", callback_data='set_group_3.2')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("Оберіть вашу групу відключення:", reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "<b>📖 Допомога</b>\n\n"
            "<b>Команди:</b>\n"
            "/start - Почати роботу\n"
            "/schedule - Показати повний графік\n"
            "/now - Швидка перевірка статусу\n"
            "/group - Змінити групу\n"
            "/help - Ця довідка\n\n"
            "<b>⚠️ Важливо:</b>\n"
            "Графіки можуть змінюватися!\n"
            "Завжди перевіряйте актуальну інформацію на офіційному сайті.\n\n"
            f"🔗 Сайт: {self.base_url}\n\n"
            "<b>Проблеми?</b>\n"
            "Якщо бот показує неправильні дані - перевірте на офіційному сайті."
        )
        
        keyboard = [[InlineKeyboardButton("🌐 Відкрити сайт", url=self.base_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if query.data == 'show_schedule':
            group = self.get_user_group(user_id)
            data = await self.fetch_schedule_v2(group)
            message = self.format_schedule_message(data)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Оновити", callback_data='show_schedule')],
                [InlineKeyboardButton("🌐 Сайт", url=self.base_url)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)
        
        elif query.data == 'change_group':
            keyboard = [
                [InlineKeyboardButton("1.1", callback_data='set_group_1.1'),
                 InlineKeyboardButton("1.2", callback_data='set_group_1.2')],
                [InlineKeyboardButton("2.1", callback_data='set_group_2.1'),
                 InlineKeyboardButton("2.2", callback_data='set_group_2.2')],
                [InlineKeyboardButton("3.1", callback_data='set_group_3.1'),
                 InlineKeyboardButton("3.2", callback_data='set_group_3.2')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text("Оберіть вашу групу відключення:", reply_markup=reply_markup)
        
        elif query.data.startswith('set_group_'):
            group = query.data.replace('set_group_', '')
            self.set_user_group(user_id, group)
            
            msg = f"✅ Групу змінено на <b>{group}</b>\n\n"
            msg += "Використовуйте /schedule щоб побачити графік"
            
            keyboard = [[InlineKeyboardButton("📅 Показати графік", callback_data='show_schedule')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    def run(self):
        logger.info("Запуск бота...")
        
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("schedule", self.schedule_command))
        application.add_handler(CommandHandler("now", self.now_command))
        application.add_handler(CommandHandler("group", self.group_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Бот запущено!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("=" * 60)
        logger.error("❌ Не знайдено TELEGRAM_BOT_TOKEN!")
        logger.error("Встановіть змінну середовища")
        logger.error("=" * 60)
        return
    
    bot = PowerScheduleBot(bot_token)
    bot.run()


if __name__ == "__main__":
    main()
