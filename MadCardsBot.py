import threading

import telebot
from telebot import types

import random
from random import seed
from random import choice
random.seed(100500)

from black_cards import black_cards
from white_cards import white_cards

import os
script_dir = os.path.dirname(__file__)
rel_path = '../token'
tkn = open(os.path.join(script_dir, rel_path), 'r')
TOKEN = tkn.readline().strip()
tkn.close()
bot = telebot.TeleBot(TOKEN)

commands_general = {
    'create'      : 'Создать игру',
    'join'        : 'Присоедениться к игре',
    'start'       : 'Начать игру',
    'cancel'      : 'Отмена игры',
    'help'        : 'Отоброжение доступных команд',
}
commands_special = {
    'scores'      : 'Таблица очков',
    'leave'       : 'Покинуть игру',
    'draw'        : 'Сбросить руку за одно очко',
}

hideBoard = types.ReplyKeyboardRemove()

HAND_SIZE = 10
MAX_GAME_ID = 0xffff
MAX_SCORES_VAL = 10
MIN_PLAYERS_NUM = 3
MAX_PLAYERS_NUM = 8
TIMER_EXPIRE_SEC = 60

gids = [0]  # GAME_ID = 0 - reserved
games = {}
uid2gid = {}

# --- assist functions ---

def extract_args(args):
    return args.split()[1:]

def user_in_game(uid):
    return uid in uid2gid

def send_message_to_others(users, msg, ignore, pm=None):
    for u in users:
        if u.id == ignore:
            continue
        bot.send_message(u.id, msg, parse_mode=pm)

def send_message_to_all(users, msg, pm=None):
    for u in users:
        bot.send_message(u.id, msg, parse_mode=pm)

def send_message_to_all_and_hide_kb(users, msg, pm=None):
    for u in users:
        bot.send_message(u.id, msg, parse_mode=pm, reply_markup=hideBoard)

def forward_message_to_others(users, msg):
    for u in users:
        if u.id == msg.from_user.id:
            continue
        bot.forward_message(u.id, msg.chat.id, msg.message_id)

# --- game logic functions ---

def timer_expire(gid):
    print("timer expired")
    if gid in games and games[gid]['stage'] == 'ongame':
        send_message_to_all_and_hide_kb(games[gid]['users'], "Таймер истек. " +
            "От неопределившиеся берется случайный ответ.")
        games[gid]['stage'] = 'wrapup'
        for u in games[gid]['users']:
            if not games[gid][u.id]['answered'] and games[gid]['host'].id != u.id:
                games[gid][u.id]['afk'] = True
                games[gid][u.id]['answered'] = True
                random.shuffle(games[gid][u.id]['hand'])
                games[gid]['answers'][games[gid][u.id]['hand'].pop()] = u
        ask_host(gid)

def end_game(gid):
    print("end game")
    for u in games[gid]['users']:
        uid2gid.pop(u.id, None)
    games[gid].clear()
    games.pop(gid, None)
    gids.remove(gid)

def print_scores(gid):
    print("print scores")
    msg = "Таблица результатов:"
    for u in games[gid]['users']:
        score = games[gid][u.id]['score']
        msg += "\n@{} : {}".format(u.username, score)
    send_message_to_all(games[gid]['users'], msg)

def show_hand(gid, u):
    print("show hand")
    select = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for a in games[gid][u.id]['hand']:
        select.add(a)
    bot.send_message(u.id, "Выберите один из вариантов:", reply_markup=select)

def give_cards(gid):
    print("give cards")
    if len(games[gid]['white_pool']) < (len(games[gid]['users']) - 1):
        games[gid]['white_pool'] += games[gid]['white_discard'].copy()
        games[gid]['white_discard'].clear()
        random.shuffle(games[gid]['white_pool'])
    for u in games[gid]['users']:
        while len(games[gid][u.id]['hand']) < HAND_SIZE:
            games[gid][u.id]['hand'].append(games[gid]['white_pool'].pop())
        if u.id != games[gid]['host'].id:
            show_hand(gid, u)

