import json
import sqlite3

DB_PATH = 'bot_settings.db'
DEFAULT_ALLOWED_TYPES = [
    'photo',
    'video',
    'document',
    'animation',
    'audio',
    'voice',
    'video_note',
    'sticker',
    'poll',
    'text',
]
DEFAULT_ALLOWED_TYPES_JSON = json.dumps(DEFAULT_ALLOWED_TYPES)


def init_db() -> None:
    """
    Инициализирует БД со всеми пользователями
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f'''
            CREATE TABLE IF NOT EXISTS chat_settings (
                source_chat_id INTEGER PRIMARY KEY,
                allowed_types TEXT DEFAULT '{DEFAULT_ALLOWED_TYPES_JSON}',
                waiting_id_for_adding INTEGER NOT NULL DEFAULT 0,
                waiting_id_for_removing INTEGER NOT NULL DEFAULT 0,
                waiting_id_for_remote INTEGER NOT NULL DEFAULT 0,
                waiting_for_types INTEGER NOT NULL DEFAULT 0
            );
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS routes (
                source_chat_id INTEGER NOT NULL,
                target_chat_id TEXT NOT NULL,
                PRIMARY KEY (source_chat_id, target_chat_id)
            );
            '''
        )

        columns = {
            row[1]
            for row in conn.execute('PRAGMA table_info(chat_settings)')
        }

        if 'allowed_types' not in columns:
            conn.execute('ALTER TABLE chat_settings ADD COLUMN allowed_types TEXT')

        if 'waiting_for_types' not in columns:
            conn.execute(
                'ALTER TABLE chat_settings ADD COLUMN waiting_for_types INTEGER NOT NULL DEFAULT 0'
            )


def set_waiting_id_for_adding(source_chat_id: int, value: bool) -> None:
    """
    Устанавливает параметр waiting_id_for_adding
    :param source_chat_id: id пользователя
    :param value: значение параметра
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chat_settings (source_chat_id, waiting_id_for_adding)
            VALUES (?, ?)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                waiting_id_for_adding = excluded.waiting_id_for_adding
            ''',
            (source_chat_id, int(value))
        )


def set_waiting_id_for_removing(source_chat_id: int, value: bool) -> None:
    """
    Устанавливает параметр waiting_id_for_removing
    :param source_chat_id: id пользователя
    :param value: значение параметра
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chat_settings (source_chat_id, waiting_id_for_removing)
            VALUES (?, ?)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                waiting_id_for_removing = excluded.waiting_id_for_removing
            ''',
            (source_chat_id, int(value))
        )


def set_waiting_id_for_remote(source_chat_id: int, value: bool) -> None:
    """
    Устанавливает параметр waiting_id_for_remote
    :param source_chat_id: id пользователя
    :param value: значение параметра
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chat_settings (source_chat_id, waiting_id_for_remote)
            VALUES (?, ?)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                waiting_id_for_remote = excluded.waiting_id_for_remote
            ''',
            (source_chat_id, int(value))
        )


def set_waiting_for_types(source_chat_id: int, value: bool) -> None:
    """
    Устанавливает параметр waiting_for_types
    :param source_chat_id: id пользователя
    :param value: значение параметра
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chat_settings (source_chat_id, waiting_for_types)
            VALUES (?, ?)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                waiting_for_types = excluded.waiting_for_types
            ''',
            (source_chat_id, int(value))
        )


def set_allowed_types(source_chat_id: int, allowed_types: list) -> None:
    """
    Устанавливает параметр allowed_types
    :param source_chat_id: id пользователя
    :param allowed_types: разрешённые для пересылки типы сообщений
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT INTO chat_settings (
                source_chat_id,
                allowed_types,
                waiting_for_types
            )
            VALUES (?, ?, 0)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                allowed_types = excluded.allowed_types,
                waiting_for_types = 0
            ''',
            (source_chat_id, json.dumps(allowed_types, ensure_ascii=False))
        )


