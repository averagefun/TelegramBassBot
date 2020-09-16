import json
import random
import time

import pay
import requests
import boto3
import mysql.connector


# Get cred
def get_cred():
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('CredTableTBot')
    items = table.scan()['Items']
    keys = [item['cred_name'] for item in items]
    values = [item['cred_value'] for item in items]
    cred = dict(zip(keys, values))
    return cred


cred = get_cred()

# convert to int some values
cred['maxsize'] = int(cred['maxsize'])
# main admin - creator
creator = {'id': int(cred['creator_id']), 'username': cred['creator_username']}

# TelegramBot
Token = cred['bot_token']
URL = "https://api.telegram.org/bot{}/".format(Token)

# Используемые типы
tags = {'audio', 'voice', 'video_note', 'video'}
formats = ('mpeg', 'mp3', 'mp4', 'ogg')

# все используемые клавиатуры
products = {"inline_keyboard": [[{"text": "Купить premium (24 часа)", 'callback_data': 'premium_day'}],
                                [{"text": "Купить premium (7 дней)", 'callback_data': 'premium_week'}],
                                [{"text": "Купить premium (30 дней)", 'callback_data': 'premium_month'}]]}
pay_inline_markup = {"inline_keyboard": [[{"text": "Перейти к оплате", 'callback_data': 'pay'}]]}
pay_check_inline_markup = {"inline_keyboard": [[{"text": "Проверить оплату", 'callback_data': 'check_payment'}],
                                               [{"text": "Проблемы с оплатой!", 'callback_data': 'error_payment'}],
                                               [{"text": "Удалить платёжную сессию!",
                                                 'callback_data': 'delete_payment'}]]}
if_edit_markup = {'keyboard': [['Редактировать файл'], ['Пропустить редактирование']], 'resize_keyboard': True}
cut_markup = {'keyboard': [['Обрезать не нужно']], 'resize_keyboard': True}
startbass_markup = {'keyboard': [['По умолчанию (с самого начала)']], 'resize_keyboard': True}
level = ["🔈Bass Low", "🔉Bass High", "🔊Bass ULTRA", "📣Earrape Low", "📢Earrape High️", "‼️Earrape ULTRA"]
bass_markup = {'keyboard': [[level[0], level[3]], [level[1], level[4]], [level[2], level[5]]],
               'one_time_keyboard': True,
               'resize_keyboard': True}
file_markup = {'keyboard': [['Отправьте файл боту!🎧']], 'resize_keyboard': True}


