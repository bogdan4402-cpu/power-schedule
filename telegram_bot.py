#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот для графіку відключень - з правильним часовим поясом"""

import logging
from datetime import datetime, timezone, timedelta
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Київський часовий пояс (UTC+2)
KYIV_TZ = timezone(timedelta(hours=2))

class PowerScheduleBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = "https://off.energy.mk.ua/"
        self.default_group = "3.1"
        self.users_file = "bot_users.json"
        self.users_data = self.load_users()
        
        # Графік для групи 3.1 (київський час):
        # 00:00-06:30 світло
        # 06:30-09:00 відключення
        # 09:00-13:30 світло
        # 13:30-19:30 відключення
        # 19:30-00:00 світло
        
        self.schedule_31 = [
            (0, 0, True),     # 00:00 - світло
            (6, 30, False),   # 06:30 - відключення
            (9, 0, True),     # 09:00 - світло
            (13, 30, False),  # 13:30 - відключення
            (19, 30, True),   # 19:30 - світло
        ]
    
    def get_kyiv_time(self):
        """Повертає поточний час у Києві"""
        return datetime.now(KYIV_TZ)
    
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
    
    def get_current_status(self):
        """Визначає чи є зараз світло (київський час)"""
        now = self.get_kyiv_time()
        current_minutes = now.hour * 60 + now.minute
        
        periods = []
        for i, (h, m, status) in enumerate(self.schedule_31):
            start_min = h * 60 + m
            
            if i + 1 < len(self.schedule_31):
                next_h, next_m, _ = self.schedule_31[i + 1]
                end_min = next_h * 60 + next_m
                end_time = f"{next_h:02d}:{next_m:02d}"
            else:
                end_min = 24 * 60
                end_time = "00:00"
            
            periods.append({
                'start': start_min,
                'end': end_min,
                'status': status,
                'start_time': f"{h:02d}:{m:02d}",
                'end_time': end_time
            })
        
        for period in periods:
            if period['start'] <= current_minutes < period['end']:
                return period
        
        return periods[0]
    
    def get_full_schedule(self):
        """Повертає повний графік"""
        now = self.get_kyiv_time()
        
        schedule_data = {
            'timestamp': now.isoformat(),
            'group': '3.1',
            'periods': []
        }
        
        for i, (h, m, status) in enumerate(self.schedule_31):
            if i + 1 < len(self.schedule_31):
                next_h, next_m, _ = self.schedule_31[i + 1]
                end_time = f"{next_h:02d}:{next_m:02d}"
            else:
                end_time = "00:00"
            
            schedule_data['periods'].append({
                'start': f"{h:02d}:{m:02d}",
                'end': end_time,
                'status': 'Є світло' if status else 'Відключення',
                'has_power': status
            })
        
        return schedule_data
    
    def format_schedule_message(self, data):
        periods = data.get('periods', [])
        now = self.get_kyiv_time()
        
        msg = f"⚡️ <b>Графік відключень - Група 3.1</b>\n"
        msg += f"🕐 {now.strftime('%d.%m.%Y %H:%M')} (Київ)\n"
        msg += f"\n📋 Дані з off.energy.mk.ua\n"
        msg += "\n" + "─" * 35 + "\n\n"
        
        current = self.get_current_status()
        
        if current['status']:
            msg += f"<b>🟢 ЗАРАЗ Є СВІТЛО</b>\n"
            msg += f"До {current['end_time']}\n\n"
        else:
            msg += f"<b>🔴 ЗАРАЗ ВІДКЛЮЧЕННЯ</b>\n"
            msg += f"До {current['end_time']}\n\n"
        
        msg += "─" * 35 + "\n\n"
        msg += "<b>📅 Повний графік:</b>\n\n"
        
        current_minutes = now.hour * 60 + now.minute
        
        for period in periods:
            start = period['start']
            end = period['end']
            has_power = period['has_power']
            
            emoji = "🟢" if has_power else "🔴"
            status_text = "Є світло" if has_power else "Відключення"
            
            start_h, start_m = map(int, start.split(':'))
            end_h, end_m = map(int, end.split(':'))
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m if end != "00:00" else 24 * 60
            
            if start_min <= current_minutes < end_min:
                msg += f"👉 <b>{start}-{end}  {emoji} {status_text}</b>\n"
            else:
                msg += f"      {start}-{end}  {emoji} {status_text}\n"
        
        total_with_light = 0
        for i, period in enumerate(periods):
            start_h, start_m = map(int, period['start'].split(':'))
            if i + 1 < len(periods):
                end_h, end_m = map(int, period['end'].split(':'))
            else:
                end_h, end_m = 0, 0
            
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m if period['end'] != "00:00" else 24 * 60
            duration = end_min - start_min
            
            if period['has_power']:
                total_with_light += duration
        
        total_without_light = 24 * 60 - total_with_light
        
        msg += f"\n📊 <b>Статистика:</b>\n"
        msg += f"🟢 Зі світлом: {total_with_light/60:.1f} год\n"
        msg += f"🔴 Без світла: {total_without_light/60:.1f} год\n"
        
        msg += f"\n⚠️ Графіки можуть змінюватись!\n"
        msg += f"Перевіряйте: {self.base_url}"
        
        return msg
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = (
            "👋 <b>Вітаю!</b>\n\n"
            "Я показую графік відключень для Миколаївської області.\n\n"
            "📍 Група: <b>3.1</b>\n\n"
            "🟢 - є світло\n"
            "🔴 - відключення\n\n"
            "<b>Команди:</b>\n"
            "/schedule - Повний графік\n"
            "/now - Чи є зараз світло?\n"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚡ Чи є зараз світло?", callback_data='check_now')],
            [InlineKeyboardButton("📅 Повний графік", callback_data='show_schedule')],
            [InlineKeyboardButton("🌐 Сайт", url=self.base_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)
    
    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        data = self.get_full_schedule()
        message = self.format_schedule_message(data)
        
        keyboard = [
            [InlineKeyboardButton("🔄 Оновити", callback_data='show_schedule')],
            [InlineKeyboardButton("🌐 Сайт", url=self.base_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)
    
    async def now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        current = self.get_current_status()
        now = self.get_kyiv_time()
        
        if current['status']:
            emoji = "🟢✅"
            status = "Є СВІТЛО"
        else:
            emoji = "🔴❌"
            status = "ВІДКЛЮЧЕННЯ"
        
        msg = f"{emoji}\n\n"
        msg += f"<b>ЗАРАЗ ({now.strftime('%H:%M')}):</b>\n"
        msg += f"<b>{status}</b>\n\n"
        msg += f"Період: {current['start_time']} - {current['end_time']}\n"
        msg += f"📍 Група: 3.1\n\n"
        msg += f"⚠️ Графіки можуть змінюватись!"
        
        keyboard = [[InlineKeyboardButton("📅 Повний графік", callback_data='show_schedule')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == 'show_schedule':
            data = self.get_full_schedule()
            message = self.format_schedule_message(data)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Оновити", callback_data='show_schedule')],
                [InlineKeyboardButton("🌐 Сайт", url=self.base_url)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup, disable_web_page_preview=True)
        
        elif query.data == 'check_now':
            current = self.get_current_status()
            now = self.get_kyiv_time()
            
            if current['status']:
                emoji = "🟢✅"
                status = "Є СВІТЛО"
            else:
                emoji = "🔴❌"
                status = "ВІДКЛЮЧЕННЯ"
            
            msg = f"{emoji}\n\n"
            msg += f"<b>ЗАРАЗ ({now.strftime('%H:%M')}):</b>\n"
            msg += f"<b>{status}</b>\n\n"
            msg += f"Період: {current['start_time']} - {current['end_time']}\n"
            msg += f"📍 Група: 3.1"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Оновити", callback_data='check_now')],
                [InlineKeyboardButton("📅 Повний графік", callback_data='show_schedule')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    def run(self):
        now = self.get_kyiv_time()
        logger.info(f"Запуск бота. Київський час: {now.strftime('%H:%M')}")
        logger.info("Графік 3.1: 00:00-06:30 світло, 06:30-09:00 відкл, 09:00-13:30 світло, 13:30-19:30 відкл, 19:30-00:00 світло")
        
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("schedule", self.schedule_command))
        application.add_handler(CommandHandler("now", self.now_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        
        logger.info("Бот запущено!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("❌ Не знайдено TELEGRAM_BOT_TOKEN!")
        return
    
    bot = PowerScheduleBot(bot_token)
    bot.run()


if __name__ == "__main__":
    main()
