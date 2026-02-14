#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот з графіком"""

import logging
from datetime import datetime, timezone, timedelta
import json
import os
import io
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = timezone(timedelta(hours=2))

class PowerScheduleBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = "https://off.energy.mk.ua/"
        self.stats_file = "weekly_stats.json"
        
        # ========================================
        # 📌 ТУТ МІНЯТИ ГРАФІК!
        # Формат: (година, хвилина, є_світло)
        # ========================================
        self.schedule_31 = [
            (0, 0, True),      # 00:00 - світло
            (6, 30, False),    # 06:30 - відключення  
            (9, 30, True),     # 09:30 - світло до кінця доби
        ]
        
        self.init_stats()
    
    def init_stats(self):
        if not os.path.exists(self.stats_file):
            # ========================================
            # 📌 ТУТ ДОДАВАТИ Нові ДНІ!
            # ========================================
            stats = {
                "2026-02-14": {
                    'hours_with_power': 21.0,    # Години зі світлом
                    'hours_without_power': 3.0,  # Години без світла
                },
                "2026-02-15": {
                    'hours_with_power': 0.0,     # 0 = графіки відсутні
                    'hours_without_power': 0.0,  # 0 = графіки відсутні
                },
                "2026-02-16": {
                    'hours_with_power': 0.0,     # 0 = графіки відсутні
                    'hours_without_power': 0.0,  # 0 = графіки відсутні
                    
                
                }
                }     
                }
            }
            self.save_stats(stats)
    
    def load_stats(self):
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def save_stats(self, stats):
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Помилка: {e}")
    
    def get_main_keyboard(self):
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
    
    def get_hour_status(self, hour_decimal):
        current_minutes = hour_decimal * 60
        
        for i, (h, m, status) in enumerate(self.schedule_31):
            start_min = h * 60 + m
            
            if i + 1 < len(self.schedule_31):
                next_h, next_m, _ = self.schedule_31[i + 1]
                end_min = next_h * 60 + next_m
            else:
                end_min = 24 * 60
            
            if start_min <= current_minutes < end_min:
                return status
        
        return True
    
    def generate_stats_image(self):
        """Графік з можливістю показати 'графіки відсутні'"""
        stats = self.load_stats()
        now = self.get_kyiv_time()
        
        if not stats:
            return None
        
        sorted_dates = sorted(stats.keys())
        num_days = len(sorted_dates)
        
        fig_width = 16
        fig_height = 5 + num_days * 1.1
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor='white')
        ax.set_facecolor('white')
        
        # Заголовок
        if num_days > 1:
            first_date = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            last_date = datetime.strptime(sorted_dates[-1], '%Y-%m-%d')
            title = f"Графік відключень світла {first_date.strftime('%d.%m')} - {last_date.strftime('%d.%m')}"
        else:
            date_obj = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            title = f"Графік відключень світла {date_obj.strftime('%d.%m.%Y')}"
        
        ax.set_title(title, fontsize=17, color='#AAAAAA', pad=20, weight='normal')
        
        # Малюємо дні
        for idx, date_str in enumerate(sorted_dates):
            data = stats[date_str]
            hours_with = data['hours_with_power']
            hours_without = data['hours_without_power']
            
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day_short = {
                'Mon': 'ПН', 'Tue': 'ВТ', 'Wed': 'СР', 
                'Thu': 'ЧТ', 'Fri': 'ПТ', 'Sat': 'СБ', 'Sun': 'НД'
            }.get(date_obj.strftime('%a'), '')
            
            y_pos = num_days - idx - 1
            
            # Перевірка: чи є графік
            if hours_with == 0 and hours_without == 0:
                # ГРАФІКИ ВІДСУТНІ - малюємо сірим
                for seg in range(48):
                    rect = Rectangle((seg/2, y_pos - 0.38), 0.5, 0.76, 
                                    facecolor='#CCCCCC', edgecolor='white', linewidth=1.2)
                    ax.add_patch(rect)
            else:
                # Є графік - малюємо нормально
                for seg in range(48):
                    hour_decimal = seg / 2
                    has_power = self.get_hour_status(hour_decimal)
                    color = '#7BC043' if has_power else '#FF6B6B'
                    
                    rect = Rectangle((seg/2, y_pos - 0.38), 0.5, 0.76, 
                                    facecolor=color, edgecolor='white', linewidth=1.2)
                    ax.add_patch(rect)
            
            # Дата зліва
            date_label = f"{day_short} ({date_obj.strftime('%d.%m')})"
            ax.text(-1.2, y_pos, date_label, va='center', ha='right', 
                   fontsize=12, weight='bold', color='#333333')
            
            # Статистика справа
            if hours_with == 0 and hours_without == 0:
                # ГРАФІКИ ВІДСУТНІ
                ax.text(25.0, y_pos, "графіки відсутні", va='center', ha='left',
                       fontsize=11, color='#999999', style='italic')
            else:
                # Є графік
                h_with = int(hours_with)
                m_with = int((hours_with % 1) * 60)
                text_with = f"{h_with}год" if m_with == 0 else f"{h_with}год {m_with}хв"
                
                ax.text(25.0, y_pos + 0.2, text_with, va='center', ha='left',
                       fontsize=11, color='#7BC043', weight='bold')
                
                h_without = int(hours_without)
                m_without = int((hours_without % 1) * 60)
                text_without = f"{h_without}год" if m_without == 0 else f"{h_without}год {m_without}хв"
                
                ax.text(25.0, y_pos - 0.2, text_without, va='center', ha='left',
                       fontsize=11, color='#FF6B6B', weight='normal')
        
        # Осі
        ax.set_xlim(-1.8, 28)
        ax.set_ylim(-2.2, num_days + 0.1)
        
        ax.set_xticks([0, 4, 8, 12, 16, 20, 24])
        ax.set_xticklabels(['0', '4', '8', '12', '16', '20', '24'], 
                          fontsize=11, color='#BBBBBB')
        ax.set_yticks([])
        
        # Сітка
        for x in [0, 4, 8, 12, 16, 20, 24]:
            ax.axvline(x, color='#DDDDDD', linewidth=0.8, alpha=0.7, zorder=0)
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # Легенда
        legend_y = -1.2
        
        rect_green = Rectangle((1, legend_y), 0.8, 0.35, 
                               facecolor='#7BC043', edgecolor='none')
        ax.add_patch(rect_green)
        ax.text(2.0, legend_y + 0.175, 'Світло було', 
               va='center', ha='left', fontsize=11, color='#666666')
        
        rect_red = Rectangle((8, legend_y), 0.8, 0.35,
                             facecolor='#FF6B6B', edgecolor='none')
        ax.add_patch(rect_red)
        ax.text(9.0, legend_y + 0.175, 'Світла не було',
               va='center', ha='left', fontsize=11, color='#666666')
        
        # Статистика
        # Рахуємо тільки дні де є графік
        days_with_data = [d for d in stats.values() if d['hours_with_power'] > 0 or d['hours_without_power'] > 0]
        
        if len(days_with_data) > 1:
            total_with = sum(d['hours_with_power'] for d in days_with_data)
            total_without = sum(d['hours_without_power'] for d in days_with_data)
            avg_with = total_with / len(days_with_data)
            
            tw_h, tw_m = int(total_with), int((total_with % 1) * 60)
            two_h, two_m = int(total_without), int((total_without % 1) * 60)
            aw_h, aw_m = int(avg_with), int((avg_with % 1) * 60)
            
            stats_y = legend_y - 0.65
            
            line1 = f"● Всього світло було: {tw_h}год"
            if tw_m > 0:
                line1 += f" {tw_m}хв"
            
            line2 = f"● Всього світла не було: {two_h}год"
            if two_m > 0:
                line2 += f" {two_m}хв"
            
            line3 = f"● В середньому світло було {aw_h}год"
            if aw_m > 0:
                line3 += f" {aw_m}хв"
            line3 += " за добу"
            
            ax.text(1, stats_y, line1, fontsize=10, color='#666666', va='top')
            ax.text(1, stats_y - 0.25, line2, fontsize=10, color='#666666', va='top')
            ax.text(1, stats_y - 0.50, line3, fontsize=10, color='#666666', va='top')
        
        plt.tight_layout(pad=1.5)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', 
                   facecolor='white', pad_inches=0.4)
        buf.seek(0)
        plt.close('all')
        
        return buf
    
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
            await update.message.reply_text("🎨 Генерую статистику...", reply_markup=self.get_main_keyboard())
            
            image_buf = self.generate_stats_image()
            
            if image_buf:
                await update.message.reply_photo(
                    photo=image_buf,
                    caption="📊 Графік відключень світла\nГрупа 3.1",
                    reply_markup=self.get_main_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Статистики поки немає",
                    reply_markup=self.get_main_keyboard()
                )
        
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
        await update.message.reply_text("🎨 Генерую статистику...")
        
        image_buf = self.generate_stats_image()
        
        if image_buf:
            await update.message.reply_photo(
                photo=image_buf,
                caption="📊 Графік відключень світла\nГрупа 3.1",
                reply_markup=self.get_main_keyboard()
            )
        else:
            await update.message.reply_text("❌ Статистики поки немає")
    
    def run(self):
        now = self.get_kyiv_time()
        logger.info(f"Запуск бота. Київський час: {now.strftime('%H:%M')}")
        
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("schedule", self.schedule_command))
        application.add_handler(CommandHandler("now", self.now_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
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