def ask_host(gid):
    print("ask host")
    hid = games[gid]['host'].id
    select = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    index = 1
    answ_msg  = "Черная карта:\n<b>{}</b>\n".format(games[gid]['black_card'])
    answ_msg += "Ответы этого раунда:"
    answ_list = list(games[gid]['answers'].keys())
    random.shuffle(answ_list)
    for t in answ_list:
        answ_msg += "\n{}. ".format(index) + t
        index += 1
        select.add(t)
    bot.send_message(hid, answ_msg, reply_markup=select, parse_mode='HTML')
    send_message_to_others(games[gid]['users'], answ_msg, hid, 'HTML')

def pop_black_card(gid):
    print("pop black card")
    games[gid]['black_card'] = games[gid]['black_pool'].pop()
    send_message_to_all(games[gid]['users'],
        "Черная карта:\n<b>{}</b>".format(games[gid]['black_card']),
        'HTML')
    if len(games[gid]['black_pool']) == 0:
        games[gid]['black_pool'] = black_cards.copy()
        random.shuffle(games[gid]['black_pool'])

def start_round(gid):
    print("start round")
    games[gid]['stage'] = 'ongame'
    for u in games[gid]['users']:
        games[gid][u.id]['answered'] = False
    games[gid]['white_discard'] += list(games[gid]['answers'].keys())
    games[gid]['answers'].clear()
    games[gid]['host'] = games[gid]['users'][games[gid]['host_idx']]
    send_message_to_all(games[gid]['users'], "@{} хост этого раунда.".format(games[gid]['host'].username))
    pop_black_card(gid)
    give_cards(gid)
    games[gid]['host_msg'] = bot.send_message(games[gid]['host'].id, "Ожидайте ответов игроков...")
    print("timer activated")
    t = threading.Timer(TIMER_EXPIRE_SEC, timer_expire, [gid])
    t.start()
    games[gid]['timer'] = t

def start_game(gid):
    print("start game")
    send_message_to_all(games[gid]['users'], "Игра начинается!")
    games[gid]['host_idx'] = 0
    random.shuffle(games[gid]['black_pool'])
    random.shuffle(games[gid]['white_pool'])
    start_round(gid)

def add_player(gid, u):
    print("add player")
    uid2gid[u.id] = gid
    games[gid][u.id] = { 'score' : 0, 'hand' : [], 'afk' : False }
    games[gid]['users'].append(u)

def look_for_host(gid, inc):
    print("look for host")
    idx = games[gid]['host_idx']
    for _ in range(1, len(games[gid]['users'])):
        idx = (games[gid]['host_idx'] + inc) % len(games[gid]['users'])
        uid = games[gid]['users'][idx].id
        if not games[gid][uid]['afk']:
            games[gid]['host_idx'] = idx
            return True
        inc += 1
    return False

# --- command handlers ---

# Show help
@bot.message_handler(commands=['help'])
def command_help(m):
    uid = m.from_user.id
    help_text = "<b>Доступные команды:</b>\n"
    for key in commands_general:
        help_text += "/" + key + ": "
        help_text += commands_general[key] + "\n"
    help_text += "<b>Специальные команды, доступные во время игры:</b>\n"
    for key in commands_special:
        help_text += "/" + key + ": "
        help_text += commands_special[key] + "\n"
    bot.send_message(uid, help_text, parse_mode='HTML')

# Create game
@bot.message_handler(commands=['create'])
def command_create(m):
    print("executing create")
    if user_in_game(m.from_user.id):
        bot.send_message(m.from_user.id,
            "Вы уже в игре. /cancel чтобы отменить, /leave чтобы покинуть.")
        return
    r = [i for i in range(MAX_GAME_ID) if i not in gids]
    if not r:
        # TODO: notify me, the situation is incredible
        bot.send_message(m.from_user.id,
            "ACHTUNG: Не могу создать игру, нет свободных ID.")
        return
    u = m.from_user
    uid = u.id
    gid = choice(r)
    gids.append(gid)
    games[gid] = {
                    'users' : [],
                    'answers' : {},
                    'stage' : 'recruit',
                    'black_pool' : black_cards.copy(),
                    'white_pool' : white_cards.copy(),
                    'white_discard' : [],
                 }
    add_player(gid, u)
    bot.send_message(m.from_user.id,
        "Игра создана, ID: {}".format(gid))

