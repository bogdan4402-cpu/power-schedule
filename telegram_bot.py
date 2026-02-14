#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот з красивим графіком у стилі СвітлоБот"""

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
        
        # ВИПРАВЛЕНИЙ графік для групи 3.1
        # 00:00-06:30 світло
        # 06:30-09:30 відключення
        # 09:30-00:00 світло
        self.schedule_31 = [
            (0, 0, True),      # 00:00 - світло
            (6, 30, False),    # 06:30 - відключення
            (9, 30, True),     # 09:30 - світло до кінця доби
        ]
        
        self.init_stats()
    
    def init_stats(self):
        if not os.path.exists(self.stats_file):
            stats = {
                "2026-02-14": {
                    'hours_with_power': 21.0,  # 6.5 + 14.5 = 21 година
                    'hours_without_power': 3.0,  # 3 години
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
            logger.error(f"Помилка збереження статистики: {e}")
    
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
        """Визначає чи є світло в конкретну годину"""
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
        """Генерує графік у стилі СвітлоБот З ЛЕГЕНДОЮ"""
        stats = self.load_stats()
        now = self.get_kyiv_time()
        
        if not stats:
            return None
        
        sorted_dates = sorted(stats.keys())
        num_days = len(sorted_dates)
        
        # Створюємо фігуру (більше місця для легенди)
        fig_height = 4 + num_days * 1.2
        fig = plt.figure(figsize=(16, fig_height), facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('white')
        
        # Заголовок
        if num_days > 1:
            first_date = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            last_date = datetime.strptime(sorted_dates[-1], '%Y-%m-%d')
            title = f"Графік відключень світла {first_date.strftime('%d.%m')} - {last_date.strftime('%d.%m')}"
        else:
            date_obj = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            title = f"Графік відключень світла {date_obj.strftime('%d.%m.%Y')}"
        
        ax.text(12, num_days + 0.7, title, ha='center', fontsize=18, 
               color='#999', fontweight='normal')
        
        # Малюємо кожен день
        for idx, date_str in enumerate(sorted_dates):
            data = stats[date_str]
            hours_with = data['hours_with_power']
            hours_without = data['hours_without_power']
            
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            day_name = date_obj.strftime('%a')
            day_short = {
                'Mon': 'ПН', 'Tue': 'ВТ', 'Wed': 'СР', 
                'Thu': 'ЧТ', 'Fri': 'ПТ', 'Sat': 'СБ', 'Sun': 'НД'
            }.get(day_name, day_name)
            
            y_pos = num_days - idx - 1
            
            # Малюємо 24-годинну шкалу (48 півгодинних сегментів)
            for segment in range(48):
                hour_start = segment / 2
                
                # Визначаємо колір
                has_power = self.get_hour_status(hour_start)
                
                if has_power:
                    color = '#7BC043'  # Зелений
                else:
                    color = '#FF6B6B'  # Червоний
                
                rect = Rectangle((hour_start, y_pos - 0.4), 0.5, 0.8, 
                                facecolor=color, edgecolor='white', linewidth=0.5)
                ax.add_patch(rect)
            
            # Лейбл дати зліва
            date_label = f"{day_short} ({date_obj.strftime('%d.%m')})"
            ax.text(-0.8, y_pos, date_label, va='center', ha='right', 
                   fontsize=12, fontweight='bold', color='#333')
            
            # Статистика справа
            hours_int = int(hours_with)
            mins_int = int((hours_with % 1) * 60)
            hours_text = f"{hours_int}год {mins_int}хв"
            
            ax.text(24.5, y_pos + 0.15, hours_text, va='center', ha='left',
                   fontsize=11, color='#7BC043', fontweight='bold')
            
            hours_without_int = int(hours_without)
            mins_without_int = int((hours_without % 1) * 60)
            hours_without_text = f"{hours_without_int}год {mins_without_int}хв"
            
            ax.text(24.5, y_pos - 0.15, hours_without_text, va='center', ha='left',
                   fontsize=11, color='#FF6B6B', fontweight='normal')
        
        # Налаштування осей
        ax.set_xlim(-1.5, 28)
        ax.set_ylim(-2.0, num_days + 0.3)
        
        # Мітки по горизонталі
        ax.set_xticks([0, 4, 8, 12, 16, 20, 24])
        ax.set_xticklabels(['0', '4', '8', '12', '16', '20', '24'], 
                          fontsize=11, color='#999')
        ax.set_yticks([])
        
        # Сітка
        for x in [0, 4, 8, 12, 16, 20, 24]:
            ax.axvline(x, color='#E0E0E0', linewidth=0.5, linestyle='-', alpha=0.5)
        
        # Прибираємо рамки
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#E0E0E0')
        ax.spines['bottom'].set_linewidth(0.5)
        
        # ЛЕГЕНДА (нижче графіка)
        legend_y = -0.9
        
        # Зелений квадратик
        rect1 = Rectangle((1, legend_y), 1.2, 0.35, facecolor='#7BC043', edgecolor='none')
        ax.add_patch(rect1)
        ax.text(2.5, legend_y + 0.175, 'Світло було', va='center', fontsize=11, color='#666')
        
        # Червоний квадратик
        rect2 = Rectangle((8, legend_y), 1.2, 0.35, facecolor='#FF6B6B', edgecolor='none')
        ax.add_patch(rect2)
        ax.text(9.5, legend_y + 0.175, 'Світла не було', va='center', fontsize=11, color='#666')
        
        # Загальна статистика
        if num_days > 1:
            total_with = sum(d['hours_with_power'] for d in stats.values())
            total_without = sum(d['hours_without_power'] for d in stats.values())
            avg_with = total_with / num_days
            
            stats_y = legend_y - 0.6
            
            total_with_h = int(total_with)
            total_with_m = int((total_with % 1) * 60)
            
            total_without_h = int(total_without)
            total_without_m = int((total_without % 1) * 60)
            
            avg_with_h = int(avg_with)
            avg_with_m = int((avg_with % 1) * 60)
            
            ax.text(1, stats_y, f"● Всього світло було: {total_with_h}год {total_with_m}хв", 
                   fontsize=10, color='#666', va='top')
            ax.text(1, stats_y - 0.17, f"● Всього світла не було: {total_without_h}год {total_without_m}хв",
                   fontsize=10, color='#666', va='top')
            ax.text(1, stats_y - 0.34, f"● В середньому світло було {avg_with_h}год {avg_with_m}хв за добу",
                   fontsize=10, color='#666', va='top')
        
        plt.tight_layout()
        
        # Зберігаємо
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', 
                   facecolor='white', edgecolor='none', pad_inches=0.3)
        buf.seek(0)
        plt.close()
        
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
        logger.info("Графік: 00:00-06:30 світло, 06:30-09:30 відкл, 09:30-00:00 світло")
        
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