diff --git a/telegram_bot.py b/telegram_bot.py
index 40a4d4ff1425c8224da868f17d65686a00579c80..b51dbcb95ca6033eeea3ec53294f4077052508ff 100644
--- a/telegram_bot.py
+++ b/telegram_bot.py
@@ -4,166 +4,216 @@
 
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
-        # 📌 ТУТ МІНЯТИ ГРАФІК!
-        # Формат: (година, хвилина, є_світло)
+        # 📌 ТУТ МІНЯТИ ГРАФІКИ ПО ДНЯХ!
+        # Ключ: "YYYY-MM-DD"
+        # Формат періоду: (година, хвилина, є_світло)
         # ========================================
-        self.schedule_31 = [
-            (0, 0, True),      # 00:00 - світло
-            (6, 30, False),    # 06:30 - відключення  
-            (9, 30, True),     # 09:30 - світло до кінця доби
-        ]
+        self.schedules_31_by_date = {
+            "2026-02-14": [
+                (0, 0, True),
+                (6, 30, False),
+                (9, 30, True),
+            ],
+            "2026-02-15": [
+                (0, 0, True),
+                (5, 0, False),
+                (8, 30, True),
+            ],
+            "2026-02-16": [
+                (0, 0, True),
+                (7, 30, False),
+                (10, 0, True),
+            ],
+        }
         
         self.init_stats()
     
     def init_stats(self):
         if not os.path.exists(self.stats_file):
-            # ========================================
-            # 📌 ТУТ ДОДАВАТИ Нові ДНІ!
-            # ========================================
-            stats = {
-                "2026-02-14": {
-                    'hours_with_power': 21.0,    # Години зі світлом
-                    'hours_without_power': 3.0,  # Години без світла
-                },
-                "2026-02-15": {
-                    'hours_with_power': 0.0,     # 0 = графіки відсутні
-                    'hours_without_power': 0.0,  # 0 = графіки відсутні
-                }
-            }
+            stats = self.build_stats_from_schedules()
             self.save_stats(stats)
+
+    def build_stats_from_schedules(self):
+        """Автоматично рахує години зі світлом/без світла для кожного дня з графіком."""
+        stats = {}
+        for date_str, schedule in self.schedules_31_by_date.items():
+            minutes_with_power = 0
+
+            for i, (h, m, has_power) in enumerate(schedule):
+                start_min = h * 60 + m
+                if i + 1 < len(schedule):
+                    next_h, next_m, _ = schedule[i + 1]
+                    end_min = next_h * 60 + next_m
+                else:
+                    end_min = 24 * 60
+
+                if has_power:
+                    minutes_with_power += end_min - start_min
+
+            hours_with = round(minutes_with_power / 60, 1)
+            stats[date_str] = {
+                'hours_with_power': hours_with,
+                'hours_without_power': round(24 - hours_with, 1),
+            }
+
+        return stats
+
+    def get_schedule_for_date(self, date_obj=None):
+        """Повертає графік для конкретної дати або найближчий доступний."""
+        if not self.schedules_31_by_date:
+            return [(0, 0, True)]
+
+        if date_obj is None:
+            date_obj = self.get_kyiv_time().date()
+
+        date_key = date_obj.strftime('%Y-%m-%d')
+        if date_key in self.schedules_31_by_date:
+            return self.schedules_31_by_date[date_key]
+
+        # Якщо немає графіка на сьогодні - беремо останній відомий
+        latest_date = max(self.schedules_31_by_date.keys())
+        return self.schedules_31_by_date[latest_date]
     
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
+        schedule = self.get_schedule_for_date(now.date())
         
         periods = []
-        for i, (h, m, status) in enumerate(self.schedule_31):
+        for i, (h, m, status) in enumerate(schedule):
             start_min = h * 60 + m
             
-            if i + 1 < len(self.schedule_31):
-                next_h, next_m, _ = self.schedule_31[i + 1]
+            if i + 1 < len(schedule):
+                next_h, next_m, _ = schedule[i + 1]
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
+        schedule = self.get_schedule_for_date(now.date())
         
         schedule_data = {
             'timestamp': now.isoformat(),
             'group': '3.1',
             'periods': []
         }
         
-        for i, (h, m, status) in enumerate(self.schedule_31):
-            if i + 1 < len(self.schedule_31):
-                next_h, next_m, _ = self.schedule_31[i + 1]
+        for i, (h, m, status) in enumerate(schedule):
+            if i + 1 < len(schedule):
+                next_h, next_m, _ = schedule[i + 1]
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
     
-    def get_hour_status(self, hour_decimal):
+    def get_hour_status(self, hour_decimal, date_str):
         current_minutes = hour_decimal * 60
-        
-        for i, (h, m, status) in enumerate(self.schedule_31):
+        try:
+            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
+        except ValueError:
+            date_obj = self.get_kyiv_time().date()
+
+        schedule = self.get_schedule_for_date(date_obj)
+
+        for i, (h, m, status) in enumerate(schedule):
             start_min = h * 60 + m
             
-            if i + 1 < len(self.schedule_31):
-                next_h, next_m, _ = self.schedule_31[i + 1]
+            if i + 1 < len(schedule):
+                next_h, next_m, _ = schedule[i + 1]
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
@@ -182,51 +232,51 @@ class PowerScheduleBot:
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
-                    has_power = self.get_hour_status(hour_decimal)
+                    has_power = self.get_hour_status(hour_decimal, date_str)
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
                 
