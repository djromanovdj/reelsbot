from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ContentType,InlineKeyboardMarkup, InlineKeyboardButton

import instaloader
from instaloader import Post

import asyncpg
import asyncio

import logging
import os
from shutil import rmtree
from random import randint

from config import *


#-------------------------------------------------------------------------------#

# Логи
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('broadcast')

# Аиограм
bot = Bot(token=TOKEN,parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

# Директория бота
root_patch = f'{os.path.abspath(os.curdir)}'

# loop асинхрона
loop = asyncio.get_event_loop()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
}

# вариации ссылок инсты
insta = ('https://www.instagram','https://instagram','instagram','instagram.com')


#-------------------------------------------------------------------------------#
# Класс стейтов

class Mailing(StatesGroup):
	messagetext = State()
	accept = State()

class AddAcc(StatesGroup):
	account_check = State()

class DeleteAcc(StatesGroup):
	deleteacc = State()

#-------------------------------------------------------------------------------#
# Хендлеры админов

@dp.message_handler(user_id = ADMIN_ID, commands = ['start'])
async def adminstartmessage(message: types.Message):
	await db.add_user(message)
	await message.answer("Привет, этот бот может скачивать Reels из инстаграмма!\nДля начала, просто отправь ссылку на видео\
						 \n\
						 \n<i>Текст ниже видит только администратор бота</i>\
						 \n\
						 \n/count - текущее количество пользователей бота\
						 \n/count_messages - текущее количество сообщений в боте\
						 \n/tell_everyone - отослать сообщение всем пользователям бота\
						 \n/addaccount - добавить аккаунты для скачивания\
						 \n/deleteaccount - удалить аккаунт\
						 \n/check_accs - Список аккаунтов в бд")

@dp.message_handler(user_id = ADMIN_ID, commands = ['count'])
async def admcount(message: types.Message,state:FSMContext):
	userscount = await db.count_users()
	await message.answer(f"Колво юзеров: {userscount}")


@dp.message_handler(user_id = ADMIN_ID, commands = ['count_messages'])
async def admcountmessges(message: types.Message,state:FSMContext):
	userscount = await db.count_messages()
	await message.answer(f"Колво сообщений в боте: {userscount}")

#----- Рассылка -----#
@dp.message_handler(user_id = ADMIN_ID, commands = ['tell_everyone'])
async def mailing(message: types.Message,state:FSMContext):
	await message.answer("Пришлите текст рассылки")
	await Mailing.messagetext.set()


@dp.message_handler(user_id = ADMIN_ID, state = Mailing.messagetext)
async def mailing_accept(message: types.Message, state: FSMContext):
    text = message.text
    await state.update_data(text=text)
    markup = InlineKeyboardMarkup(
    	inline_keyboard=
        [
            [InlineKeyboardButton(text="Отослать", callback_data="yes")],
            [InlineKeyboardButton(text="Отмена", callback_data="cancle")],
        ]
    )
    await message.answer("Текст:\n"
                         "{text}".format(text = text),
                         reply_markup = markup)
    await Mailing.accept.set()


@dp.callback_query_handler(user_id = ADMIN_ID, state = Mailing.accept)
async def mailing_start(call: types.CallbackQuery, state: FSMContext):
	if call.data == "yes":
	    data = await state.get_data()
	    text = data.get("text")
	    await state.reset_state()
	    await call.message.edit_reply_markup()
	    users = await db.get_all_users()
	    for user in users:
	        try:
	            await bot.send_message(chat_id=user['user_id'],
	                                   text=text)
	            await asyncio.sleep(0.3)
	        except Exception:
	            pass
	    await call.message.answer("Рассылка выполнена.")
	else:
		await call.message.answer("Вы отменили действие")
		await call.message.edit_reply_markup()
		await state.reset_state()

#----- Добавление аккаунтов -----#

@dp.message_handler(user_id = ADMIN_ID, commands = ['addaccount'])
async def addaccount(message:types.Message, state:FSMContext):
	markup = InlineKeyboardMarkup().row(
		InlineKeyboardButton(text="Отмена", callback_data="cancel"))
	await message.answer("Введите login:password аккаунтa\
						\n(Можно несколько, через запятую)",
						reply_markup = markup)
	await AddAcc.account_check.set()

