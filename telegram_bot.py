#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот для графіку відключень світла"""

import logging
from datetime import datetime
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
from bs4 import BeautifulSoup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class PowerScheduleBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = "https://off.energy.mk.ua/"
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
    
    async def fetch_schedule(self, group=None):
        if group is None:
            group = self.default_group
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(self.base_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            schedule_data = {
                'timestamp': datetime.now().isoformat(),
                'group': group,
                'schedule': []
            }
            
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                headers_row = rows[0] if rows else None
                headers = []
                if headers_row:
                    headers = [th.get_text(strip=True) for th in headers_row.find_all('th')]
                
                group_index = -1
                for i, header in enumerate(headers):
                    if group in header:
                        group_index = i
                        break
                
                for row in rows[1:]:
                    cells = row.find_all('td')
                    if len(cells) > 0:
                        time_slot = cells[0].get_text(strip=True)
                        status = ""
                        has_power = False
                        
                        if group_index >= 0 and len(cells) > group_index:
                            status = cells[group_index].get_text(strip=True)
                            has_power = 'світло' in status.lower() or 'можливе' in status.lower()
                        
                        schedule_data['schedule'].append({
                            'time': time_slot,
                            'status': status,
                            'has_power': has_power
                        })
            
            return schedule_data
            
        except Exception as e:
            logger.error(f"Помилка: {e}")
            return None
    
    def format_schedule_message(self, data):
        if not data:
            return "❌ Не вдалося отримати графік. Спробуйте пізніше."
        
        group = data.get('group', '3.1')
        schedule = data.get('schedule', [])
        
        msg = f"⚡️ <b>Графік відключень - Група {group}</b>\n"
        msg += f"🕐 Оновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        msg += "─" * 30 + "\n\n"
        
        if not schedule:
            msg += "⚠️ Графік недоступний\n"
            return msg
        
        now = datetime.now()
        current_hour = now.hour
        
        msg += "<b>📅 Графік на сьогодні:</b>\n\n"
        
        for item in schedule[:12]:
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
            msg += f"✅ Зі світлом: {with_power}/{total} ({(with_power/total)*100:.0f}%)\n"
            msg += f"❌ Без світла: {total-with_power}/{total}\n"
        
        return msg
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        group = self.get_user_group(user_id)
        
        welcome_text = (
            "👋 Вітаю!\n\n"
            "Я бот для відстеження графіку відключень.\n\n"
            f"📍 Ваша група: <b>{group}</b>\n\n"
            "<b>Команди:</b>\n"
            "/schedule - Показати графік\n"
            "/now - Чи є зараз світло?\n"
            "/group - Змінити групу\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("📅 Показати графік", callback_data='show_schedule')],
            [InlineKeyboardButton("⚙️ Змінити групу", callback_data='change_group')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        group = self.get_user_group(user_id)
        
        await update.message.reply_text("🔄 Завантажую...")
        
        data = await self.fetch_schedule(group)
        message = self.format_schedule_message(data)
        
        keyboard = [[InlineKeyboardButton("🔄 Оновити", callback_data='show_schedule')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        group = self.get_user_group(user_id)
        
        await update.message.reply_text("⏳ Перевіряю...")
        
        data = await self.fetch_schedule(group)
        
        if not data or not data.get('schedule'):
            await update.message.reply_text("❌ Помилка")
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
            msg += f"📍 Група: {group}"
            
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("⚠️ Не вдалося визначити")
    
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
        
        await update.message.reply_text("Оберіть групу:", reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if query.data == 'show_schedule':
            group = self.get_user_group(user_id)
            data = await self.fetch_schedule(group)
            message = self.format_schedule_message(data)
            
            keyboard = [[InlineKeyboardButton("🔄 Оновити", callback_data='show_schedule')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
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
            
            await query.edit_message_text("Оберіть групу:", reply_markup=reply_markup)
        
        elif query.data.startswith('set_group_'):
            group = query.data.replace('set_group_', '')
            self.set_user_group(user_id, group)
            
            await query.edit_message_text(
                f"✅ Групу змінено на <b>{group}</b>\n\nВикористовуйте /schedule",
                parse_mode='HTML'
            )
    
    def run(self):
        logger.info("Запуск бота...")
        
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("schedule", self.schedule_command))
        application.add_handler(CommandHandler("now", self.now_command))
        application.add_handler(CommandHandler("group", self.group_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Бот запущено!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("=" * 60)
        print("❌ Не знайдено токен бота!")
        print("Встановіть: export TELEGRAM_BOT_TOKEN='ваш_токен'")
        print("=" * 60)
        return
    
    bot = PowerScheduleBot(bot_token)
    bot.run()


if __name__ == "__main__":
    main()