class User:
    def __init__(self, event):
        self.event = event

        # проверка что это сообщение от пользователя, а не мусор
        try:
            self.id = self.event['message']['chat']['id']
        except KeyError:
            self.init_success = False
            return

        # проверка на наличие username
        try:
            self.username = self.event['message']['chat']['username']
        except KeyError:
            send_message(self.id, "Пожалуйста, установите ненулевой @username в настройках Telegram!")
            send_message(self.id,
                "После этого наберите /start если вы зашли к боту в первый раз, иначе повторите последнюю команду!")
            self.init_success = False
            return

        self.init_success = True

        mycursor.execute('SELECT * FROM users WHERE id = %s', (self.id,))
        self.user_info = mycursor.fetchone()

        # init new user
        if not self.user_info:
            self.role, self.balance, self.status, self.total = self.new_user()[2:6]
        else:
            self.balance, self.status, self.total = self.user_info[5:8]

            # проверяем на изменённый ник
            if self.username != self.user_info[2]:
                mycursor.execute("UPDATE users SET username = %s WHERE id = %s", (self.username, self.id))
                mydb.commit()

            # проверяем, закончилась ли роль
            mycursor.execute("SELECT EXISTS(SELECT id FROM users WHERE id = %s and (NOW() + INTERVAL 3 HOUR) >= role_end)",
                             (self.id, ))
            # закончилась
            if mycursor.fetchone()[0]:
                send_message(self.id, "<b>Внимание:</b> У вас закончилась подписка на premium!")
                mycursor.execute("UPDATE users SET role_ = 'standard', role_end = NULL WHERE id = %s", (self.id, ))
                mydb.commit()
                self.role = 'standard'
            else:
                self.role = self.user_info[4]

        '''  SQL
                status_:
                    start : начальное приветствие,
                    wait_file: бот ожидает файл,
                    wait_cut: бот ожидает ввод обрезки файла,
                    wait_bass_start: бот ожидает ввода начала басса,
                    wait_bass_level: бот ожидает ввод уровня басса,
                    req_sent: запрос отправлен, ожидание получения файла от BassBoost
                '''

        # get max_sec and role_active
        mycursor.execute("SELECT max_sec, role_active FROM roles WHERE name = %s", (self.role,))
        self.max_sec, self.role_active = mycursor.fetchone()

    def new_user(self):
        user_info = [self.id, self.username, "start", 0, "start", 0]
        # init admins
        if self.id == creator['id']:
            user_info[2] = 'admin'
            send_message(self.id, 'Привет, Создатель!')
        mycursor.execute(
            f'''INSERT INTO users (id, username, reg_date, role_, balance, status_, total) VALUES
                (%s, %s, NOW() + INTERVAL 3 HOUR, %s, %s, %s, %s)''', user_info)
        mydb.commit()
        return user_info

    def start_msg(self):
        send_sticker(self.id, 'start')
        start_param = {'username': self.username}
        tag = 'start' if self.role_active else 'start_debug'
        text = get_text_from_db(tag, start_param)
        send_message(self.id, text, file_markup)
        if self.role_active:
            mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id,))
            mydb.commit()
        else:
            # проверка на реферальную ссылку при старте с дебагом
            try:
                text = self.event['message']['text'].split()
            except KeyError:
                pass
            if text[0] == '/start' and len(text) == 2 and text[1].isdigit() and self.status == 'start':
                ref_user_id = int(text[1])
                mycursor.execute("SELECT EXISTS(SELECT id FROM users WHERE id = %s)", (ref_user_id, ))
                res = mycursor.fetchone()
                if res:
                    mycursor.execute("INSERT INTO referral VALUES (%s, %s, %s)", (ref_user_id, self.id, 0))
                    mydb.commit()

    def commands(self):
        # команды по ролям
        commands_list = {'standard': ['/start', '/help', '/stats', '/cancel', '/pay', '/buy', '/commands'],
                         'premium': [],
                         'admin': ['/active', '/users', '/message', '/ban', '/unban', '/text', '/price', '/update']}
        # команды по оплате
        pays_command = ['/pay', '/buy']
        row_text = self.text.split('\n')
        text = row_text[0].split()
        command = text[0]

        if self.role == 'admin':
            # если admin - делим всё сообщение на 2 аргумента!
            if len(text) == 1:
                arg, arg2 = None, None
            elif len(text) == 2:
                arg = text[1]
                if len(row_text) == 1:
                    arg2 = None
                else:
                    arg2 = '\n'.join(row_text[1:])

            else:
                send_message(self.id, 'Введите второй аргумент с новой строки!')
                return
        else:
            # если обычный пользователь - то только 1 аргумент
            arg = ' '.join(self.text.split()[1:])
            arg2 = None

        # standard
        if command not in commands_list['standard'] and self.role in ('start', 'standard'):
            send_message(self.id, 'Такой команды не существует или она не доступна вам!')
            return

        # начальное сообщение-приветствие
        if command == '/start':
            if self.status == 'start' or self.role in ('admin', 'block_by_user'):
                # проверка на реферальную ссылку
                if arg and arg.isdigit() and self.status == 'start':
                    ref_user_id = int(arg)
                    mycursor.execute("SELECT EXISTS(SELECT id FROM users WHERE id = %s)", (ref_user_id, ))
                    res = mycursor.fetchone()
                    if res:
                        mycursor.execute("INSERT INTO referral VALUES (%s, %s, %s)", (ref_user_id, self.id, 0))
                        mydb.commit()

                # восстановление роли standard после блокировки
                if self.role == 'block_by_user':
                    mycursor.execute("UPDATE users SET role_ = 'standard' WHERE id = %s", (self.id, ))
                    mydb.commit()
                    mycursor.execute("UPDATE referral SET invited_active = 1 WHERE invited_id = %s", (self.id, ))
                    self.role = 'standard'

                self.start_msg()
            else:
                send_message(self.id, "Бот уже запущен и ожидает\nфайл/сообщение!\n(/help - помощь по боту)")
            return

        # удаление запроса
        elif command == '/cancel':
            mycursor.execute('DELETE FROM bass_requests WHERE id = %s', (self.id,))
            mydb.commit()
            mycursor.execute('UPDATE users SET status_ = "wait_file" WHERE id = %s', (self.id,))
            mydb.commit()
            send_message(self.id, '<b>Запрос отменён!</b> \n<i>Загрузите файл для нового запроса.</i>',
                         file_markup)
            return

        elif command == '/help':
            text = get_text_from_db('help')
            text += '\n\n'
            mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = 'ref_bonus'")
            text += get_text_from_db('referral', {'id': self.id, 'ref_bonus': mycursor.fetchone()[0]})
            send_message(self.id, text)
            return

        # Оплата
        elif command in pays_command:
            # получаем цены на товары и курс секунд сейчас
            mycursor.execute("SELECT * FROM payment_param")
            params = mycursor.fetchall()
            keys = [param[0] for param in params]
            values = [param[1] for param in params]
            p = dict(zip(keys, values))

            # получаем параметры по ролям
            mycursor.execute("SELECT * FROM roles")
            roles = mycursor.fetchall()
            keys = [role[0] for role in roles]
            values = [role[1] for role in roles]  # max_sec
            r = dict(zip(keys, values))

            param_prod = {'premium_day': p['premium_day'], 'premium_week': p['premium_week'],
                          'premium_month': p['premium_month'], 'max_sec_premium': r['premium'],
                          'max_sec_standard': r['standard']}

            if command == '/pay':
                text = get_text_from_db('pay_system')
                text += '\n\n'
                text += get_text_from_db('products', param_prod)
                send_message(self.id, text, pay_inline_markup)
                return

            elif command == '/buy':
                text = get_text_from_db('products', param_prod)
                send_message(self.id, text, products)
                return

        elif command == '/stats':
            if self.user_info[-1]:
                role_end = f"Действует до: {self.user_info[-1]} по МСК"
            else:
                role_end = ""

            mycursor.execute("SELECT COUNT(*) FROM referral WHERE user_id = %s and invited_active = 1",
                                                                                            (self.id, ))
            ref_count = mycursor.fetchone()[0]
            param = {'balance': self.balance, 'role': self.role, 'role_end': role_end,
                     'max_sec': self.max_sec, 'total': self.total, 'ref_count': ref_count}
            text = get_text_from_db('stats', param)
            send_message(self.id, text)
            return

        elif command == '/commands':
            role = self.role.replace('start', 'standard')
            text = 'Доступные команды:\n'
            for item in commands_list.items():
                text += ', '.join(item[1]) + '| '
                if item[0] == role:
                    break
            send_message(self.id, text)
            return

        # premium
        if command not in commands_list['premium'] and self.role == 'premium':
            send_message(self.id, 'Такой команды не существует или она не доступна вам!')
            return

        # admin
        if command not in commands_list['admin'] and self.role == 'admin':
            send_message(self.id, 'Такой команды не существует!')
            return

        # активирование ролей
        elif command == '/active':
            mycursor.execute("SELECT name, role_active FROM roles")
            roles = mycursor.fetchall()
            keys = [role[0] for role in roles]
            values = [role[1] for role in roles]
            roles = dict(zip(keys, values))
            if arg and (arg in keys):
                if arg2:
                    if not arg2.isdigit():
                        send_message(self.id, 'Неверный аргумент (укажите 0 или 1)')
                        return
                    mycursor.execute("UPDATE roles SET role_active = %s WHERE name = %s",
                                     (int(arg2), arg))
                    mydb.commit()
                    send_message(self.id, f'Активность роли {arg} установлена в {arg2}')
                else:
                    send_message(self.id, roles[arg])
            elif arg:
                if not arg.isdigit():
                    send_message(self.id, 'Неверный аргумент (укажите 0 или 1)')
                    return
                mycursor.execute("UPDATE roles SET role_active = %s WHERE name != 'admin'",
                                 (int(arg),))
                mydb.commit()
                send_message(self.id, f'Активность всех пользователей = {arg}')
            else:
                send_message(self.id, f"Активность: {roles}")

        # статистика по пользователям
        elif command == '/users':
            param = {'show': 'username', 'count': 'count(*)'}
            if arg in param:
                req = f"SELECT {param[arg]} FROM users"
                if arg2 == 'all_active':
                    req += " WHERE last_query IS NOT NULL AND role_ != 'block_by_user'"
                elif arg2 == 'today':
                    req += " WHERE DATE(reg_date) = DATE(NOW() + INTERVAL 3 HOUR)"
                elif arg2 == 'today_active':
                    req += " WHERE DATE(reg_date) = DATE(NOW() + INTERVAL 3 HOUR) AND last_query IS NOT NULL AND role_ != 'block_by_user'"
                elif arg2 == 'block':
                    req += " WHERE role_ = 'block_by_user'"

                mycursor.execute(req)
                res = mycursor.fetchall()
                # проверяем на пустой результат
                if res:
                    if arg == 'show':
                        msg = '@' + ', @'.join([r[0] for r in res])
                    else:
                        msg = res[0][0]
                    send_message(self.id, msg)
                else:
                    send_message(self.id, "Пустой результат!")
            elif arg and arg[0] == '@':
                mycursor.execute('SELECT * FROM users WHERE username = %s', (arg[1:],))
                user_info = mycursor.fetchone()

                if not user_info:
                    send_message(self.id, 'Пользователь не найден!')
                    return
                else:
                    user_id = user_info[1]
                    role, balance, status, total = user_info[4:8]

                if user_info[-1]:
                    role_end = f"Действует до: {user_info[-1]} по МСК"
                else:
                    role_end = ""

                # get max_sec and role_active
                mycursor.execute("SELECT max_sec, role_active FROM roles WHERE name = %s", (role,))
                max_sec, role_active = mycursor.fetchone()

                if role_active:
                    role += ' (активна)'
                else:
                    role += ' (НЕ активна)'

                # get ref_count
                mycursor.execute("SELECT COUNT(*) FROM referral WHERE user_id = %s and invited_active = 1",
                                                                                                (user_id, ))
                ref_count = mycursor.fetchone()[0]

                param = {'id': user_id,'username': arg, 'balance': balance, 'reg_date': user_info[3],
                         'role': role, 'role_end': role_end,
                         'status': status, 'max_sec': max_sec, 'last_query': user_info[-2], 'total': total,
                         'ref_count': ref_count}
                text = get_text_from_db('admin_stats', param)
                send_message(self.id, text)
                return

            else:
                # при отсутсвии аргумента выводим количество пользователей
                mycursor.execute("SELECT count(*), sum(total), sum(balance) FROM users WHERE role_ != 'block_by_user'")
                res = mycursor.fetchone()
                send_message(self.id, f"Всего пользователей: <b>{res[0]}</b>\nВсего секунд: <b>{res[1]}</b>\nСумма балансов: <b>{res[2]}</b> руб.")

        # произвольное сообщение некоторым пользователям
        elif command == '/message':
            if arg and arg != 'saved' and arg2:
                # понимаем, что хотим отправить быстрое сообщение
                mycursor.execute(f"SELECT id FROM users WHERE username = %s", (arg[1:], ))
                chat_id = mycursor.fetchone()
                if not chat_id:
                    send_message(self.id, f"Пользователь {arg} не найден!")
                    return
                else:
                    chat_id = chat_id[0]
                r = send_message(chat_id, arg2)
                # проверяем на успешную отправку
                if not r['ok']:
                    # 403 - пользователь заблокировал бота
                    if r['error_code'] == 403:
                        mycursor.execute("UPDATE users SET role_ = 'block_by_user' WHERE id = %s", (chat_id,))
                        mydb.commit()
                        mycursor.execute("UPDATE referral SET invited_active = 0 WHERE invited_id = %s", (chat_id,))
                        mydb.commit()
                        send_message(self.id, "Пользователь заблокировал бота!")
                    else:
                        send_message(self.id,
                                     f"!!! <b>ERROR</b>\n{r['description']}")
                else:
                    send_message(self.id, "Сообщение успешно отправлено!")
                return

            # режим отправки сохранённого сообщения
            text = get_text_from_db('savedMsg')
            if arg == 'saved' and arg2:
                usernames = "', '".join(user[1:] for user in arg2.split())
                mycursor.execute(f"SELECT id FROM users WHERE username in ('{usernames}')")
                id_for_msg = [user[0] for user in mycursor.fetchall()]
                diff = len(arg2.split())-len(id_for_msg)
                if diff <= 0:
                    k = 0
                    blocked = []
                    for chat_id in id_for_msg:
                        r = send_message(chat_id, text)
                        time.sleep(0.04)
                        # проверяем на успешную отправку
                        if not r['ok']:
                            if r['error_code'] == 403:
                                # 403 - пользователь заблокировал бота
                                blocked.append(chat_id)
                            else:
                                # прочая ошибка
                                send_message(creator['id'],
                                             f"!!! <b>ERROR</b> на {k + 1} человеке (id: {chat_id}):\n{r['description']}")
                                return
                        else:
                            k += 1

                    n = len(blocked)
                    if n > 0:
                        # обновляем заблокированных пользователей
                        blocked = ', '.join(map(str, blocked))
                        # update block users
                        mycursor.execute(f"UPDATE users SET role_ = 'block_by_user' WHERE id in ({blocked})")
                        mydb.commit()

                        mycursor.execute(f"UPDATE referral SET invited_active = 0 WHERE invited_id in ({blocked})")
                        mydb.commit()

                    send_message(creator['id'], f"Сообщений успешно отправлено: <b>{k}</b>\nЗаблокировали бота: <b>{n}</b> чел.")
                else:
                    # Часть пользователей не найдена
                    send_message(self.id, f'NameError: {diff} пользователя не найдено!')
            else:
                # Как будет выглядеть сообщение
                send_message(self.id, text)

        # ban пользователя
        elif command == '/ban':
            if arg:
                mycursor.execute("SELECT EXISTS(SELECT username FROM users WHERE username = %s)",
                                 (arg[1:],))
                user_exist = mycursor.fetchone()
                if user_exist and arg != creator['username']:
                    mycursor.execute("UPDATE users SET role_ = 'ban' WHERE username = %s",
                                     (arg[1:],))
                    mydb.commit()
                    send_message(self.id, f'Пользователь {arg} забанен!')
                else:
                    send_message(self.id, f'Пользователь {arg} <b>не найден</b>!')
            else:
                mycursor.execute("SELECT username FROM users WHERE role_ = 'ban'")
                ban_list = mycursor.fetchone()
                if ban_list:
                    send_message(self.id, '<b>Забаненные:</b>\n@' + ', @'.join(ban_list))
                else:
                    send_message(self.id, 'Нет забаненных пользователей.')

        elif command == '/unban':
            if arg:
                mycursor.execute("UPDATE users SET role_ = 'standard' WHERE username = %s",
                                 (arg[1:],))
                mydb.commit()
                send_message(self.id, f'Пользователь {arg} разбанен!')
            else:
                send_message(self.id, f"Введите имя пользователя")

        # редактирование текста
        elif command == '/text':
            mycursor.execute("SELECT name FROM msgs WHERE text IS NOT NULL")
            texts = [text[0] for text in mycursor.fetchall()]
            if arg and (arg in texts):
                if arg2:
                    send_message(self.id, f'Теперь {arg} будет выглядеть так:')
                    r = send_message(self.id, arg2)
                    if not r['ok']:
                        send_message(self.id, r['description'])
                        return
                    mycursor.execute("UPDATE msgs SET text = %s WHERE name = %s",
                                     (arg2, arg))
                    mydb.commit()
                else:
                    text = get_text_from_db(arg)
                    send_message_not_parse(self.id, text)
            else:
                send_message(self.id, 'Доступны следующие теги: ' + ', '.join(texts))

        elif command == '/price':
            mycursor.execute("SELECT name_param FROM payment_param")
            params = [param[0] for param in mycursor.fetchall()]
            if arg and (arg in params):
                if arg2:
                    mycursor.execute("UPDATE payment_param SET value_param = %s WHERE name_param = %s",
                                     (arg2, arg))
                    mydb.commit()
                    send_message(self.id, f'Теперь {arg} = {arg2} сек')
                else:
                    mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = %s", (arg,))
                    value_param = mycursor.fetchone()[0]
                    send_message_not_parse(self.id, value_param)
            else:
                send_message(self.id, 'Доступны следующие товары: ' + ', '.join(params))

        # рассылка всем пользователям кроме заблокировавших
        elif command == '/update':
            if arg == 'confirm':
                put_SNS('MailingTrigger', 'update')
            else:
                mycursor.execute("SELECT text FROM msgs WHERE name = 'update'")
                text = mycursor.fetchone()[0]
                send_message(self.id, text)

    def file(self, tag, message):
        # проверка на статус юзера
        if self.status != "wait_file":
            send_message(self.id,
                         'Извините, но на данном этапе не нужно загружать файл. <i>Введите корректный ответ!</i>')
            return

        audio = self.event['message'][tag]

        # определение формата (если video_note >> mp4)
        if tag != 'video_note':
            format_ = audio['mime_type'].split('/')[1]
        else:
            format_ = 'mp4'

        # проверка на формат
        if format_ not in formats:
            send_message(self.id,
                         'Неизвестный формат файла! \n<b>Доступные форматы: mp3, ogg, mp4!</b>')
            send_message(self.id, '<i>Загрузите файл для нового запроса!</i>')
            mycursor.execute(f'DELETE FROM bass_requests WHERE id = %s', (self.id, ))
            mydb.commit()
            mycursor.execute(f"UPDATE users SET status_ = 'wait_file' WHERE id = %s", (self.id, ))
            mydb.commit()
            return

        # проверка на длительность и размер файла
        duration = round(audio['duration'])
        if audio['file_size'] > cred['maxsize']:
            send_message(self.id,
                             f"Мы не работаем с файлами больше {round(cred['maxsize']/10**6, 1)} Мб." +
                             "\n<b>Выберите файл поменьше!</b>")
            return

        # удаляем все предыдущие запросы во избежании багов
        mycursor.execute('DELETE FROM bass_requests WHERE id = %s', (self.id,))
        mydb.commit()

        # пытаемся определить название файла
        if 'performer' in audio and 'title' in audio:
            title = f"{audio['performer'].replace('|',' ')}|{audio['title'].replace('|',' ')}"
        elif 'title' in audio:
            title = audio['title'].replace('|', ' ')
        elif 'performer' in audio:
            title = audio['performer'].replace('|', ' ')
        else:
            title = 'Audio'

        # начинаем формировать запрос
        mycursor.execute("INSERT INTO bass_requests (id, file_id, format_, duration, file_name) VALUES (%s, %s, %s, %s, %s)", (
            self.id, audio['file_id'], format_, duration, title))
        mydb.commit()

        send_message(self.id,
                     'Файл принят! <b>Теперь можно отредактировать аудио</b>' +
                     '\n(обрезка и прочее...):',
                     if_edit_markup)

        # обновляем статус
        mycursor.execute('UPDATE users SET status_ = "wait_edit" WHERE id = %s', (self.id,))
        mydb.commit()

    def send_req_to_bass(self):
        # посылаем запрос
        send_message(self.id, '<b>Запрос отправлен!</b> Ожидайте файл в течение 15-40 секунд.')
        # получаем id сообщения (стикер с думающим утёнком)
        req_id = send_sticker(self.id, 'loading')
        file = get_file(self.id)
        # аварийная проверка на размер
        assert file['result']['file_size'] <= cred['maxsize']
        file_path = file['result']['file_path']
        mycursor.execute(
            f"UPDATE bass_requests SET req_id = %s, file_path = %s WHERE id = %s",
            (req_id, file_path, self.id))
        mydb.commit()
        mycursor.execute(
            "UPDATE users SET status_ = 'req_sent', last_query = NOW() + INTERVAL 3 HOUR WHERE id = %s",
            (self.id,))
        mydb.commit()
        put_SNS('BassBoostTrigger', req_id)

    # автоматическое обрезание песни
    def auto_cut(self, duration):
        if self.max_sec > duration:
            return
        # обрезаем файл, если максимальный объём меньше duration
        send_message(self.id,
                     '<b>Внимание!</b>' +
                     f'\nВаша роль не позволяет обрабатывать песни более <b>{self.max_sec}</b> секунд.' +
                     f'\nПесня будет обрезана до этого значения!')

        mycursor.execute('UPDATE bass_requests SET start_ = %s, end_ = %s where id = %s',
                         (0, self.max_sec, self.id))
        mydb.commit()

    def msg(self):
        # пытаемся распознать текст, иначе понимаем что юзер скинул неизвестный документ
        try:
            self.text = self.event['message']['text']
        except KeyError:
            # если мы сейчас ожидаем аудио >> неизвестный формат
            if self.status == "wait_file":
                send_message(self.id,
                             '<b>Ошибка!</b>\nВы отправили файл <b>документом</b>!' +
                             '\nВ этом случае бот не может узнать кодировку аудио и его продолжительность.' +
                             '\n<b>Отправьте файл в виде аудио!</b>')

            # иначе мы получили неизвестный документ, когда ожидали сообщение
            else:
                send_message(self.id, 'Ошибка! Введите ваш ответ более корректно!')
            return

        # command
        if self.text[0] == '/':
            self.commands()

        elif self.status == 'start':
            self.start_msg()

        elif self.status == "wait_file":
            send_message(self.id, 'Пожалуйста, отправьте <b>файл</b>, а не сообщение!',
                         file_markup)

        elif self.status == 'wait_edit':
            if self.text == 'Редактировать файл':
                mycursor.execute("UPDATE users SET status_ = 'wait_cut' WHERE id = %s", (self.id, ))
                mydb.commit()
                send_message(self.id,
                             '<b>Сначала укажи границы обрезки файла (если нужно).</b>' +
                             '\nПример (вводить без кавычек): "1.5 10" - обрезка песни с 1.5 по 10 секунду.',
                             cut_markup)
            elif self.text == 'Пропустить редактирование':
                # получаем длительность файла
                mycursor.execute('SELECT duration from bass_requests where id = %s', (self.id,))
                duration = mycursor.fetchone()[0]

                # выполняем автообрезание
                self.auto_cut(duration)

                mycursor.execute("UPDATE users SET status_ = 'wait_bass_level' WHERE id = %s", (self.id,))
                mydb.commit()
                send_message(self.id, '<b>Выбери уровень усиления трека:</b>', bass_markup)
            else:
                send_message(self.id, 'Нажмите одну из кнопок на клавиатуре!')

        # обрезка файла
        elif self.status == "wait_cut":
            # находим длительность файла
            mycursor.execute('SELECT duration from bass_requests where id = %s', (self.id,))
            duration = mycursor.fetchone()[0]

            if self.text == 'Обрезать не нужно':

                # автообрезание
                self.auto_cut(duration)

                send_message(self.id,
                             '<b>Теперь укажи, с какой секунды начинать преобразовывать трек. </b>Пример "5.2" - с 5.2 секунды.',
                             startbass_markup)
            else:
                s = self.text.split()
                # проверка, что введено 2 значения
                if len(s) != 2:
                    send_message(self.id, "<b>Введите 2 числа!</b>")
                    return

                # проверка, что введены именно ЧИСЛА
                try:
                    f0 = round(float(s[0]), 1)
                    f1 = round(float(s[1]), 1)
                except ValueError:
                    send_message(self.id,
                                 'Синтаксическая ошибка! \n<b>Проверьте, что десятичная дробь записана через точку!</b>',
                                 cut_markup)
                    return
                if (f0 >= 0) and (f0 < f1) and (f1 <= duration):
                    # проверка на баланс
                    mycursor.execute('UPDATE bass_requests SET start_ = %s, end_ = %s where id = %s',
                                     (f0, f1, self.id))
                    mydb.commit()
                    send_message(self.id,
                                 'Всё чётко! <b>Теперь укажи, с какой секунды начинать преобразовывать трек.</b>' +
                                  '\nПример: "5.2" - с 5.2 секунды.\n<i>Указывай время с начала уже обрезанной песни!</i>',
                                  startbass_markup)
                else:
                    send_message(self.id,
                                 'Границы обрезки выходят за длительность песни.\n<b>Напишите границы обрезки корректно!</b>',
                                 cut_markup)
                    return

            # обновляем статус на 2
            mycursor.execute('UPDATE users SET status_ = "wait_bass_start" WHERE id = %s', (self.id,))
            mydb.commit()

        # начало баса
        elif self.status == "wait_bass_start":
            if self.text != 'По умолчанию (с самого начала)':
                # корректность ввода числа
                try:
                    # f - начало басса
                    f = round(float(self.text), 1)
                except ValueError:
                    send_message(self.id,
                                 'Синтаксическая ошибка! \n<b>Проверьте, что десятичная дробь записана через точку!</b>',
                                 startbass_markup)
                    return
                mycursor.execute('SELECT duration, start_, end_ from bass_requests where id = %s', (self.id,))
                duration = mycursor.fetchone()
                if not duration[1]:
                    f1 = duration[0]
                else:
                    f1 = duration[2] - duration[1]

                # корректность ввода данных
                if (f >= 0) and (f < f1):
                    mycursor.execute('UPDATE bass_requests SET start_bass = %s WHERE id = %s',
                                     (f, self.id))
                    mydb.commit()
                else:
                    send_message(self.id,
                                 "Начало баса выходит за границы песни.\n" +
                                 "<i>(Если вы обрезали песню, то считайте начало от уже обрезанной песни!)</i>\n" +
                                 "<b>Напишите время корректно!</b>",
                                 startbass_markup)
                    return

            send_message(self.id, '<b>Выбери уровень усиления трека:</b>', bass_markup)
            # обновляем статус
            mycursor.execute('UPDATE users SET status_ = "wait_bass_level" WHERE id = %s', (self.id,))
            mydb.commit()

        # выбор уровня баса
        elif self.status == "wait_bass_level":
            if self.text in level:
                # уровень баса в словах >> цифры
                l = level.index(self.text)
                mycursor.execute('UPDATE bass_requests SET bass_level = %s WHERE id = %s',
                                 (l, self.id))
                mydb.commit()
                # отправляем запрос к BassBoostFunc
                self.send_req_to_bass()

            # непонятный уровень баса, введённый пользователем
            else:
                send_message(self.id,
                             'Такого уровня баса ещё не существует. Выберите уровень из <b>установленных значений!</b>',
                             bass_markup)


