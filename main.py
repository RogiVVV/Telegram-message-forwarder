import asyncio
import re
import aiohttp
from typing import Any
import time

import constants
import sqlogic

media_groups = {}
MSG_TYPES = ['photo', 'video', 'document', 'animation', 'audio',
             'voice', 'video_note', 'sticker', 'poll', 'text']


async def copy_message(session: aiohttp.ClientSession,
                       target_chat_id: int | str,
                       source_chat_id: int | str,
                       message_id: int) -> Any:
    """
    Пересылает сообщение из одного тг канала в другой
    :param session: текущая сессия
    :param target_chat_id: айди адресата
    :param source_chat_id: айди адресанта
    :param message_id: айди сообщения, которое нужно переслать
    :return: информация о боте
    """
    url = constants.URL + '/copyMessage'
    data = {
        'chat_id': target_chat_id,
        'from_chat_id': source_chat_id,
        'message_id': message_id,
    }
    async with session.post(url, data=data) as resp:
        resp.raise_for_status()
        return await resp.json()


async def send_message(session: aiohttp.ClientSession,
                       target_chat_id: int | str,
                       msg: str) -> Any:
    """
    Отправляет сообщение пользователю
    :param session: текущая сессия
    :param target_chat_id: айди адресата
    :param msg: сообщение, которое нужно переслать
    :return: информация о боте
    """
    url = constants.URL + '/sendMessage'
    data = {
        'chat_id': target_chat_id,
        'text': msg,
        'parse_mode': 'HTML',
    }
    async with session.post(url, data=data) as resp:
        resp.raise_for_status()
        return await resp.json()


async def copy_messages(session: aiohttp.ClientSession,
                        target_chat_id: int | str,
                        source_chat_id: int | str,
                        message_ids: list[int]) -> Any:
    """
    Пересылает несколько сообщений из одного тг канала в другой
    :param session: текущая сессия
    :param target_chat_id: айди адресата
    :param source_chat_id: айди адресанта
    :param message_ids: список айди сообщений, которые нужно переслать
    :return: информация о боте
    """
    url = constants.URL + '/copyMessages'
    data = {
        'chat_id': target_chat_id,
        'from_chat_id': source_chat_id,
        'message_ids': sorted(message_ids),
    }
    async with session.post(url, json=data) as resp:
        result = await resp.json(content_type=None)
        if not resp.ok:
            raise RuntimeError(f'copyMessages error: {result}')
        return result


async def get_updates(session: aiohttp.ClientSession,
                      offset: int | None = None,
                      timeout: int = -1) -> Any:
    """
    Получает все сообщения, которые были отправлены боту, начиная с
    сообщения с айди offset (если offset is None - все
    сообщения за последние 24 часа)
    :param session: текущая сессия
    :param offset: айди апдейта, начиная с которого нужно выводить
    все остальные (по умолчанию None)
    :param timeout: время ожидания ответа от сервера
    :return: все апдейты
    """
    url = constants.URL + '/getUpdates'
    params = {'timeout': timeout}
    if offset is not None:
        params['offset'] = offset

    async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        result = await resp.json(content_type=None)
        if not resp.ok:
            raise RuntimeError(f'getUpdates error: {result}')
        return result


def detect_message_kind(post: dict) -> str:
    """
    Определяет тип поста
    :param post: информация о посте
    :return: тип поста
    """
    if 'paid_media' in post:
        return 'paid_media'
    if 'photo' in post:
        return 'photo'
    if 'video' in post:
        return 'video'
    if 'document' in post:
        return 'document'
    if 'animation' in post:
        return 'animation'
    if 'audio' in post:
        return 'audio'
    if 'voice' in post:
        return 'voice'
    if 'video_note' in post:
        return 'video_note'
    if 'sticker' in post:
        return 'sticker'
    if 'poll' in post:
        return 'poll'
    if 'invoice' in post:
        return 'invoice'
    if 'giveaway' in post:
        return 'giveaway'
    if 'giveaway_winners' in post:
        return 'giveaway_winners'
    if 'text' in post:
        return 'text'
    return 'unknown'


async def flush_ready_media_groups(session: aiohttp.ClientSession) -> None:
    """
    Отправляет готовые паки медиа
    :param session: текущая сессия
    """
    now = time.time()
    to_delete = []

    for group_id, group in media_groups.items():
        if (
                now - group['last_update'] > constants.MEDIA_GROUP_TIMEOUT
                or len(group['messages']) >= 10
        ):
            source_chat_id = group['chat_id']
            target_chat_ids = sqlogic.get_target_chat_ids(source_chat_id)

            if not target_chat_ids:
                to_delete.append(group_id)
                continue

            for target_chat_id in target_chat_ids:
                try:
                    await copy_messages(
                        session,
                        target_chat_id,
                        source_chat_id,
                        sorted(group['messages']),
                    )
                except Exception as e:
                    print(f'Album copy failed for {group_id}: {e}')

            to_delete.append(group_id)

    for group_id in to_delete:
        del media_groups[group_id]


