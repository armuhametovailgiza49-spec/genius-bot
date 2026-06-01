import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "genius_bot.db")


class Database:
    def __init__(self):
        self.path = DB_PATH

    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def init(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS profile (
                    user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now')), PRIMARY KEY (user_id, key));
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    category TEXT NOT NULL, content TEXT NOT NULL, source TEXT,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS dialog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, event_time TEXT NOT NULL, remind_at TEXT,
                    prep_steps TEXT, reminded_main INTEGER DEFAULT 0,
                    is_done INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS roadmaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    dream TEXT NOT NULL, steps_json TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    filename TEXT NOT NULL, file_type TEXT, summary TEXT, full_text TEXT,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    timezone TEXT DEFAULT 'Asia/Yekaterinburg', onboarded INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL, category TEXT NOT NULL, description TEXT,
                    is_pp INTEGER DEFAULT 0, is_healthy INTEGER DEFAULT 1, shop TEXT,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS income (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL, source TEXT, note TEXT,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS budget_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    category TEXT NOT NULL, monthly_limit INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')), UNIQUE(user_id, category));
                CREATE TABLE IF NOT EXISTS savings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL, note TEXT,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS pp_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    name TEXT NOT NULL, category TEXT DEFAULT 'base', is_pp INTEGER DEFAULT 1,
                    days_supply INTEGER DEFAULT 7, last_bought TEXT,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS shopping_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    item TEXT NOT NULL, amount TEXT, is_pp INTEGER DEFAULT 1,
                    is_bought INTEGER DEFAULT 0, added_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS blog_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    platform TEXT DEFAULT 'instagram', followers INTEGER NOT NULL,
                    recorded_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS content_plan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, format TEXT, theme TEXT, shoot_date TEXT,
                    remind_at TEXT, prep_steps TEXT, is_done INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS barter_deals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    brand TEXT NOT NULL, category TEXT, value_rub INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'wishlist', followers_needed INTEGER DEFAULT 0,
                    note TEXT, created_at TEXT DEFAULT (datetime('now')));
                CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_memory_user ON memory(user_id, category);
                CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
                CREATE INDEX IF NOT EXISTS idx_dialog_user ON dialog(user_id);
            """)

    def set_profile(self, user_id, key, value):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO profile (user_id,key,value,updated_at) VALUES (?,?,?,datetime('now'))", (user_id, key, value))

    def get_profile(self, user_id) -> dict:
        with self.conn() as c:
            rows = c.execute("SELECT key,value FROM profile WHERE user_id=?", (user_id,)).fetchall()
            return {r["key"]: r["value"] for r in rows}

    def delete_profile_key(self, user_id, key):
        with self.conn() as c:
            c.execute("DELETE FROM profile WHERE user_id=? AND key=?", (user_id, key))

    def add_memory(self, user_id, category, content, source="dialog"):
        with self.conn() as c:
            c.execute("INSERT INTO memory (user_id,category,content,source) VALUES (?,?,?,?)", (user_id, category, content, source))

    def get_memories(self, user_id, category=None, limit=50) -> list:
        with self.conn() as c:
            if category:
                rows = c.execute("SELECT * FROM memory WHERE user_id=? AND category=? ORDER BY created_at DESC LIMIT ?", (user_id, category, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM memory WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def add_dialog(self, user_id, role, content):
        with self.conn() as c:
            c.execute("INSERT INTO dialog (user_id,role,content) VALUES (?,?,?)", (user_id, role, content))
            c.execute("DELETE FROM dialog WHERE user_id=? AND id NOT IN (SELECT id FROM dialog WHERE user_id=? ORDER BY id DESC LIMIT 40)", (user_id, user_id))

    def get_dialog(self, user_id, limit=16) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT role,content FROM dialog WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def add_event(self, user_id, title, event_time, remind_at=None, prep_steps=None) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO events (user_id,title,event_time,remind_at,prep_steps) VALUES (?,?,?,?,?)",
                            (user_id, title, event_time, remind_at, json.dumps(prep_steps or [])))
            return cur.lastrowid

    def get_upcoming_events(self, user_id) -> list:
        with self.conn() as c:
            now = datetime.utcnow().isoformat()
            rows = c.execute("SELECT * FROM events WHERE user_id=? AND event_time>? AND is_deleted=0 ORDER BY event_time ASC", (user_id, now)).fetchall()
            return [dict(r) for r in rows]

    def get_event(self, event_id) -> Optional[dict]:
        with self.conn() as c:
            r = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(r) if r else None

    def delete_event(self, event_id):
        with self.conn() as c:
            c.execute("UPDATE events SET is_deleted=1 WHERE id=?", (event_id,))

    def get_events_to_remind(self, from_t, to_t) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM events WHERE remind_at BETWEEN ? AND ? AND reminded_main=0 AND is_deleted=0", (from_t, to_t)).fetchall()
            return [dict(r) for r in rows]

    def mark_reminded(self, event_id):
        with self.conn() as c:
            c.execute("UPDATE events SET reminded_main=1 WHERE id=?", (event_id,))

    def save_roadmap(self, user_id, dream, steps) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO roadmaps (user_id,dream,steps_json) VALUES (?,?,?)", (user_id, dream, json.dumps(steps, ensure_ascii=False)))
            return cur.lastrowid

    def get_roadmaps(self, user_id) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM roadmaps WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
            result = []
            for r in rows:
                d = dict(r); d["steps"] = json.loads(d["steps_json"]); result.append(d)
            return result

    def update_roadmap_step(self, roadmap_id, step_index, done):
        with self.conn() as c:
            r = c.execute("SELECT steps_json FROM roadmaps WHERE id=?", (roadmap_id,)).fetchone()
            if r:
                steps = json.loads(r["steps_json"])
                if 0 <= step_index < len(steps):
                    steps[step_index]["done"] = done
                    c.execute("UPDATE roadmaps SET steps_json=? WHERE id=?", (json.dumps(steps, ensure_ascii=False), roadmap_id))

    def save_file(self, user_id, filename, file_type, summary, full_text) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO files (user_id,filename,file_type,summary,full_text) VALUES (?,?,?,?,?)", (user_id, filename, file_type, summary, full_text))
            return cur.lastrowid

    def get_files(self, user_id) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT id,filename,file_type,summary,created_at FROM files WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_file_text(self, file_id) -> Optional[str]:
        with self.conn() as c:
            r = c.execute("SELECT full_text FROM files WHERE id=?", (file_id,)).fetchone()
            return r["full_text"] if r else None

    def get_settings(self, user_id) -> dict:
        with self.conn() as c:
            r = c.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
            if r: return dict(r)
            c.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
            return {"user_id": user_id, "timezone": "Asia/Yekaterinburg", "onboarded": 0}

    def set_timezone(self, user_id, tz):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO user_settings (user_id,timezone,onboarded) VALUES (?,?,1)", (user_id, tz))

    def set_onboarded(self, user_id):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO user_settings (user_id,onboarded) VALUES (?,1)", (user_id,))

    # ─── РАСХОДЫ ─────────────────────────────────────────────
    def add_expense(self, user_id, amount, category, description="", is_pp=0, is_healthy=1, shop="") -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO expenses (user_id,amount,category,description,is_pp,is_healthy,shop) VALUES (?,?,?,?,?,?,?)",
                            (user_id, amount, category, description, is_pp, is_healthy, shop))
            return cur.lastrowid

    def get_expenses(self, user_id, days=30) -> list:
        with self.conn() as c:
            from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            rows = c.execute("SELECT * FROM expenses WHERE user_id=? AND created_at>=? ORDER BY created_at DESC", (user_id, from_date)).fetchall()
            return [dict(r) for r in rows]

    def get_expenses_by_category(self, user_id, days=30) -> dict:
        by_cat = {}
        for e in self.get_expenses(user_id, days):
            by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]
        return by_cat

    def get_expenses_total(self, user_id, days=30) -> int:
        return sum(e["amount"] for e in self.get_expenses(user_id, days))

    def add_income(self, user_id, amount, source="", note="") -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO income (user_id,amount,source,note) VALUES (?,?,?,?)", (user_id, amount, source, note))
            return cur.lastrowid

    def get_income_total(self, user_id, days=30) -> int:
        with self.conn() as c:
            from_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            r = c.execute("SELECT SUM(amount) as total FROM income WHERE user_id=? AND created_at>=?", (user_id, from_date)).fetchone()
            return r["total"] or 0

    def set_budget_limit(self, user_id, category, limit):
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO budget_goals (user_id,category,monthly_limit) VALUES (?,?,?)", (user_id, category, limit))

    def get_budget_limits(self, user_id) -> dict:
        with self.conn() as c:
            rows = c.execute("SELECT category,monthly_limit FROM budget_goals WHERE user_id=?", (user_id,)).fetchall()
            return {r["category"]: r["monthly_limit"] for r in rows}

    # ─── НАКОПЛЕНИЯ ──────────────────────────────────────────
    def add_savings(self, user_id, amount, note="") -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO savings (user_id,amount,note) VALUES (?,?,?)", (user_id, amount, note))
            return cur.lastrowid

    def get_savings_total(self, user_id) -> int:
        with self.conn() as c:
            r = c.execute("SELECT SUM(amount) as total FROM savings WHERE user_id=?", (user_id,)).fetchone()
            return r["total"] or 0

    # ─── ПП ПРОДУКТЫ ─────────────────────────────────────────
    def get_pp_products(self, user_id) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM pp_products WHERE user_id=? ORDER BY category,name", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_pp_product(self, user_id, name, category="base", days_supply=7):
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO pp_products (user_id,name,category,days_supply) VALUES (?,?,?,?)", (user_id, name, category, days_supply))

    def update_product_bought(self, user_id, name):
        with self.conn() as c:
            c.execute("UPDATE pp_products SET last_bought=datetime('now') WHERE user_id=? AND LOWER(name) LIKE LOWER(?)", (user_id, f"%{name}%"))

    def get_missing_products(self, user_id) -> list:
        with self.conn() as c:
            rows = c.execute("""SELECT * FROM pp_products WHERE user_id=?
                AND (last_bought IS NULL OR julianday('now') - julianday(last_bought) >= days_supply)""", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_shopping_list(self, user_id) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM shopping_list WHERE user_id=? AND is_bought=0 ORDER BY added_at DESC", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_to_shopping(self, user_id, item, amount="", is_pp=1):
        with self.conn() as c:
            c.execute("INSERT INTO shopping_list (user_id,item,amount,is_pp) VALUES (?,?,?,?)", (user_id, item, amount, is_pp))

    def mark_bought(self, user_id, item):
        with self.conn() as c:
            c.execute("UPDATE shopping_list SET is_bought=1 WHERE user_id=? AND LOWER(item) LIKE LOWER(?)", (user_id, f"%{item}%"))

    def clear_shopping_list(self, user_id):
        with self.conn() as c:
            c.execute("UPDATE shopping_list SET is_bought=1 WHERE user_id=?", (user_id,))

    # ─── БЛОГ ────────────────────────────────────────────────
    def add_blog_stat(self, user_id, followers, platform="instagram"):
        with self.conn() as c:
            c.execute("INSERT INTO blog_stats (user_id,platform,followers) VALUES (?,?,?)", (user_id, platform, followers))

    def get_latest_followers(self, user_id) -> int:
        with self.conn() as c:
            r = c.execute("SELECT followers FROM blog_stats WHERE user_id=? ORDER BY recorded_at DESC LIMIT 1", (user_id,)).fetchone()
            return r["followers"] if r else 394

    def get_followers_history(self, user_id, limit=10) -> list:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM blog_stats WHERE user_id=? ORDER BY recorded_at DESC LIMIT ?", (user_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def add_content_item(self, user_id, title, format_type, theme, shoot_date, remind_at=None, prep_steps=None) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO content_plan (user_id,title,format,theme,shoot_date,remind_at,prep_steps) VALUES (?,?,?,?,?,?,?)",
                            (user_id, title, format_type, theme, shoot_date, remind_at, json.dumps(prep_steps or [])))
            return cur.lastrowid

    def get_content_plan(self, user_id, days_ahead=14) -> list:
        with self.conn() as c:
            now = datetime.utcnow().isoformat()
            future = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat()
            rows = c.execute("SELECT * FROM content_plan WHERE user_id=? AND shoot_date BETWEEN ? AND ? AND is_done=0 ORDER BY shoot_date ASC",
                             (user_id, now, future)).fetchall()
            return [dict(r) for r in rows]

    def mark_content_done(self, content_id):
        with self.conn() as c:
            c.execute("UPDATE content_plan SET is_done=1 WHERE id=?", (content_id,))

    def add_barter(self, user_id, brand, category, value_rub=0, status="wishlist", followers_needed=0, note="") -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO barter_deals (user_id,brand,category,value_rub,status,followers_needed,note) VALUES (?,?,?,?,?,?,?)",
                            (user_id, brand, category, value_rub, status, followers_needed, note))
            return cur.lastrowid

    def get_barters(self, user_id, status=None) -> list:
        with self.conn() as c:
            if status:
                rows = c.execute("SELECT * FROM barter_deals WHERE user_id=? AND status=? ORDER BY created_at DESC", (user_id, status)).fetchall()
            else:
                rows = c.execute("SELECT * FROM barter_deals WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_barter_saved_total(self, user_id) -> int:
        with self.conn() as c:
            r = c.execute("SELECT SUM(value_rub) as total FROM barter_deals WHERE user_id=? AND status='received'", (user_id,)).fetchone()
            return r["total"] or 0

    def update_barter_status(self, barter_id, status):
        with self.conn() as c:
            c.execute("UPDATE barter_deals SET status=? WHERE id=?", (status, barter_id))