def get_users(role):
    mycursor.execute("SELECT id FROM users WHERE role_ = %s", (role,))
    users = [user[0] for user in mycursor.fetchall()]
    return users


class InlineButton:
    def __init__(self, event):
        call = event['callback_query']
        self.msg = call['message']
        self.user_id = self.msg['chat']['id']
        self.data = call['data']
        self.call_id = call['id']
        self.msg_id = self.msg['message_id']

    def action(self):
        # выполняем различные действия в зависимости от нажатия кнопки
        # генерируем оплату
        if self.data == 'pay':
            self.answer_query_no_text()
            r = send_message(self.user_id, 'Создание оплаты...')
            if not r['ok']:
                send_message(self.user_id, 'Ошибка в создании оплаты, повторите попытку позже.')
                return
            pay_id = r['result']['message_id']
            param = {'pay_id': pay_id, 'status': '❌ НЕ оплачено!'}
            text = get_text_from_db('pay_rule', param)
            edit_message(self.user_id, pay_id, text, pay_check_inline_markup)
            mycursor.execute(
                "INSERT INTO payment_query(pay_id, user_id, username, start_query, status_) VALUES (%s, %s, %s, NOW() + INTERVAL 3 HOUR, %s)",
                (pay_id, self.user_id, self.msg['chat']['username'], "wait_for_payment"))
            mydb.commit()
        elif self.data == 'check_payment':
            pay_check = pay.check_payment(self.msg_id, cred, mycursor, mydb)
            if pay_check['success']:
                self.answer_query_no_text()
                param = {'pay_id': self.msg_id, 'status': '<b>✅ Оплачено!</b>'}
                text = get_text_from_db('pay_rule', param)
                edit_message(self.user_id, self.msg_id, text)
                # получаем сумму в рублях
                sum_rub = pay_check['sum']
                # обновляем баланс
                mycursor.execute("UPDATE users SET balance = balance + %s WHERE id = %s",
                                 (sum_rub, self.user_id))
                mydb.commit()
                send_sticker(self.user_id, 'money')
                send_message(self.user_id,
                             f"Оплата успешно завершена!\nВам начислено <b>{sum_rub}</b> руб!")
            else:
                if pay_check['error'] == 'Payment_not_found':
                    self.answer_query(
                        'Повторите попытку проверки через нескольско секунд. Мы ещё не получили платёж от Qiwi!',
                        show_alert=True)
                elif pay_check['error'] == 'already_complete':
                    self.answer_query('Вы уже успешно оплатили этот заказ!', show_alert=True)
                else:
                    self.answer_query_no_text()
                    send_message(self.id,
                                 f"""Произошла ошибка на стороне Qiwi ({pay_check['error']}).
                                    <i>Убедитесь, что все введённые при оплате данные верны и
                                    повторите оплату снова.</i>""")
                    mycursor.execute("UPDATE payment_query SET status_ = %s WHERE pay_id = %s",
                                     (pay_check['error'], self.msg_id))
                    mydb.commit()
        elif self.data == 'error_payment':
            self.answer_query_no_text()
            send_message(self.user_id,
                         f"Сожалеем, что у вас возникли проблемы, опишите свою проблему в сообщении @{creator['username']}, прикрепите скриншот квитанции об оплате!")

        elif self.data == 'delete_payment':
            mycursor.execute("DELETE FROM payment_query WHERE pay_id = %s", (self.msg_id,))
            mydb.commit()
            self.answer_query('Успешно удалено')
            delete_message(self.user_id, self.msg_id)

        elif self.data in ('anon_share', 'name_share'):
            caption = f"{self.user_id}|{self.msg_id}|@{self.msg['chat']['username']}|"
            caption += "anon" if self.data == 'anon_share' else "public"
            caption += f"|reason|<b>"
            if 'performer' in self.msg['audio']:
                caption += f"{self.msg['audio']['performer']} - "
            caption += f"{self.msg['audio']['title']}</b>"
            send_to_admin_share_channel(self.msg['audio']['file_id'], caption)
            # удаляем клавиатуру
            edit_markup(self.user_id, self.msg_id)
            self.answer_query('Трек отправлен на модерацию в @BassBoostCollection!', show_alert=True)

        elif self.data == 'send_to_channel':
            if self.msg['caption']:
                parts = self.msg['caption'].split("|")
                if len(parts) == 6 and parts[3] in ('anon', 'public'):
                    caption = parts[5]
                    if parts[3] == 'public':
                        caption += f"\nОтправил {parts[2]}"
                    put_SNS('SendToChannelTrigger', f"{self.msg['audio']['file_id']}|{caption}")
                    delete_message(self.user_id, self.msg_id)
                    self.answer_query('Трек успешно отправлен!')
                    send_reply_message(parts[0],
                                       "Ваш трек <b>успешно</b> прошёл модерацию в канал @BassBoostCollection!",
                                       parts[1])
                else:
                    self.answer_query('Исправьте описание по образцу!', show_alert=True)
            else:
                self.answer_query('Добавьте к треку описание по образцу!', show_alert=True)

        elif self.data == 'delete_from_admin_share_channel':
            if self.msg['caption']:
                parts = self.msg['caption'].split("|")
                if len(parts) != 6:
                    self.answer_query("В описании должно быть 6 слов, разделённых '|'.", show_alert=True)
                    return
                text = "Извините, ваш трек не прошёл модерацию в канал @BassBoostCollection."
                if parts[4] != 'reason':
                    text += f" Причина: {parts[4]}."
                text += " Попробуйте в следующий раз :)"
                send_reply_message(parts[0], text, parts[1])
                delete_message(self.user_id, self.msg_id)
                self.answer_query('Успешно удалён!')

        # товары
        else:
            mycursor.execute("SELECT balance FROM users WHERE id = %s", (self.user_id,))
            balance = mycursor.fetchone()[0]
            premium_prod = {'premium_day': 1, 'premium_week': 7, 'premium_month': 30}
            if self.data in premium_prod:
                mycursor.execute("SELECT value_param FROM payment_param WHERE name_param = %s", (self.data, ))
                price = mycursor.fetchone()[0]
                if balance >= price:
                    mycursor.execute(
                        """UPDATE users SET balance = balance - %s, role_ = 'premium',
                        role_end = IF (role_end IS NULL, NOW() + INTERVAL 3 HOUR + INTERVAL %s DAY, role_end + INTERVAL %s DAY)
                        WHERE id = %s""",
                        (price, premium_prod[self.data], premium_prod[self.data], self.user_id))
                    mydb.commit()
                    self.answer_query("Успешно!")
                    mycursor.execute("SELECT role_end FROM users WHERE id = %s", (self.user_id, ))
                    send_message(self.user_id,
                                 f"Вы успешно приобрели подписку premium до {mycursor.fetchone()[0]} по МСК.")

                else:
                    self.answer_query("Недостаточно средств на балансе!", show_alert=True)

    def answer_query(self, text, show_alert=False):
        url = URL + "answerCallbackQuery?callback_query_id={}&text={}&show_alert={}".format(self.call_id, text,
                                                                                            show_alert)
        requests.get(url)

    def answer_query_no_text(self):
        url = URL + "answerCallbackQuery?callback_query_id={}".format(self.call_id)
        requests.get(url)


