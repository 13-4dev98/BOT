import time
import telebot
import requests
import uuid
import random
import urllib.parse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException
from apify_client import ApifyClient

def encode_tags(tags):
    return '+'.join(urllib.parse.quote(tag) for tag in tags)

tags = ["1girl"]
encoded_tags = encode_tags(tags)
url_template = "https://danbooru.donmai.us/posts.json?limit=1000000&tags={tags}+rating:safe"

bot = telebot.TeleBot(TG_BOT)

APIFY_API_TOKEN = APIFY_API

CHANNEL_ID = CHANNEL_ID_T
IDadmin = IDadminT  # Make sure this is an integer

client = ApifyClient(APIFY_API_TOKEN)
photos_data = {}
bot.remove_webhook()

def get_random_image_url():
    global encoded_tags
    random.shuffle(tags)
    encoded_tags = encode_tags(tags[:2])
    response = requests.get(url_template.format(tags=encoded_tags))
    if response.status_code == 200:
        data = response.json()
        if data:
            random_post = random.choice(data)
            return random_post.get("file_url"), random_post.get("tag_string_artist", "No author"), random_post.get("source", "")
    return None, None, None

def scrape_tweet_photo(tweet_url):
    run_input = {
        "handles": [],
        "tweetsDesired": 1,
        "addUserInfo": True,
        "startUrls": [{"url": tweet_url}],
        "proxyConfig": {"useApifyProxy": True},
    }

    run = client.actor("u6ppkMWAx2E2MpEuF").call(run_input=run_input)

    photos = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        if 'media' in item and item['media']:
            for media_item in item['media']:
                if 'media_url' in media_item:
                    photo_info = {
                        "media_url": media_item['media_url'],
                        "tweet_url": tweet_url
                    }
                    photos.append(photo_info)

    return photos

def send_photo_to_admin():
    while True:
        image_url, author, source = get_random_image_url()
        if not image_url:
            print("Image URL not found, retrying...")
            bot.send_message(IDadmin, f'Ошибка - ничего не найдено по тегам {tags} . Мб это из-за неправильных тегов, пропиши: /tag 1girl landscape ...time.sleep(10)')
            time.sleep(10)
            continue

        unique_id = str(uuid.uuid4())
        photos_data[unique_id] = {"url": image_url, "author": author, "source": source}

        markup = InlineKeyboardMarkup()
        approve_button = InlineKeyboardButton("✅", callback_data=f"approve|{unique_id}")
        decline_button = InlineKeyboardButton("❌", callback_data=f"decline|{unique_id}")
        markup.add(approve_button, decline_button)

        author_link = f'<a href="{source}">{author}</a>' if source else f'{author}'

        try:
            bot.send_photo(IDadmin, image_url, caption=f'{author_link} \n \n #няшкі', reply_markup=markup, parse_mode='HTML')
            break  # Exit the loop if the photo is sent successfully
        except ApiTelegramException as e:
            if e.result_json['description'] == 'Bad Request: wrong file identifier/HTTP URL specified':
                print(f"Error sending photo: {e}. Retrying with a different image...")
                del photos_data[unique_id]
                get_random_image_url()

def restricted(func):
    def wrapper(message, *args, **kwargs):
        if message.from_user.id != IDadmin:
            bot.reply_to(message, "Access denied.")
            return
        return func(message, *args, **kwargs)
    return wrapper

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve') or call.data.startswith('decline'))
def callback_inline(call):
    action, unique_id = call.data.split('|')
    photo_data = photos_data.get(unique_id)

    if photo_data:
        image_url = photo_data["url"]
        author = photo_data["author"]
        source = photo_data["source"]

        if action == "approve":
            author_link = f'<a href="{source}">{author}</a>' if source else f'{author}'
            bot.send_photo(CHANNEL_ID, image_url, caption=f'{author_link}  \n \n #няшкі', parse_mode='HTML')
            bot.answer_callback_query(call.id, "approve")
        elif action == "decline":
            bot.answer_callback_query(call.id, "decline")

        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_photo_to_admin()
        del photos_data[unique_id]
    else:
        bot.answer_callback_query(call.id, "error.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('send'))
def send_photo_to_channel(call):
    _, photo_url = call.data.split('|')
    caption = f"<a href='{photo_url}'>source</a>"
    bot.send_photo(CHANNEL_ID, photo_url, caption=caption, parse_mode='HTML')
    bot.answer_callback_query(call.id, "Photo sent to channel")
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['alive'])
@restricted
def send_welcome(message):
    bot.reply_to(message, 'I am alive')

@bot.message_handler(commands=['start'])
@restricted
def send_welcome(message):
    bot.reply_to(message, "при нажатии на \n✅ фото будет отправлено в канал \n❌ фото будет удалено \n /alive что-бы проверить работу серверов. \n /tag что бы поменять тег \n/link для ссылки на твит \nесли что-то сломается, пишите 13.4")

@bot.message_handler(commands=['tag'])
@restricted
def change_tags(message):
    global tags, encoded_tags
    new_tags = message.text[len('/tag '):].strip().split()
    if new_tags:
        tags = new_tags
        bot.reply_to(message, f"Теги обновлены на: {' '.join(tags)} нажми на ❌ под прошлой фоткой для запуска цикла")
    else:
        bot.reply_to(message, f"Пожалуйста, укажите новые теги после команды /tag \n пример: 1girl landscape \n что бы выбрать анти-теги, перед тегом нужно поставить - \n пример : /tag 2girls yuri -azumanga \nтеги которые установлены сейчас: {' '.join(tags)} \n После принятия тегов нажми ❌ под прошлой фоткой (продолжение цикла)")

@bot.message_handler(commands=['link'])
@restricted
def send_welcome(message):
    bot.reply_to(message, " Отправь мне ссылку на твит, и я пришлю тебе фото из него.")

@bot.message_handler(func=lambda message: True)
@restricted
def handle_message(message):
    if 'twitter.com' not in message.text and 'x.com' not in message.text:
        bot.reply_to(message, 'Это не ссылка на твит.')
        return
    bot.reply_to(message, "wait... (+- 18 секунд)")
    tweet_url = message.text
    print("---tw link----")
    try:
        photos = scrape_tweet_photo(tweet_url)
        if photos:
            for photo in photos:
                caption = f"<a href='{photo['tweet_url']}'>source</a>  \n \n #няшкі"
                markup = InlineKeyboardMarkup()
                send_button = InlineKeyboardButton("▶️", callback_data=f"send|{photo['tweet_url']}")
                markup.add(send_button)
                bot.send_photo(message.chat.id, photo['tweet_url'], caption=caption, reply_markup=markup, parse_mode='HTML')
        else:
            bot.reply_to(message, "err(пиши 13.4).")
    except Exception as e:
        bot.reply_to(message, f"неправильная ссылка либо ошибка на стороне сервера. Пиши 13.4")

if __name__ == "__main__":
    while True:
        try:
            get_random_image_url()
            send_photo_to_admin()
            bot.polling(none_stop=True)

        except ApiTelegramException as e:
            print(f"Telegram API error occurred: {e}")
            get_random_image_url()
        except Exception as e:
            print(f"An error occurred: {e}")
            get_random_image_url()