def add_target_chat_id(source_chat_id: int, target_chat_id: str) -> None:
    """
    Добавляет новый target_chat_id в список адресатов
    :param source_chat_id: id пользователя
    :param target_chat_id: id адресата
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            '''
            INSERT OR IGNORE INTO routes (
                source_chat_id,
                target_chat_id
            )
            VALUES (?, ?)
            ''',
            (source_chat_id, target_chat_id)
        )

        conn.execute(
            '''
            INSERT INTO chat_settings (
                source_chat_id,
                waiting_id_for_adding
            )
            VALUES (?, 0)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                waiting_id_for_adding = 0
            ''',
            (source_chat_id,)
        )


def remove_target_chat_id(source_chat_id: int, target_chat_id: str) -> bool:
    """
    Убирает чат из адресатов
    :param source_chat_id: пользователь
    :param target_chat_id: id чата, который надо убрать из списка адресатов
    :return:
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            '''
            DELETE FROM routes
            WHERE source_chat_id = ?
              AND target_chat_id = ?
            ''',
            (source_chat_id, target_chat_id)
        )

        conn.execute(
            '''
            INSERT INTO chat_settings (
                source_chat_id,
                waiting_id_for_removing
            )
            VALUES (?, 0)
            ON CONFLICT(source_chat_id) DO UPDATE SET
                waiting_id_for_removing = 0
            ''',
            (source_chat_id,)
        )

    return cursor.rowcount > 0


def is_waiting_id_for_adding(source_chat_id: int) -> bool:
    """
    Проверяет истинность параметра waiting_id_for_adding у выбранного пользователя
    :param source_chat_id: выбранный пользователь
    :return: значение параметра waiting_id_for_adding
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            '''
            SELECT waiting_id_for_adding
            FROM chat_settings
            WHERE source_chat_id = ?
            ''',
            (source_chat_id,)
        ).fetchone()

    return row is not None and bool(row[0])


def is_waiting_id_for_removing(source_chat_id: int) -> bool:
    """
    Проверяет истинность параметра waiting_id_for_removing у выбранного пользователя
    :param source_chat_id: выбранный пользователь
    :return: значение параметра waiting_id_for_removing
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            '''
            SELECT waiting_id_for_removing
            FROM chat_settings
            WHERE source_chat_id = ?
            ''',
            (source_chat_id,)
        ).fetchone()

    return row is not None and bool(row[0])


def is_waiting_id_for_remote(source_chat_id: int) -> bool:
    """
    Проверяет истинность параметра waiting_id_for_remote у выбранного пользователя
    :param source_chat_id: выбранный пользователь
    :return: значение параметра waiting_id_for_remote
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            '''
            SELECT waiting_id_for_remote
            FROM chat_settings
            WHERE source_chat_id = ?
            ''',
            (source_chat_id,)
        ).fetchone()

    return row is not None and bool(row[0])


def is_waiting_for_types(source_chat_id: int) -> bool:
    """
    Проверяет истинность параметра waiting_for_types у выбранного пользователя
    :param source_chat_id: выбранный пользователь
    :return: значение параметра waiting_for_types
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            '''
            SELECT waiting_for_types
            FROM chat_settings
            WHERE source_chat_id = ?
            ''',
            (source_chat_id,)
        ).fetchone()

    return row is not None and bool(row[0])


def get_target_chat_ids(source_chat_id: int) -> list[str]:
    """
    Достаёт параметр target_chat_ids
    :param source_chat_id: id пользователя
    :return: соответствующие target_chat_ids
    """
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            '''
            SELECT target_chat_id
            FROM routes
            WHERE source_chat_id = ?
            ''',
            (source_chat_id,)
        ).fetchall()

    return [row[0] for row in rows]


def get_allowed_types(source_chat_id: int) -> list[str]:
    """
    Достаёт параметр allowed_types
    :param source_chat_id: id пользователя
    :return: соответствующий allowed_types
    """
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            '''
            SELECT allowed_types
            FROM chat_settings
            WHERE source_chat_id = ?
            ''',
            (source_chat_id,)
        ).fetchone()

    if row is None or row[0] is None:
        return DEFAULT_ALLOWED_TYPES

    return json.loads(row[0])