def msg_handler(event):
    global mycursor
    global mydb
    # обновляем подключение к бд
    mycursor, mydb = connect_db()

    # проверка на нажатие инлайн кнопки
    if 'callback_query' in event.keys():
        button = InlineButton(event)
        button.action()
        return

    # инициализация юзера
    user = User(event)
    # проверка на успешную инициализацию
    if not user.init_success:
        return

    # проверка на бан
    if user.role == 'ban':
        text = get_text_from_db('ban')
        send_message(user.id, text)
        return

    # debug mode
    if user.role_active == 0:
        if user.status == 'start':
            user.start_msg()
        else:
            text = get_text_from_db('sleep')
            send_message(user.id, text)
            send_sticker(user.id, 'sleep')
        return

    # проверяем: это сообщение или файл - находим общие ключи
    c = list(set(event['message'].keys()) & tags)

    # юзер залил файл
    if c:
        user.file(c[0], event['message'])

    # Юзер написал текст
    else:
        user.msg()


####################
#  lambda_handler  #
####################
def lambda_handler(event, context):
    # обрабатываем любые исключения
    try:
        event = json.loads(event['body'])
        msg_handler(event)
    except Exception as e:
        print(f'ERROR:{e} || EVENT:{event}')
        send_message(creator['id'], f'ERROR:\n{e}\nEVENT:\n{event}')

    # в любом случае возвращаем телеграму код 200
    return {'statusCode': 200}


