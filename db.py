# db.py
import os
import time
import psycopg2
from psycopg2.extras import DictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is not set")

# اتصال به دیتابیس Supabase Postgres
conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
conn.autocommit = True  # برای MVP ساده


def init_db():
    """ساخت جدول‌ها اگر وجود نداشته باشن"""
    with conn.cursor() as cur:
        cur.execute("""
        create table if not exists users (
            id serial primary key,
            telegram_id bigint unique not null,
            username text,
            mew_points integer default 0,
            last_mew_ts bigint
        );
        """)

        cur.execute("""
        create table if not exists cats (
            id serial primary key,
            owner_id integer references users(id) on delete cascade,
            name text not null,
            rarity text not null,
            element text,
            trait text,
            description text,
            level integer default 1,
            xp integer default 0,
            hunger integer default 50,
            happiness integer default 50,
            created_at bigint,
            last_tick_ts bigint
        );
        """)

        cur.execute("""
        create table if not exists user_groups (
            id serial primary key,
            user_id integer references users(id) on delete cascade,
            chat_id bigint not null
        );
        """)

        # یونیک بودن ترکیب user + chat برای تکراری نشدن
        cur.execute("""
        do $$
        begin
            if not exists (
                select 1 from pg_indexes
                where schemaname = 'public'
                  and indexname = 'user_groups_user_chat_idx'
            ) then
                create unique index user_groups_user_chat_idx
                on user_groups(user_id, chat_id);
            end if;
        end
        $$;
        """)


def get_or_create_user(telegram_id, username):
    with conn.cursor() as cur:
        cur.execute(
            "select id, mew_points, last_mew_ts from users where telegram_id = %s;",
            (telegram_id,),
        )
        row = cur.fetchone()
        if row:
            return row["id"]

        cur.execute(
            "insert into users(telegram_id, username, mew_points, last_mew_ts) "
            "values(%s,%s,0,null) returning id;",
            (telegram_id, username),
        )
        user_id = cur.fetchone()["id"]
        return user_id


def get_user(telegram_id):
    with conn.cursor() as cur:
        cur.execute(
            "select id, telegram_id, username, mew_points, last_mew_ts "
            "from users where telegram_id = %s;",
            (telegram_id,),
        )
        return cur.fetchone()


def update_user_mew(telegram_id, mew_points, last_mew_ts):
    with conn.cursor() as cur:
        cur.execute(
            "update users set mew_points = %s, last_mew_ts = %s "
            "where telegram_id = %s;",
            (mew_points, last_mew_ts, telegram_id),
        )


def register_user_group(user_id, chat_id):
    """ثبت این که این یوزر تو این گروه فعّال بوده (برای لیدربورد گروهی)"""
    with conn.cursor() as cur:
        cur.execute("""
            insert into user_groups(user_id, chat_id)
            values (%s, %s)
            on conflict (user_id, chat_id) do nothing;
        """, (user_id, chat_id))


def get_group_users(chat_id):
    """لیست یوزرهای این گروه با mew_points"""
    with conn.cursor() as cur:
        cur.execute("""
            select u.id, u.telegram_id, u.username, u.mew_points
            from users u
            join user_groups g on g.user_id = u.id
            where g.chat_id = %s;
        """, (chat_id,))
        return cur.fetchall()


def get_all_users():
    with conn.cursor() as cur:
        cur.execute("""
            select id, telegram_id, username, mew_points
            from users;
        """)
        return cur.fetchall()


def get_user_cats(user_id):
    with conn.cursor() as cur:
        cur.execute("""
            select id, owner_id, name, rarity, element, trait, description,
                   level, xp, hunger, happiness, created_at, last_tick_ts
            from cats
            where owner_id = %s
            order by id desc;
        """, (user_id,))
        return cur.fetchall()


def add_cat(owner_id, name, rarity, element, trait, description):
    now = int(time.time())
    with conn.cursor() as cur:
        cur.execute("""
            insert into cats(owner_id, name, rarity, element, trait, description,
                             level, xp, hunger, happiness, created_at, last_tick_ts)
            values(%s,%s,%s,%s,%s,%s,
                   1, 0, 60, 60, %s, %s)
            returning id;
        """, (owner_id, name, rarity, element, trait, description, now, now))
        row = cur.fetchone()
        return row["id"]


def get_cat(cat_id, owner_id):
    with conn.cursor() as cur:
        cur.execute("""
            select id, owner_id, name, rarity, element, trait, description,
                   level, xp, hunger, happiness, created_at, last_tick_ts
            from cats
            where id = %s and owner_id = %s;
        """, (cat_id, owner_id))
        return cur.fetchone()


def update_cat_stats(cat_id, owner_id, hunger, happiness, xp, level, last_tick_ts):
    with conn.cursor() as cur:
        cur.execute("""
            update cats
            set hunger = %s,
                happiness = %s,
                xp = %s,
                level = %s,
                last_tick_ts = %s
            where id = %s and owner_id = %s;
        """, (hunger, happiness, xp, level, last_tick_ts, cat_id, owner_id))