@dp.message_handler(user_id = ADMIN_ID, state = AddAcc.account_check)
async def addaccount_check(message:types.Message, state:FSMContext):
	await state.reset_state()
	accs = message.text.split(",")
	for acc in accs:
		acc = acc.split(":")
		await db.add_account(acc[0], acc[1])
		await message.answer(f"Добавил аккаунт\
			                \nЛогин: {acc[0]}\
							\nПароль: {acc[1]}")

#----- Список аккаунтов в бд -----#

@dp.message_handler(user_id = ADMIN_ID, commands = ['check_accs'])
async def checkaccs(message: types.Message,state:FSMContext):
	accs = await db.get_all_accounts()
	if accs:
		await message.answer("Аккаунты:")
		for acc in accs:
			await message.answer(f"Логин: {acc.get('username')}\
								\nПароль: {acc.get('password')}")
	else:
		await message.answer('Не добавленно ни одного аккаунта')

#----- Удаление аккаунта -----#

@dp.message_handler(user_id = ADMIN_ID, commands = ['deleteaccount'])
async def deleteacc(message: types.Message,state:FSMContext):
	markup = InlineKeyboardMarkup().row(
		InlineKeyboardButton(text="Отмена", callback_data="cancel"))
	await message.answer("Введите логин аккаунтa",
						reply_markup = markup)
	await DeleteAcc.deleteacc.set()

@dp.message_handler(user_id = ADMIN_ID, state = DeleteAcc.deleteacc)
async def deleteacc2(message: types.Message,state:FSMContext):
	login = message.text
	await state.reset_state()
	await db.delete_account(login)
	await message.answer(f"Удалён аккаунт {login}")

@dp.callback_query_handler(user_id = ADMIN_ID, state = [AddAcc.account_check, DeleteAcc.deleteacc])
async def cancle(call: types.CallbackQuery, state: FSMContext):
	if call.data == "cancel":
		await call.message.answer("Вы отменили действие")
		await call.message.edit_reply_markup()
		await state.reset_state()

#-------------------------------------------------------------------------------#
# Хендлеры юзеров

@dp.message_handler(commands=['start'])
async def startmessage(message: types.Message):
	await db.add_user(message)
	await message.answer("Привет, этот бот может скачивать Reels из инстаграмма!\n Для начала, просто отправь ссылку на видео")

@dp.message_handler(commands=['help'])
async def helpmessage(message: types.Message):
	await message.answer("Пришли мне ссылку на reels, а я его скачаю и кину тебе!\
						 \nПример ссылки: https://www.instagram.com/reel/XXXXXXXX/")

@dp.message_handler(content_types=ContentType.ANY)
async def instadl(message: types.Message):
	await db.add_message(message)
	try:
		if message.text:
			if message.text.startswith(insta):
				url = message.text.split("/")
				if url[3] in 'reel':
					itemid = url[4]
				else:
					await message.reply("Это не reels ссылка!")
					return False
				mes = await message.answer("<i>Скачиваю...</i>")
				dirname = randint(0,9999999)
				await download_reels(mes, itemid, dirname)
				await send_video(message, itemid, dirname)
				await bot.delete_message(message.from_user.id,mes.message_id)
				rmtree(fr'{root_patch}/files/{dirname}')
			else:
				await message.answer("Это не ссылка на видео!")
		else:
			await message.answer("Это не ссылка на видео!")
	except Exception as e:
		print(e)
		await bot.send_message(DEV_ID, f"Ошибка: {e}\
									   \nСообщение пользователя: {message.text}\
									   \nПользователь: @{message.from_user.username}\
									   \nАйди пользователя: {message.from_user.id}")


#-------------------------------------------------------------------------------#
# Функции

def download_item(itemid, dirname,login,password):

	if(os.path.isdir(fr"files/{dirname}") == False):
		os.mkdir(fr"files/{dirname}")

	dlinst = instaloader.Instaloader(user_agent = headers.get("User-Agent"),
									 dirname_pattern =fr'{root_patch}/files/{dirname}/', 
                					 max_connection_attempts=3,
									 download_video_thumbnails=False,
									 save_metadata=False,
									 post_metadata_txt_pattern = '',
									)
	dlinst.login(login,password)
	post = Post.from_shortcode(dlinst.context, itemid)
	dlinst.download_post(post,":feed")