# Start game
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id), commands=['start'])
def command_start(m):
    print("executing start")
    gid = uid2gid[m.from_user.id]
    if games[gid]['stage'] != 'recruit':
        bot.send_message(m.from_user.id, "Игра уже начата.")
        return
    if len(games[gid]['users']) >= MIN_PLAYERS_NUM:
        start_game(gid)
    else:
        bot.send_message(m.from_user.id, "Для начала игры надо как минимум 3 человека. " +
            "Сейчас зарегестрировано: {}".format(len(games[gid]['users'])))

# Join game by id
@bot.message_handler(commands=['join'])
def command_join(m):
    print("executing join")
    args = extract_args(m.text)
    if not args:
        bot.send_message(m.from_user.id,
            "Для подключения к игре укажите ID игры:\n/join ID")
        return
    if user_in_game(m.from_user.id):
        bot.send_message(m.from_user.id, "Вы уже в игре.")
        return
    gid = 0
    try:
        gid = int(args[0])
    except Exception as err:
        bot.send_message(m.from_user.id, "Указан некорректный ID: {}".format(gid))
        return
    if not games.get(gid):
        bot.send_message(m.from_user.id, "Игры с указаным ID нет.")
        return
    if games[gid]['stage'] != 'recruit':
        bot.send_message(m.from_user.id, "Игра уже начата.")
        return
    u = m.from_user
    uid = u.id
    bot.send_message(uid, "Вы зарегистрировались. " +
        "Игра начнется, когда наберется 8 участников или по использованию команды /start. " +
        "Вы можете писать своим товарищам в этот чат.")
    add_player(gid, u)
    send_message_to_others(games[gid]['users'],
        "@{} присоединился к игре".format(m.from_user.username), uid)
    if len(games[gid]['users']) >= MAX_PLAYERS_NUM:
        start_game(gid)

# Leave game
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id), commands=['leave'])
def command_text_leave(m):
    print("executing leave")
    u = m.from_user
    gid = uid2gid[u.id]
    # --- small example of python's convenience
    for i in range(len(games[gid]['users'])):
        if games[gid]['users'][i].id == u.id:
            del games[gid]['users'][i]
            break
    # --- love it so much
    games[gid].pop(u.id, None)
    uid2gid.pop(u.id, None)
    send_message_to_all(games[gid]['users'],
        "@{} решил покинуть игру".format(u.username))
    if games[gid]['stage'] == 'recruit':
        if len(games[gid]['users']) == 0:
            bot.send_message(m.from_user.id, "Игра отменена ввиду отсутствия участников.")
            end_game(gid)
    else:
        if len(games[gid]['users']) < MIN_PLAYERS_NUM:
            send_message_to_all(games[gid]['users'],
                "Слишком мало игроков чтобы продолжать, игра окончена")
            print_scores(gid)
            end_game(gid)
        elif games[gid]['host'].id == u.id:
            if look_for_host(gid, 0):
                start_round(gid)
            else:
                send_message_to_all(games[gid]['users'],
                    "Нет активных игроков, игра отменена.")
                end_game(gid)

# Draw new cards
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id), commands=['draw'])
def command_text_draw(m):
    print("executing draw")
    uid = m.from_user.id
    gid = uid2gid[uid]
    if games[gid]['stage'] == 'recruit':
        bot.send_message(uid, "Игра еще не началась.")
    else:
        if games[gid][uid]['score'] > 0:
            games[gid]['white_discard'] += games[gid][uid]['hand']
            games[gid][uid]['hand'] = []
            while len(games[gid][uid]['hand']) < HAND_SIZE:
                games[gid][uid]['hand'].append(games[gid]['white_pool'].pop())
            games[gid][uid]['score'] -= 1
            send_message_to_others(games[gid]['users'],
                "@{} сбросил руку.".format(m.from_user.username), uid)
            bot.send_message(uid,
                "Рука обновлена, теперь у вас {} очков".format(games[gid][uid]['score']))
            if games[gid]['host'].id != uid and games[gid]['stage'] == 'ongame':
                show_hand(gid, m.from_user)
        else:
            bot.send_message(uid, "Недостаточно очков для сброса руки.")

