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

CANCEL_KEYBOARD = {
    'keyboard': [[{'text': 'Отмена'}]],
    'resize_keyboard': True,
    'one_time_keyboard': True,
}
REMOVE_KEYBOARD = {
    'remove_keyboard': True,
}


async def get_chat_info(session: aiohttp.ClientSession, chat_id: int) -> dict | None:
    """
    Получает информацию о чате по айди
    :param session: текущая сессия
    :param chat_id: айди чата
    :return: информация о чате
    """
    url = constants.URL + '/getChat'
    async with session.post(url, json={'chat_id': chat_id}) as resp:
        result = await resp.json(content_type=None)
        if not resp.ok:
            return None
        return result['result']


async def copy_message(session: aiohttp.ClientSession,
                       source_chat_id: int | str,
                       target_chat_id: int | str,
                       message_id: int) -> Any:
    """
    Пересылает сообщение из одного тг канала в другой
    :param session: текущая сессия
    :param source_chat_id: айди адресанта
    :param target_chat_id: айди адресата
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
                       msg: str,
                       reply_markup=None) -> Any:
    """
    Отправляет сообщение пользователю
    :param session: текущая сессия
    :param target_chat_id: айди адресата
    :param msg: сообщение, которое нужно переслать
    :param reply_markup:
    :return: информация о боте
    """
    url = constants.URL + '/sendMessage'
    data = {
        'chat_id': target_chat_id,
        'text': msg,
        'parse_mode': 'HTML',
    }

    if reply_markup is not None:
        data['reply_markup'] = reply_markup

    async with session.post(url, json=data) as resp:
        resp.raise_for_status()
        return await resp.json()


async def copy_messages(session: aiohttp.ClientSession,
                        source_chat_id: int | str,
                        target_chat_id: int | str,
                        message_ids: list[int]) -> Any:
    """
    Пересылает несколько сообщений из одного тг канала в другой
    :param session: текущая сессия
    :param source_chat_id: айди адресанта
    :param target_chat_id: айди адресата
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
                        source_chat_id,
                        target_chat_id,
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
                print(update)
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

                if msg == 'Отмена':
                    sqlogic.reset_waiting_states(source_chat_id)
                    await send_message(
                        session,
                        source_chat_id,
                        'Действие отменено',
                        REMOVE_KEYBOARD
                    )
                    continue

                if sqlogic.is_waiting_id_for_adding(source_chat_id):
                    ids = msg.split('\n')
                    correct_ids = []
                    for id in ids:
                        if not re.fullmatch(r'-?\d+', id):
                            await send_message(session, source_chat_id, f'Некорректный id: {id}')
                            continue

                        elif str(source_chat_id) == id:
                            await send_message(session, source_chat_id,
                                               f'id {id} совпадает с вашим')
                            continue
                        else:
                            chat = await get_chat_info(session, id)
                            if chat is None:
                                await send_message(session, source_chat_id, f'Бот не имеет доступа к чату {id}')
                                continue

                            chat_type = chat['type']
                            if chat_type == 'private':
                                await send_message(
                                    session,
                                    source_chat_id,
                                    f'{id} - личный чат\n'
                                    f'Нельзя добавлять личные чаты в список ресурсов'
                                )
                                continue
                            if chat_type in {'group', 'supergroup'}:
                                await send_message(
                                    session,
                                    source_chat_id,
                                    f'Для пересылки в выбранном чате отправьте команду\n'
                                    f'"/allow_forwarding_to {source_chat_id}"'
                                )
                                continue
                            if chat_type == 'channel':
                                if 'username' in chat:
                                    correct_ids.append(id)
                                    sqlogic.add_source_chat_id(id, source_chat_id)
                                    await send_message(
                                        session,
                                        source_chat_id,
                                        f'Чат {source_chat_id} добавлен в список ресурсов'
                                    )
                                else:
                                    await send_message(
                                        session,
                                        source_chat_id,
                                        f'Для пересылки в выбранном чате отправьте команду\n'
                                        f'"/allow_forwarding_to {source_chat_id}"'
                                    )
                                continue

                    added_ids = ', '.join(correct_ids)
                    sqlogic.set_waiting_id_for_adding(source_chat_id, False)
                    if added_ids:
                        await send_message(session, source_chat_id,
                                           f'id {added_ids} добавлены в список ресурсов',
                                           REMOVE_KEYBOARD)
                        continue

                if sqlogic.is_waiting_id_for_removing(source_chat_id):
                    ids = msg.split('\n')
                    correct_ids = []
                    for id in ids:
                        if not re.fullmatch(r'-?\d+', id):
                            await send_message(session, source_chat_id, f'Некорректный id: {id}')
                            continue

                        elif str(source_chat_id) == id:
                            await send_message(session, source_chat_id,
                                               f'id {id} совпадает с вашим')
                            continue
                        sqlogic.remove_source_chat_id(source_chat_id, id)
                        correct_ids.append(id)
                    added_ids = ', '.join(correct_ids)
                    if added_ids:
                        sqlogic.set_waiting_id_for_removing(source_chat_id, False)
                        await send_message(session, source_chat_id,
                                           f'id {added_ids} убраны из списка ресурсов',
                                           REMOVE_KEYBOARD)
                    else:
                        await send_message(session, source_chat_id,
                                           f'Не обнаружено корректных id. '
                                           'Попробуйте ещё раз')
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
                                            ', '.join(allowed_types)),
                                           REMOVE_KEYBOARD)
                        continue

                if msg.startswith('/allow_forwarding_to'):
                    parts = msg.split(maxsplit=1)
                    if len(parts) != 2:
                        await send_message(session, source_chat_id, 'Использование: /allow_forwarding_to <target_id>')
                        continue
                    target_chat_id = parts[1]

                    if not re.fullmatch(r'-?\d+', target_chat_id):
                        await send_message(session, source_chat_id, f'Некорректный id')
                        continue

                    elif str(source_chat_id) == target_chat_id:
                        await send_message(session, source_chat_id,
                                           f'id совпадает с вашим')
                        continue
                    else:
                        sqlogic.add_source_chat_id(target_chat_id, source_chat_id)
                        await send_message(session, source_chat_id,
                                           f'Вы разрешили боту пересылать '
                                           f'сообщения в чат {target_chat_id}')
                        await send_message(
                            session,
                            target_chat_id,
                            f'Чат {source_chat_id} добавлен в список ресурсов'
                        )
                        continue

                if msg == '/check_sources':
                    sources = sqlogic.get_source_chat_ids(source_chat_id)
                    await send_message(
                        session,
                        source_chat_id,
                        sources
                    )
                    continue

                if msg == '/add_source_ids':
                    await send_message(
                        session,
                        source_chat_id,
                        'Введите id ресурсов в одном сообщении\n'
                        'Каждый новый id с новой строчки',
                        CANCEL_KEYBOARD
                    )
                    sqlogic.set_waiting_id_for_adding(source_chat_id, True)
                    continue

                if msg == '/remove_source_ids':
                    await send_message(
                        session,
                        source_chat_id,
                        'Введите id чатов, которые надо убрать из списка ресурсов\n'
                        'Каждый новый id с новой строчки',
                        CANCEL_KEYBOARD
                    )
                    sqlogic.set_waiting_id_for_removing(source_chat_id, True)
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
                        'Выпишите каждый новый тип с новой строчки',
                        CANCEL_KEYBOARD
                    )
                    sqlogic.set_waiting_for_types(source_chat_id, True)
                    continue

                kind = detect_message_kind(post)
                if kind in {'paid_media', 'invoice', 'giveaway', 'giveaway_winners'}:
                    print(f"Skip unsupported kind={kind}, message_id={message_id}")
                    continue

                target_chat_ids = sqlogic.get_target_chat_ids(source_chat_id)
                for target in target_chat_ids:
                    target = int(target)
                    allowed_types = sqlogic.get_allowed_types(target)
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
                        else:
                            try:
                                await copy_message(
                                    session,
                                    source_chat_id,
                                    target,
                                    message_id,
                                )
                            except Exception as e:
                                print(f'Message copy failed for {message_id}: {e}')

            await flush_ready_media_groups(session)


if __name__ == '__main__':
    asyncio.run(main())