async def download_reels(mes, itemid, dirname):
	try:
		url = f'https://www.instagram.com/reel/{itemid}'
		login,password = await get_random_acc()
		#proxy,proxies = await get_proxies()
		futures = [await loop.run_in_executor(None, download_item, itemid, dirname, login,password )]
	except Exception as e:
		print(e)
		await bot.delete_message(mes.chat.id,mes.message_id)
		await mes.answer("Ошибка скачивания, попробуйте позже")
		await bot.send_message(DEV_ID, f"Ошибка: {e}\
									     \nВидео: https://www.instagram.com/reel/{itemid}\
									     \nСообщение пользователя: {mes.text}\
									     \nПользователь: @{mes.from_user.username}\
									     \nАйди пользователя: {mes.from_user.id}")


async def send_video(message, itemid, dirname):
	me = await bot.get_me()
	promotecaption = f"https://www.instagram.com/reel/{itemid}\n\nСкачано в @{me.username}"
	for file in os.listdir(fr'{root_patch}/files/{dirname}/'):
		if file.endswith('.mp4'):
			await bot.send_video(
							 	chat_id = message.from_user.id,
								video = open(fr'{root_patch}/files/{dirname}/{file}', 'rb'),
							 	caption = promotecaption,
								)

async def get_random_acc():
	accs = await db.get_all_accounts()
	random = randint( 0, len(accs)-1 )
	loginpass = accs[random]
	login = loginpass.get('username')
	password = loginpass.get('password')
	return login,password

#-------------------------------------------------------------------------------#
# Работа с базой данных

class Database:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.pool = loop.run_until_complete(
            asyncpg.create_pool(DATABASE_URL))

#----- Работа с юзерами -----#

    async def add_user(self,message):
    	username,userid = message.from_user.username,message.from_user.id
    	sql = '''
        INSERT INTO users(username, user_id) VALUES($1, $2) \
		ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
				'''
    	await self.pool.execute(sql,username,userid)

    async def add_message(self,message):
    	username,userid = message.from_user.username,message.from_user.id
    	message	= str(message.to_python())
    	sql = '''
        INSERT INTO messages(username, user_id, message) VALUES($1, $2, $3)
			  '''
    	await self.pool.execute(sql,username,userid, message)

    async def count_users(self):
        return await self.pool.fetchval("SELECT COUNT(*) FROM users")

    async def count_messages(self):
        return await self.pool.fetchval("SELECT COUNT(*) FROM messages")

    async def get_all_users(self):
    	return await self.pool.fetch("SELECT user_id FROM users")

#----- Работа с аккаунтами -----#

    async def get_all_accounts(self):
    	rows = await self.pool.fetch("SELECT username,password FROM accounts")
    	data = [dict(row) for row in rows]
    	return data

    async def add_account(self,login,passwd):
    	sql = """
    	INSERT INTO accounts(username, password) VALUES($1, $2)
		"""
    	await self.pool.execute(sql,login,passwd)

    async def delete_account(self,login):
    	sql = """
    	DELETE FROM accounts WHERE username=$1
    	"""
    	await self.pool.execute(sql,login)

#----- Создание таблиц -----#

    async def create_table_users(self):
    	sql = '''
		        CREATE TABLE IF NOT EXISTS users(
		            id serial not null,
		            username text,
		            user_id integer PRIMARY KEY,
		            language text
		            )
		    '''
    	await self.pool.execute(sql)

    async def create_table_messages(self):
    	sql = '''
		    	CREATE TABLE IF NOT EXISTS messages(
		            id serial PRIMARY KEY,
		            username text,
		            user_id integer,
		            message text
		            )
		    '''
    	await self.pool.execute(sql)
    async def create_table_accounts(self):
    	sql = '''
		    	CREATE TABLE IF NOT EXISTS accounts(
		            id serial PRIMARY KEY,
		            username text,
		            password text
		            )
		    '''
    	await self.pool.execute(sql)

db = Database(loop)


#-------------------------------------------------------------------------------#

async def on_startup(dp):
	await bot.send_message(DEV_ID,"Бот успешно запущен")
	await db.create_table_users()
	await db.create_table_messages()
	await db.create_table_accounts()

async def on_shutdown(dp):
	pass

if __name__ == '__main__':
    executor.start_polling(dispatcher=dp,on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True)
	