# Telegram methods
def send_message(chat_id, text, reply_markup=None):
    url = URL + "sendMessage?chat_id={}&text={}&parse_mode=HTML".format(chat_id, text)
    if reply_markup:
        url += f"&reply_markup={json.dumps(reply_markup)}"
    r = requests.get(url).json()
    return r


def send_reply_message(chat_id, text, msg_id):
    url = URL + "sendMessage?chat_id={}&text={}&reply_to_message_id={}&parse_mode=HTML".format(chat_id, text, msg_id)
    requests.get(url)


def send_message_not_parse(chat_id, text):
    url = URL + "sendMessage?chat_id={}&text={}".format(chat_id, text)
    requests.get(url)


def edit_message(chat_id, message_id, text, reply_markup=None):
    url = URL + "editMessageText?chat_id={}&message_id={}&text={}&parse_mode=HTML".format(chat_id, message_id, text)
    if reply_markup:
        url += f"&reply_markup={json.dumps(reply_markup)}"
    requests.get(url)


def edit_markup(chat_id, message_id, reply_markup=None):
    url = URL + "editMessageReplyMarkup?chat_id={}&message_id={}".format(chat_id, message_id)
    if reply_markup:
        url += f"&reply_markup={json.dumps(reply_markup)}"
    requests.get(url)


