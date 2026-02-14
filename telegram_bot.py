#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram бот з таймером світла та виправленою логікою переходів через північ.
📍 Група: 3.1
"""

import logging
from datetime import datetime, timezone, timedelta
import json
import os
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

KYIV_TZ = timezone(timedelta(hours=2))

class PowerScheduleBot:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.base_url = "https://off.energy.mk.ua/"
        self.stats_file = "weekly_stats.json"
        
        # Актуальний розклад згідно з твоїм графіком (картинкою)
        # Формат: (година, хвилина, чи є світло)
        self.schedules = {
            "2026-02-14": [
                (0, 0, True),
                (6, 30, False),
                (9, 30, True),
            ],
            "2026-02-15": [
                (0, 0, True),
                (10, 30, False),
                (13, 0, True),
                (17, 30, False),
                (20, 0, True),
            ],
            "2026-02-16": [
                (0, 0, True), # Передбачаємо, що в пн з півночі світло є
            ],
        }
        
        self.init_stats()
        self.cleanup_old_days()

    # ==========================================
    # РОБОТА З ЧАСОМ ТА ГРАФІКОМ (ВИПРАВЛЕНО)
    # ==========================================

    def get_kyiv_time(self):
        return datetime.now(KYIV_TZ)

    def get_schedule_for_date(self, date_str):
        return self.schedules.get(date_str)

    def get_current_status(self):
        """
        Знаходить поточний період і ВИПРАВЛЕНО визначає його кінець,
        перевіряючи розклад на наступний день.
        """
        now = self.get_kyiv_time()
        today_str = now.strftime('%Y-%m-%d')
        tomorrow_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')
        
        schedule_today = self.get_schedule_for_date(today_str)
        if not schedule_today:
            return {'status': None, 'start_time': '?', 'end_time': '?'}

        current_minutes = now.hour * 60 + now.minute
        
        # 1. Знаходимо поточний запис у сьогоднішньому графіку
        idx = -1
        for i, (h, m, _) in enumerate(schedule_today):
            if (h * 60 + m) <= current_minutes:
                idx = i
            else:
                break
        
        if idx == -1: return {'status': None}

        h, m, status = schedule_today[idx]
        period_start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # 2. Визначаємо кінець періоду
        period_end = None
        end_time_str = ""

        if idx + 1 < len(schedule_today):
            # Якщо сьогодні ще будуть зміни
            next_h, next_m, _ = schedule_today[idx + 1]
            period_end = now.replace(hour=next_h, minute=next_m, second=0, microsecond=0)
            end_time_str = f"{next_h:02d}:{next_m:02d}"
        else:
            # Якщо це останній запис сьогодні — дивимось у завтрашній графік
            schedule_tomorrow = self.get_schedule_for_date(tomorrow_str)
            if schedule_tomorrow:
                # Шукаємо ПЕРШУ зміну статусу завтра, яка відрізняється від поточної
                found = False
                for th, tm, ts in schedule_tomorrow:
                    if ts != status:
                        period_end = (now + timedelta(days=1)).replace(hour=th, minute=tm, second=0, microsecond=0)
                        end_time_str = f"{th:02d}:{tm:02d}"
                        found = True
                        break
                if not found:
                    # Якщо завтра весь день такий самий статус
                    period_end = (now + timedelta(days=1)).replace(hour=23, minute=59)
                    end_time_str = "23:59"
            else:
                # Дефолт до півночі, якщо завтрашній день не завантажено
                period_end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_time_str = "00:00"

        return {
            'status': status,
            'start_time': f"{h:02d}:{m:02d}",
            'end_time': end_time_str,
            'period_start_datetime': period_start,
            'period_end_datetime': period_end
        }

    # ==========================================
    # ГЕНЕРАЦІЯ ПОВІДОМЛЕНЬ (ТАЙМЕР)
    # ==========================================

    def format_timer_message(self):
        now = self.get_kyiv_time()
        current = self.get_current_status()
        
        if current.get('status') is None:
            return "❌ Графік на сьогодні не знайдено."

        # Розрахунок інтервалів
        elapsed = now - current['period_start_datetime']
        remaining = current['period_end_datetime'] - now

        def format_delta(td):
            s = int(td.total_seconds())
            return f"<b>{s//3600} год {(s%3600)//60} хв {s%60} сек</b>"

        is_power = current['status']
        emoji = "🟢✅" if is_power else "🔴❌"
        status_text = "СВІТЛО Є" if is_power else "СВІТЛА НЕМАЄ"
        
        msg = f"{emoji}\n\n"
        msg += f"<b>⏱️ {status_text}</b>\n\n"
        msg += f"🕐 Зараз: {now.strftime('%H:%M:%S')}\n\n"
        msg += f"{'✅' if is_power else '❌'} {status_text.capitalize()} вже:\n{format_delta(elapsed)}\n\n"
        msg += f"⏳ Залишилось {'до відключення' if is_power else 'до ввімкнення'}:\n{format_delta(remaining)}\n\n"
        msg += f"{'🔴 Наступне відключення' if is_power else '🟢 Наступне ввімкнення'}:\n"
        msg += f"<b>о {current['end_time']}</b>\n\n"
        msg += "📍 Група: 3.1"
        return msg

    # ==========================================
    # СТАТИСТИКА ТА ВІЗУАЛІЗАЦІЯ (ТВІЙ ОРИГІНАЛ)
    # ==========================================

    def init_stats(self):
        if not os.path.exists(self.stats_file):
            stats = {
                "2026-02-14": {'hours_with_power': 21.0, 'hours_without_power': 3.0},
                "2026-02-15": {'hours_with_power': 19.0, 'hours_without_power': 5.0}
            }
            self.save_stats(stats)

    def load_stats(self):
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}

    def save_stats(self, stats):
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    def generate_stats_image(self):
        stats = self.load_stats()
        if not stats: return None
        
        sorted_dates = sorted(stats.keys())
        num_days = len(sorted_dates)
        
        fig, ax = plt.subplots(figsize=(12, 4 + num_days), facecolor='white')
        ax.set_title(f"Графік відключень (Група 3.1)", fontsize=15, pad=20)

        for idx, date_str in enumerate(sorted_dates):
            y_pos = num_days - idx - 1
            # Малюємо блоки по 30 хв
            for half_hour in range(48):
                h_dec = half_hour / 2
                # Визначаємо статус для цієї години
                status = self.get_status_at_time(date_str, h_dec)
                color = '#7BC043' if status else '#FF6B6B'
                ax.add_patch(Rectangle((h_dec, y_pos - 0.4), 0.5, 0.8, facecolor=color, edgecolor='white', linewidth=0.5))
            
            ax.text(-0.5, y_pos, date_str, va='center', ha='right', fontweight='bold')

        ax.set_xlim(0, 24)
        ax.set_ylim(-1, num_days)
        ax.set_xticks(range(25))
        ax.set_yticks([])
        plt.grid(axis='x', color='gray', linestyle='--', alpha=0.3)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        return buf

    def get_status_at_time(self, date_str, hour_decimal):
        sched = self.get_schedule_for_date(date_str)
        if not sched: return True
        current_m = hour_decimal * 60
        status = True
        for h, m, s in sched:
            if (h * 60 + m) <= current_m: status = s
            else: break
        return status

    def cleanup_old_days(self):
        now = self.get_kyiv_time()
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        stats = self.load_stats()
        new_stats = {d: v for d, v in stats.items() if d >= yesterday}
        self.save_stats(new_stats)

    # ==========================================
    # ОБРОБНИКИ КОМАНД ТЕЛЕГРАМ
    # ==========================================

    def get_main_keyboard(self):
        return ReplyKeyboardMarkup([
            [KeyboardButton("⚡ Зараз є світло?")],
            [KeyboardButton("📅 Повний графік"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("⏱️ Таймер світла")],
            [KeyboardButton("🌐 Відкрити сайт")]
        ], resize_keyboard=True)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "⏱️ Таймер світла":
            await update.message.reply_text(self.format_timer_message(), parse_mode='HTML')
        elif text == "📊 Статистика":
            img = self.generate_stats_image()
            if img: await update.message.reply_photo(img, caption="Ваша статистика відключень")
        elif text == "⚡ Зараз є світло?":
            curr = self.get_current_status()
            st = "Є СВІТЛО 🟢" if curr.get('status') else "ВІДКЛЮЧЕННЯ 🔴"
            await update.message.reply_text(f"<b>Зараз: {st}</b>\nДо {curr.get('end_time')}", parse_mode='HTML')
        elif text == "🌐 Відкрити сайт":
            await update.message.reply_text(f"Сайт обленерго: {self.base_url}")
        elif text == "📅 Повний графік":
             await update.message.reply_text("Функція текстування графіка в розробці, використовуйте 'Статистика' для фото.")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Привіт! Я твій помічник по світлу (Група 3.1).", reply_markup=self.get_main_keyboard())

# --- ЗАПУСК ---
def main():
    TOKEN = "8291719049:AAG3s_jDNdrYhpF8kQa6D9Mzb_HYNwByHSk"
    bot = PowerScheduleBot(TOKEN)
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    logger.info("Бот полетів!")
    app.run_polling()

if __name__ == '__main__':
    main()
