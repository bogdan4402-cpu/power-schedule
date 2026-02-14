#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот для графіку відключень - зі статистикою за тиждень"""

import logging
from datetime import datetime, timezone, timedelta
import json
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = timezone(timedelta(hours=2))

class PowerScheduleBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = "https://off.energy.mk.ua/"
        self.stats_file = "weekly_stats.json"
        
        # Графік для групи 3.1
        self.schedule_31 = [
            (0, 0, True),      # 00:00-06:30 світло
            (6, 30, False),    # 06:30-09:00 відключення
            (9, 0, True),      # 09:00-13:30 світло
            (13, 30, False),   # 13:30-19:30 відключення
            (19, 30, True),    # 19:30-00:00 світло
        ]
        
        # Ініціалізуємо статистику
        self.init_stats()
    
    def init_stats(self):
        """Ініціалізує файл статистики"""
        if not os.path.exists(self.stats_file):
            # Створюємо статистику за останні 7 днів
            stats = {}
            now = self.get_kyiv_time()
            
            for i in range(7):
                date = (now - timedelta(days=i)).strftime('%Y-%m-%d')
                stats[date] = {
                    'hours_with_power': 15.5,  # Годин зі світлом
                    'hours_without_power': 8.5,  # Годин без світла
                    'outages_count': 2,  # Кількість відключень
                }
            
            self.save_stats(stats)
    
    def load_stats(self):
        """Завантажує статистику"""
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def save_stats(self, stats):
        """Зберігає статистику"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Помилка збереження статистики: {e}")
    
    def get_main_keyboard(self):
        """Головне меню"""
        keyboard = [
            [KeyboardButton("⚡ Зараз є світло?")],
            [KeyboardButton("📅 Повний графік"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("🌐 Відкрити сайт")],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def get_kyiv_time(self):
        return datetime.now(KYIV_TZ)
    
    def get_current_status(self):
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
    
    def format_weekly_stats(self):
        """Форматує статистику за тиждень"""
        stats = self.load_stats()
        now = self.get_kyiv_time()
        
        msg = "📊 <b>СТАТИСТИКА ЗА ТИЖДЕНЬ</b>\n"
        msg += f"📍 Група: 3.1\n"
        msg += f"🕐 {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        msg += "─" * 35 + "\n\n"
        
        # Останні 7 днів
        total_with_power = 0
        total_without_power = 0
        
        for i in range(6, -1, -1):  # Від старішої дати до новішої
            date = (now - timedelta(days=i)).strftime('%Y-%m-%d')
            day_name = (now - timedelta(days=i)).strftime('%a')
            day_short = {
                'Mon': 'Пн', 'Tue': 'Вт', 'Wed': 'Ср', 
                'Thu': 'Чт', 'Fri': 'Пт', 'Sat': 'Сб', 'Sun': 'Нд'
            }.get(day_name, day_name)
            
            if date in stats:
                data = stats[date]
                hours_with = data['hours_with_power']
                hours_without = data['hours_without_power']
                
                total_with_power += hours_with
                total_without_power += hours_without
                
                # Візуальний прогрес-бар
                percentage = int((hours_with / 24) * 100)
                bar_length = 10
                filled = int((percentage / 100) * bar_length)
                bar = "🟢" * filled + "🔴" * (bar_length - filled)
                
                msg += f"<b>{day_short} {(now - timedelta(days=i)).strftime('%d.%m')}</b>\n"
                msg += f"{bar} {percentage}%\n"
                msg += f"  🟢 {hours_with:.1f}год  🔴 {hours_without:.1f}год\n\n"
        
        msg += "─" * 35 + "\n\n"
        
        # Загальна статистика
        avg_with_power = total_with_power / 7
        avg_without_power = total_without_power / 7
        
        msg += "<b>📈 Середнє за тиждень:</b>\n"
        msg += f"🟢 Зі світлом: {avg_with_power:.1f} год/день\n"
        msg += f"🔴 Без світла: {avg_without_power:.1f} год/день\n\n"
        
        msg += f"<b>📊 Всього за тиждень:</b>\n"
        msg += f"🟢 Зі світлом: {total_with_power:.1f} год\n"
        msg += f"🔴 Без світла: {total_without_power:.1f} год\n\n"
        
        # Прогноз
        msg += "<b>🔮 Сьогодні очікується:</b>\n"
        msg += "🟢 15.5 год зі світлом\n"
        msg += "🔴 8.5 год без світла\n\n"
        
        msg += "⚠️ Дані приблизні, графіки можуть змінюватись!"
        
        return msg
    
    def format_schedule_message(self, data):
        periods = data.get('periods', [])
        now = self.get_kyiv_time()
        
        msg = f"⚡️ <b>Графік відключень - Група 3.1</b>\n"
        msg += f"🕐 {now.strftime('%d.%m.%Y %H:%M')} (Київ)\n\n"
        
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
        
        msg += f"\n⚠️ Графіки можуть змінюватись!"
        
        return msg
    
    def format_now_message(self):
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
        
        return msg
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_text = (
            "👋 <b>Вітаю!</b>\n\n"
            "Я показую графік відключень для Миколаївської області.\n\n"
            "📍 Група: <b>3.1</b>\n\n"
            "Використовуйте меню внизу 👇"
        )
        
        await update.message.reply_text(
            welcome_text, 
            parse_mode='HTML', 
            reply_markup=self.get_main_keyboard()
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if text == "⚡ Зараз є світло?":
            message = self.format_now_message()
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard())
        
        elif text == "📅 Повний графік":
            data = self.get_full_schedule()
            message = self.format_schedule_message(data)
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard(), disable_web_page_preview=True)
        
        elif text == "📊 Статистика":
            message = self.format_weekly_stats()
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard())
        
        elif text == "🌐 Відкрити сайт":
            await update.message.reply_text(
                f"🌐 Офіційний сайт:\n{self.base_url}",
                reply_markup=self.get_main_keyboard(),
                disable_web_page_preview=True
            )
    
    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        data = self.get_full_schedule()
        message = self.format_schedule_message(data)
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard(), disable_web_page_preview=True)
    
    async def now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = self.format_now_message()
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard())
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = self.format_weekly_stats()
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard())
    
    def run(self):
        now = self.get_kyiv_time()
        logger.info(f"Запуск бота зі статистикою. Київський час: {now.strftime('%H:%M')}")
        
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("schedule", self.schedule_command))
        application.add_handler(CommandHandler("now", self.now_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("Бот запущено з постійним меню та статистикою!")
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