async def main() -> None:
    """
    Основная логика бота
    """
    sqlogic.init_db()
    offset = None

    async with aiohttp.ClientSession() as session:
        while True:
            updates = await get_updates(session, offset)

            for update in updates['result']:
                offset = update['update_id'] + 1

                if 'channel_post' in update:
                    post = update['channel_post']
                elif 'message' in update:
                    post = update['message']
                else:
                    continue
                source_chat_id = post['chat']['id']
                message_id = post['message_id']
                msg = post.get('text', '')

                if sqlogic.is_waiting_id_for_adding(source_chat_id):
                    if not re.fullmatch(r'-?\d+', msg):
                        await send_message(session, source_chat_id, 'Некорректный id')
                        continue

                    elif str(source_chat_id) == msg:
                        await send_message(session, source_chat_id,
                                           'id совпадает с вашим')
                        continue

                    sqlogic.add_target_chat_id(source_chat_id, msg)
                    await send_message(session, source_chat_id, 'id добавлен в список адресатов')
                    continue

                if sqlogic.is_waiting_id_for_removing(source_chat_id):
                    if not re.fullmatch(r'-?\d+', msg):
                        await send_message(session, source_chat_id, 'Некорректный id')
                        continue

                    elif str(source_chat_id) == msg:
                        await send_message(session, source_chat_id,
                                           'id совпадает с вашим')
                        continue

                    sqlogic.remove_target_chat_id(source_chat_id, msg)
                    await send_message(session, source_chat_id, 'id убран из списка адресатов')
                    continue

                if sqlogic.is_waiting_id_for_remote(source_chat_id):
                    source_and_targets = msg.split('\n')
                    source = source_and_targets[0]
                    for target in source_and_targets[1:]:
                        if not re.fullmatch(r'-?\d+', target):
                            await send_message(session, source_chat_id,
                                               f'Некорректный id: {target}')
                            continue

                        elif str(source) == target:
                            await send_message(session, source_chat_id,
                                               f'id совпадает с вашим: {target}')
                            continue
                        sqlogic.add_target_chat_id(source, target)
                    await send_message(session, source_chat_id,
                                       f'Все корректные id добавлены в список адресатов')
                    sqlogic.set_waiting_id_for_remote(source_chat_id, False)
                    continue

                if sqlogic.is_waiting_for_types(source_chat_id):
                    selected_types = msg.split('\n')
                    allowed_types = []
                    for elem in selected_types:
                        elem = elem.lower()
                        if elem in MSG_TYPES:
                            allowed_types.append(elem)
                        else:
                            await send_message(session, source_chat_id,
                                               f'Типа {elem} не существует, возможно, это опечатка')
                    if not allowed_types:
                        await send_message(session, source_chat_id,
                                           'Не обнаружено корректных типов сообщений. '
                                           'Попробуйте ещё раз')
                        continue
                    else:
                        sqlogic.set_allowed_types(source_chat_id, allowed_types)
                        sqlogic.set_waiting_for_types(source_chat_id, False)
                        await send_message(session, source_chat_id,
                                           ('Выбранные типы сообщений: ' +
                                            ', '.join(allowed_types)))
                        continue

                if msg == '/add_target_id':
                    await send_message(
                        session,
                        source_chat_id,
                        'Введите id чата, в который бот будет пересылать сообщения'
                    )
                    sqlogic.set_waiting_id_for_adding(source_chat_id, True)
                    continue

                if msg == '/remove_target_id':
                    await send_message(
                        session,
                        source_chat_id,
                        'Введите id чата, который надо убрать из списка адресатов'
                    )
                    sqlogic.set_waiting_id_for_removing(source_chat_id, True)
                    continue

                if msg == '/set_source_target_ids':
                    await send_message(
                        session,
                        source_chat_id,
                        'Введите id адресанта и id всех адресатов\n'
                        'Каждый id c новой строки'
                    )
                    sqlogic.set_waiting_id_for_remote(source_chat_id, True)
                    continue

                if msg == '/set_allowed_types':
                    await send_message(
                        session,
                        source_chat_id,

                        'Выберите типы сообщений, которые будут пересылаться ботом:\n'
                        'photo - фото 🖼\n'
                        'video - видео 📹\n'
                        'document - документы - 📁\n'
                        'animation - GIF\n'
                        'audio - музыка, аудио 🎧\n'
                        'voice - голосовые сообщения 🗣\n'
                        'video_note - видеосообщения\n'
                        'sticker - стикеры\n'
                        'poll - опросы 📊\n'
                        'text - текстовые сообщения 💬\n'
                        'Выпишите каждый новый тип с новой строчки'
                    )
                    sqlogic.set_waiting_for_types(source_chat_id, True)
                    continue

                kind = detect_message_kind(post)
                allowed_types = sqlogic.get_allowed_types(source_chat_id)
                if kind in {'paid_media', 'invoice', 'giveaway', 'giveaway_winners'}:
                    print(f"Skip unsupported kind={kind}, message_id={message_id}")
                    continue
                if kind in allowed_types:
                    if 'media_group_id' in post:
                        group_id = (post['media_group_id'], source_chat_id)
                        if group_id not in media_groups:
                            media_groups[group_id] = {
                                'messages': [],
                                'last_update': time.time(),
                                'chat_id': source_chat_id}
                        media_groups[group_id]['messages'].append(message_id)
                        media_groups[group_id]['last_update'] = time.time()

                    elif not sqlogic.get_target_chat_ids(source_chat_id):
                        await send_message(session, source_chat_id,
                                           'Не выбран чат для пересылки\n'
                                           'Установите чат для пересылки командой /set_target_id')

                    else:
                        target_chat_ids = sqlogic.get_target_chat_ids(source_chat_id)

                        if not target_chat_ids:
                            continue

                        for target_chat_id in target_chat_ids:
                            try:
                                await copy_message(
                                    session,
                                    target_chat_id,
                                    source_chat_id,
                                    message_id,
                                )
                            except Exception as e:
                                print(f'Message copy failed for {message_id}: {e}')

            await flush_ready_media_groups(session)


if __name__ == '__main__':
    asyncio.run(main())