def delete_message(chat_id, message_id):
    url = URL + "deleteMessage?chat_id={}&message_id={}".format(chat_id, message_id)
    requests.get(url)


def send_to_admin_share_channel(bass_file_id, caption):
    url = URL + "sendAudio?chat_id={}&audio={}&caption={}&parse_mode=HTML".format(cred['admin_share_channel_id'],
                                                                                  bass_file_id, caption)
    # добавляем клавиатуру
    admin_share_markup = {"inline_keyboard": [[{"text": "ОТПРАВИТЬ В КАНАЛ!", 'callback_data': 'send_to_channel'}],
                                              [{"text": "УДАЛИТЬ ТРЕК!", 'callback_data': 'delete_from_admin_share_channel'}]]}
    url += f"&reply_markup={json.dumps(admin_share_markup)}"
    requests.get(url)


def get_text_from_db(tag, param=None):
    mycursor.execute("SELECT text FROM msgs WHERE name = %s", (tag,))
    text = mycursor.fetchone()[0]
    if text:
        if param:
            try:
                text = text.format(**param)
            except KeyError:
                admins = get_users('admin')
                for admin in admins:
                    send_message(admin, f'!!! <b>ERROR</b> Error with format {tag}!')
        return text
    admins = get_users('admin')
    for admin in admins:
        send_message(admin, f'!!! <b>ERROR</b> Error {tag} not found!')