# Print scores
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id), commands=['scores'])
def command_text_scores(m):
    print("executing scores")
    gid = uid2gid[m.from_user.id]
    print_scores(gid)

# Cancel game
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id), commands=['cancel'])
def command_text_cancel(m):
    print("executing cancel")
    gid = uid2gid[m.from_user.id]
    send_message_to_all_and_hide_kb(games[gid]['users'], "Игрок @{} отменил игру".format(m.from_user.username))
    end_game(gid)

# Text messages handler
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id), content_types=['text'])
def command_text_user(m):
    print("executing text")
    u = m.from_user
    uid = u.id
    gid = uid2gid[uid]
    if games[gid]['stage'] == 'wrapup' and games[gid]['host'].id == uid and m.text in games[gid]['answers']:            # host chose winner of the raund
        print("host answered")
        w = games[gid]['answers'][m.text] # winner
        games[gid][w.id]['score'] += 1
        msg = "Победитель этого раунда @{}:\n{}\nс ответом:\n{}".format(w.username, games[gid]['black_card'], m.text)
        send_message_to_all_and_hide_kb(games[gid]['users'], msg)
        if (games[gid][w.id]['score'] >= MAX_SCORES_VAL):
            print_scores(gid)
            send_message_to_all(games[gid]['users'], "<b>@{} победитель этой игры!</b>".format(w.username), pm='HTML')
            end_game(gid)
        else:
            if look_for_host(gid, 1):
                start_round(gid)
            else:
                send_message_to_all(games[gid]['users'],
                    "Нет активных игроков, игра отменентменена.")
                end_game(gid)
    elif games[gid]['stage'] == 'ongame' and not games[gid][uid]['answered'] and m.text in games[gid][uid]['hand']:     # participant made his choice
        print("participant answered")
        games[gid][uid]['afk'] = False
        games[gid][uid]['answered'] = True
        games[gid]['answers'][m.text] = m.from_user
        games[gid][uid]['hand'].remove(m.text)
        bot.send_message(uid, "Ваш вариант принят", reply_markup=hideBoard)
        if len(games[gid]['users']) == (len(games[gid]['answers']) + 1):
            games[gid]['timer'].cancel()
            games[gid]['stage'] = 'wrapup'
            bot.edit_message_text("Все ответы получены",
                chat_id=games[gid]['host'].id,
                message_id=games[gid]['host_msg'].message_id)
            ask_host(gid)
        else:
            bot.edit_message_text("Получен {} ответ/a/ов".format(len(games[gid]['answers'])),
                chat_id=games[gid]['host'].id, message_id=games[gid]['host_msg'].message_id)
    elif m.text not in white_cards:                                                                                     # forward message to others
        print("fwd")
        forward_message_to_others(games[gid]['users'], m)

# Forward non-text messages to others
@bot.message_handler(func=lambda message: user_in_game(message.from_user.id),
                                          content_types=['audio', 'photo', 'voice', 'video', 'document', 'location', 'contact', 'sticker', 'video_note', 'venue'])
def command_not_text(m):
    print("executing non-text")
    uid = m.from_user.id
    gid = uid2gid[uid]
    if m.content_type in ['audio', 'photo', 'video', 'document', 'location', 'contact', 'sticker', 'venue']:
        send_message_to_others(games[gid]['users'],
            "fwd from @{}:".format(m.from_user.username), uid)
    forward_message_to_others(games[gid]['users'], m)

bot.polling(none_stop=True, interval=0)
