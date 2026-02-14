#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram бот з таймером світла"""

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
        }
        
        self.init_stats()
        self.cleanup_old_days()
    
    def cleanup_old_days(self):
        now = self.get_kyiv_time()
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        to_remove = []
        for date_str in self.schedules.keys():
            if date_str < yesterday:
                to_remove.append(date_str)
        
        for date_str in to_remove:
            del self.schedules[date_str]
            logger.info(f"Видалено старий графік: {date_str}")
        
        stats = self.load_stats()
        updated = False
        
        to_remove_stats = []
        for date_str in stats.keys():
            if date_str < yesterday:
                to_remove_stats.append(date_str)
        
        for date_str in to_remove_stats:
            del stats[date_str]
            updated = True
            logger.info(f"Видалено стару статистику: {date_str}")
        
        if updated:
            self.save_stats(stats)
    
    def init_stats(self):
        if not os.path.exists(self.stats_file):
            stats = {
                "2026-02-14": {
                    'hours_with_power': 21.0,
                    'hours_without_power': 3.0,
                },
                "2026-02-15": {
                    'hours_with_power': 19.0,
                    'hours_without_power': 5.0,
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
            [KeyboardButton("⏱️ Таймер світла")],
            [KeyboardButton("🌐 Відкрити сайт")],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def get_kyiv_time(self):
        return datetime.now(KYIV_TZ)
    
    def get_schedule_for_date(self, date_str):
        if date_str in self.schedules:
            return self.schedules[date_str]
        else:
            return None
    
    def get_current_status(self):
        now = self.get_kyiv_time()
        today_str = now.strftime('%Y-%m-%d')
        
        schedule = self.get_schedule_for_date(today_str)
        
        if not schedule:
            return {
                'start': 0,
                'end': 24 * 60,
                'status': None,
                'start_time': '00:00',
                'end_time': '00:00',
                'period_start_datetime': None,
                'period_end_datetime': None
            }
        
        current_minutes = now.hour * 60 + now.minute
        
        periods = []
        for i, (h, m, status) in enumerate(schedule):
            start_min = h * 60 + m
            
            # Час початку періоду
            period_start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            
            if i + 1 < len(schedule):
                next_h, next_m, _ = schedule[i + 1]
                end_min = next_h * 60 + next_m
                end_time = f"{next_h:02d}:{next_m:02d}"
                period_end = now.replace(hour=next_h, minute=next_m, second=0, microsecond=0)
            else:
                end_min = 24 * 60
                end_time = "00:00"
                # Кінець доби = початок наступного дня
                period_end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            periods.append({
                'start': start_min,
                'end': end_min,
                'status': status,
                'start_time': f"{h:02d}:{m:02d}",
                'end_time': end_time,
                'period_start_datetime': period_start,
                'period_end_datetime': period_end
            })
        
        for period in periods:
            if period['start'] <= current_minutes < period['end']:
                return period
        
        return periods[0]
    
    def get_next_period(self):
        """Отримує наступний період після поточного"""
        now = self.get_kyiv_time()
        today_str = now.strftime('%Y-%m-%d')
        
        schedule = self.get_schedule_for_date(today_str)
        
        if not schedule:
            return None
        
        current_minutes = now.hour * 60 + now.minute
        
        # Шукаємо наступний період
        for i, (h, m, status) in enumerate(schedule):
            period_start_min = h * 60 + m
            
            if period_start_min > current_minutes:
                # Це наступний період
                return {
                    'start_time': f"{h:02d}:{m:02d}",
                    'status': status,
                    'start_datetime': now.replace(hour=h, minute=m, second=0, microsecond=0)
                }
        
        # Якщо наступного періоду сьогодні немає - беремо перший період завтра
        tomorrow = now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y-%m-%d')
        schedule_tomorrow = self.get_schedule_for_date(tomorrow_str)
        
        if schedule_tomorrow and len(schedule_tomorrow) > 0:
            h, m, status = schedule_tomorrow[0]
            return {
                'start_time': f"{h:02d}:{m:02d}",
                'status': status,
                'start_datetime': tomorrow.replace(hour=h, minute=m, second=0, microsecond=0)
            }
        
        return None
    
    def format_timer_message(self):
        """НОВИЙ пункт - таймер світла"""
        now = self.get_kyiv_time()
        current = self.get_current_status()
        
        if current['status'] is None:
            return "❌ Графік відсутній"
        
        # Початок поточного періоду
        period_start = current['period_start_datetime']
        period_end = current['period_end_datetime']
        
        # Скільки часу минуло з початку періоду
        elapsed = now - period_start
        elapsed_hours = int(elapsed.total_seconds() // 3600)
        elapsed_minutes = int((elapsed.total_seconds() % 3600) // 60)
        elapsed_seconds = int(elapsed.total_seconds() % 60)
        
        # Скільки часу до кінця періоду
        remaining = period_end - now
        remaining_hours = int(remaining.total_seconds() // 3600)
        remaining_minutes = int((remaining.total_seconds() % 3600) // 60)
        remaining_seconds = int(remaining.total_seconds() % 60)
        
        # Наступний період
        next_period = self.get_next_period()
        
        if current['status']:
            # Є світло
            emoji = "🟢✅"
            status = "СВІТЛО Є"
            
            msg = f"{emoji}\n\n"
            msg += f"<b>⏱️ {status}</b>\n\n"
            msg += f"🕐 Зараз: {now.strftime('%H:%M:%S')}\n\n"
            
            msg += f"✅ Світло є вже:\n"
            msg += f"<b>{elapsed_hours} год {elapsed_minutes} хв {elapsed_seconds} сек</b>\n\n"
            
            msg += f"⏳ Залишилось до відключення:\n"
            msg += f"<b>{remaining_hours} год {remaining_minutes} хв {remaining_seconds} сек</b>\n\n"
            
            msg += f"🔴 Наступне відключення:\n"
            msg += f"<b>о {current['end_time']}</b>\n\n"
        else:
            # Немає світла
            emoji = "🔴❌"
            status = "СВІТЛА НЕМАЄ"
            
            msg = f"{emoji}\n\n"
            msg += f"<b>⏱️ {status}</b>\n\n"
            msg += f"🕐 Зараз: {now.strftime('%H:%M:%S')}\n\n"
            
            msg += f"❌ Світла немає вже:\n"
            msg += f"<b>{elapsed_hours} год {elapsed_minutes} хв {elapsed_seconds} сек</b>\n\n"
            
            msg += f"⏳ Залишилось до ввімкнення:\n"
            msg += f"<b>{remaining_hours} год {remaining_minutes} хв {remaining_seconds} сек</b>\n\n"
            
            msg += f"🟢 Наступне ввімкнення:\n"
            msg += f"<b>о {current['end_time']}</b>\n\n"
        
        # Інфо про наступний період після цього
        if next_period:
            time_until_next = next_period['start_datetime'] - now
            hours_until = int(time_until_next.total_seconds() // 3600)
            minutes_until = int((time_until_next.total_seconds() % 3600) // 60)
            
            if next_period['status']:
                msg += f"📅 Потім ввімкнуть о <b>{next_period['start_time']}</b>\n"
                msg += f"   (через {hours_until}год {minutes_until}хв)\n"
            else:
                msg += f"📅 Потім відключать о <b>{next_period['start_time']}</b>\n"
                msg += f"   (через {hours_until}год {minutes_until}хв)\n"
        
        msg += f"\n📍 Група: 3.1"
        
        return msg
    
    def calculate_day_stats(self, periods):
        total_with = 0
        for period in periods:
            start_h, start_m = map(int, period['start'].split(':'))
            end_h, end_m = map(int, period['end'].split(':'))
            
            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m if period['end'] != "00:00" else 1440
            
            duration = end_min - start_min
            
            if period['has_power']:
                total_with += duration
        
        total_without = 1440 - total_with
        
        return {
            'with_power': total_with / 60,
            'without_power': total_without / 60
        }
    
    def get_full_schedule(self):
        now = self.get_kyiv_time()
        today_str = now.strftime('%Y-%m-%d')
        
        schedule_today = self.get_schedule_for_date(today_str)
        
        tomorrow = now + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y-%m-%d')
        schedule_tomorrow = self.get_schedule_for_date(tomorrow_str)
        
        result = {
            'timestamp': now.isoformat(),
            'group': '3.1',
            'today': {
                'date': today_str,
                'periods': []
            },
            'tomorrow': {
                'date': tomorrow_str,
                'periods': []
            }
        }
        
        if schedule_today:
            for i, (h, m, status) in enumerate(schedule_today):
                if i + 1 < len(schedule_today):
                    next_h, next_m, _ = schedule_today[i + 1]
                    end_time = f"{next_h:02d}:{next_m:02d}"
                else:
                    end_time = "00:00"
                
                result['today']['periods'].append({
                    'start': f"{h:02d}:{m:02d}",
                    'end': end_time,
                    'status': 'Є світло' if status else 'Відключення',
                    'has_power': status
                })
        
        if schedule_tomorrow:
            for i, (h, m, status) in enumerate(schedule_tomorrow):
                if i + 1 < len(schedule_tomorrow):
                    next_h, next_m, _ = schedule_tomorrow[i + 1]
                    end_time = f"{next_h:02d}:{next_m:02d}"
                else:
                    end_time = "00:00"
                
                result['tomorrow']['periods'].append({
                    'start': f"{h:02d}:{m:02d}",
                    'end': end_time,
                    'status': 'Є світло' if status else 'Відключення',
                    'has_power': status
                })
        
        return result
    
    def get_hour_status(self, hour_decimal, date_str):
        schedule = self.get_schedule_for_date(date_str)
        
        if not schedule:
            return None
        
        current_minutes = hour_decimal * 60
        
        for i, (h, m, status) in enumerate(schedule):
            start_min = h * 60 + m
            
            if i + 1 < len(schedule):
                next_h, next_m, _ = schedule[i + 1]
                end_min = next_h * 60 + next_m
            else:
                end_min = 24 * 60
            
            if start_min <= current_minutes < end_min:
                return status
        
        return True
    
    def generate_stats_image(self):
        stats = self.load_stats()
        now = self.get_kyiv_time()

        if not stats:
            return None

        sorted_dates = sorted(stats.keys())
        num_days = len(sorted_dates)

        fig_width = 16
        fig_height = 6 + num_days * 1.0

        fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor='white')
        ax.set_facecolor('white')

        if num_days > 1:
            first_date = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            last_date = datetime.strptime(sorted_dates[-1], '%Y-%m-%d')
            title = f"Графік відключень світла {first_date.strftime('%d.%m')} - {last_date.strftime('%d.%m')}"
        else:
            date_obj = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            title = f"Графік відключень світла {date_obj.strftime('%d.%m.%Y')}"

        ax.set_title(title, fontsize=17, color='#AAAAAA', pad=20)

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

            for seg in range(48):
                hour_decimal = seg / 2
                has_power = self.get_hour_status(hour_decimal, date_str)

                if has_power is None:
                    color = '#CCCCCC'
                else:
                    color = '#7BC043' if has_power else '#FF6B6B'

                rect = Rectangle((seg/2, y_pos - 0.38), 0.5, 0.76,
                                 facecolor=color, edgecolor='white', linewidth=2.0)
                ax.add_patch(rect)

            date_label = f"{day_short} ({date_obj.strftime('%d.%m')})"
            ax.text(-1.4, y_pos, date_label, va='center', ha='right',
                    fontsize=12, weight='bold', color='#333333')

            h_with = int(hours_with)
            h_without = int(hours_without)

            ax.text(25.0, y_pos + 0.2, f"{h_with}год",
                    va='center', ha='left',
                    fontsize=11, color='#7BC043', weight='bold')

            ax.text(25.0, y_pos - 0.2, f"{h_without}год",
                    va='center', ha='left',
                    fontsize=11, color='#FF6B6B')

        ax.set_xlim(-3.5, 28)
        ax.set_ylim(-2.8, num_days + 0.5)

        ax.set_xticks(range(0, 25))
        ax.set_xticklabels([str(i) for i in range(0, 25)],
                           fontsize=10, color='#888888', weight='bold')
        ax.set_yticks([])

        for x in [0, 4, 8, 12, 16, 20, 24]:
            ax.axvline(x, color='#BBBBBB', linewidth=1.5, alpha=0.8)

        for x in range(1, 24):
            if x not in [4, 8, 12, 16, 20]:
                ax.axvline(x, color='#DDDDDD', linewidth=0.8, alpha=0.5)

        for spine in ax.spines.values():
            spine.set_visible(False)

        # =============================
        # ВЕРТИКАЛЬНА ЛЕГЕНДА ЗЛІВА
        # =============================

        legend_x = -3.0
        legend_y = -1.2

        rect_green = Rectangle((legend_x, legend_y), 0.4, 0.3,
                               facecolor='#7BC043', edgecolor='none')
        ax.add_patch(rect_green)

        ax.text(legend_x + 0.6, legend_y + 0.15,
                'Світло було',
                va='center', ha='left',
                fontsize=11, color='#666666')

        rect_red = Rectangle((legend_x, legend_y - 0.6), 0.4, 0.3,
                             facecolor='#FF6B6B', edgecolor='none')
        ax.add_patch(rect_red)

        ax.text(legend_x + 0.6, legend_y - 0.45,
                'Світла не було',
                va='center', ha='left',
                fontsize=11, color='#666666')

        # =============================
        # СТАТИСТИКА ПІД ЛЕГЕНДОЮ
        # =============================

        days_with_data = [
            d for d in stats.values()
            if d['hours_with_power'] > 0 or d['hours_without_power'] > 0
        ]

        if len(days_with_data) > 1:
            total_with = sum(d['hours_with_power'] for d in days_with_data)
            total_without = sum(d['hours_without_power'] for d in days_with_data)
            avg_with = total_with / len(days_with_data)

            stats_y = legend_y - 1.2

            ax.text(legend_x, stats_y,
                    f"Всього світло було: {int(total_with)}год",
                    fontsize=10, color='#666666', va='top')

            ax.text(legend_x, stats_y - 0.35,
                    f"Всього світла не було: {int(total_without)}год",
                    fontsize=10, color='#666666', va='top')

            ax.text(legend_x, stats_y - 0.7,
                    f"В середньому світло було {int(avg_with)}год за добу",
                    fontsize=10, color='#666666', va='top')

        plt.tight_layout(pad=1.5)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150,
                    bbox_inches='tight', facecolor='white', pad_inches=0.5)
        buf.seek(0)
        plt.close('all')

        return buf

        
        if not stats:
            return None
        
        sorted_dates = sorted(stats.keys())
        num_days = len(sorted_dates)
        
        fig_width = 16
        fig_height = 7 + num_days * 1.1
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor='white')
        ax.set_facecolor('white')
        
        if num_days > 1:
            first_date = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            last_date = datetime.strptime(sorted_dates[-1], '%Y-%m-%d')
            title = f"Графік відключень світла {first_date.strftime('%d.%m')} - {last_date.strftime('%d.%m')}"
        else:
            date_obj = datetime.strptime(sorted_dates[0], '%Y-%m-%d')
            title = f"Графік відключень світла {date_obj.strftime('%d.%m.%Y')}"
        
        ax.set_title(title, fontsize=17, color='#AAAAAA', pad=20, weight='normal')
        
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
            
            if hours_with == 0 and hours_without == 0:
                for seg in range(48):
                    rect = Rectangle((seg/2, y_pos - 0.38), 0.5, 0.76, 
                                    facecolor='#CCCCCC', edgecolor='white', linewidth=1.5)
                    ax.add_patch(rect)
            else:
                for seg in range(48):
                    hour_decimal = seg / 2
                    has_power = self.get_hour_status(hour_decimal, date_str)
                    
                    if has_power is None:
                        color = '#CCCCCC'
                    else:
                        color = '#7BC043' if has_power else '#FF6B6B'
                    
                    rect = Rectangle((seg/2, y_pos - 0.38), 0.5, 0.76, 
                                    facecolor=color, edgecolor='white', linewidth=2.0)
                    ax.add_patch(rect)
            
            date_label = f"{day_short} ({date_obj.strftime('%d.%m')})"
            ax.text(-1.2, y_pos, date_label, va='center', ha='right', 
                   fontsize=12, weight='bold', color='#333333')
            
            if hours_with == 0 and hours_without == 0:
                ax.text(25.0, y_pos, "графіки відсутні", va='center', ha='left',
                       fontsize=11, color='#999999', style='italic')
            else:
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
        
        ax.set_xlim(-1.8, 28)
        ax.set_ylim(-3.5, num_days + 0.1)
        
        ax.set_xticks(range(0, 25))
        ax.set_xticklabels([str(i) for i in range(0, 25)], 
                          fontsize=10, color='#888888', weight='bold')
        ax.set_yticks([])
        
        for x in [0, 4, 8, 12, 16, 20, 24]:
            ax.axvline(x, color='#BBBBBB', linewidth=1.5, alpha=0.8, zorder=0)
        
        for x in range(1, 24):
            if x not in [4, 8, 12, 16, 20]:
                ax.axvline(x, color='#DDDDDD', linewidth=0.8, alpha=0.5, zorder=0)
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        legend_y = -2.2
        
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
                   facecolor='white', pad_inches=0.5)
        buf.seek(0)
        plt.close('all')
        
        return buf
    
    def format_schedule_message(self, data):
        now = self.get_kyiv_time()
        
        msg = f"⚡️ <b>Графік відключень - Група 3.1</b>\n"
        msg += f"🕐 {now.strftime('%d.%m.%Y %H:%M')}\n\n"
        
        current = self.get_current_status()
        
        if current['status'] is None:
            msg += f"❌ <b>ГРАФІК ВІДСУТНІЙ</b>\n\n"
        elif current['status']:
            msg += f"<b>🟢 ЗАРАЗ Є СВІТЛО</b>\n"
            msg += f"До {current['end_time']}\n\n"
        else:
            msg += f"<b>🔴 ЗАРАЗ ВІДКЛЮЧЕННЯ</b>\n"
            msg += f"До {current['end_time']}\n\n"
        
        msg += "─" * 35 + "\n\n"
        
        today_periods = data['today']['periods']
        if today_periods:
            msg += "<b>📅 Повний графік:</b>\n\n"
            
            current_minutes = now.hour * 60 + now.minute
            
            for period in today_periods:
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
            
            stats_today = self.calculate_day_stats(today_periods)
            
            msg += f"\n📊 <b>Статистика:</b>\n"
            msg += f"🟢 Зі світлом: {stats_today['with_power']:.1f} год\n"
            msg += f"🔴 Без світла: {stats_today['without_power']:.1f} год\n"
        
        tomorrow_periods = data['tomorrow']['periods']
        if tomorrow_periods:
            tomorrow_date = datetime.strptime(data['tomorrow']['date'], '%Y-%m-%d')
            msg += f"\n\n👉 <b>Графік на завтра ({tomorrow_date.strftime('%d.%m')}):</b>\n\n"
            
            for period in tomorrow_periods:
                start = period['start']
                end = period['end']
                has_power = period['has_power']
                
                emoji = "🟢" if has_power else "🔴"
                status_text = "Є світло" if has_power else "Відключення"
                
                msg += f"      {start}-{end}  {emoji} {status_text}\n"
            
            stats_tomorrow = self.calculate_day_stats(tomorrow_periods)
            
            msg += f"\n📊 <b>Статистика:</b>\n"
            msg += f"🟢 Зі світлом: {stats_tomorrow['with_power']:.1f} год\n"
            msg += f"🔴 Без світла: {stats_tomorrow['without_power']:.1f} год\n"
        
        msg += f"\n⚠️ Графіки можуть змінюватись!"
        
        return msg
    
    def format_now_message(self):
        current = self.get_current_status()
        now = self.get_kyiv_time()
        
        if current['status'] is None:
            emoji = "❌"
            status = "ГРАФІК ВІДСУТНІЙ"
        elif current['status']:
            emoji = "🟢✅"
            status = "Є СВІТЛО"
        else:
            emoji = "🔴❌"
            status = "ВІДКЛЮЧЕННЯ"
        
        msg = f"{emoji}\n\n"
        msg += f"<b>ЗАРАЗ ({now.strftime('%H:%M')}):</b>\n"
        msg += f"<b>{status}</b>\n\n"
        
        if current['status'] is not None:
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
        
        elif text == "⏱️ Таймер світла":
            message = self.format_timer_message()
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard())
        
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
    
    async def timer_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = self.format_timer_message()
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=self.get_main_keyboard())
    
    def run(self):
        now = self.get_kyiv_time()
        logger.info(f"Запуск бота. Київський час: {now.strftime('%H:%M')}")
        
        application = Application.builder().token(self.bot_token).build()
        
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("schedule", self.schedule_command))
        application.add_handler(CommandHandler("now", self.now_command))
        application.add_handler(CommandHandler("stats", self.stats_command))
        application.add_handler(CommandHandler("timer", self.timer_command))
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