def send_sticker(chat_id, sticker):
    mycursor.execute("SELECT stick_id FROM msgs WHERE name = %s", (sticker,))
    stick = mycursor.fetchone()[0]
    if stick:
        url = URL + "sendSticker?chat_id={}&sticker={}&parse_mode=HTML".format(chat_id, stick)
        try:
            r = requests.get(url).json()
            return r['result']['message_id']
        except KeyError:
            pass

    # если ошибка
    admins = get_users('admin')
    for admin in admins:
        send_message(admin, f'!!! <b>ERROR</b> Sticker {sticker} not found!')
    return round(time.time())


def get_file(chat_id):
    # get file_id from db
    mycursor.execute('SELECT file_id FROM bass_requests WHERE id = %s', (chat_id,))
    file_id = mycursor.fetchone()[0]
    # make request
    url = URL + "getFile?file_id={}".format(file_id)
    r = requests.get(url)
    return json.loads(r.content)


# AWS methods
# RDS DataBase
def connect_db():
    # DataBase
    mydb = mysql.connector.connect(
        host=cred['db_host'],
        user=cred['db_user'],
        passwd=cred['db_passwd'],
        database=cred['db_name']
    )
    mycursor = mydb.cursor()
    return mycursor, mydb


# publish to SNS topic
def put_SNS(topic_name, message):
    arn = cred[f'{topic_name}_topic_arn']
    client = boto3.client('sns')

    response = client.publish(
        TargetArn=arn,
        Message=json.dumps(message)
    )
