import os
import time
import telebot
import requests
import uuid
import random
import urllib.parse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException
from apify_client import ApifyClient
from flask import Flask, request

def encode_tags(tags):
    return '+'.join(urllib.parse.quote(tag) for tag in tags)

tags = ["1girl"]
api_key = os.getenv('GELBOROU_T')
user_id = os.getenv('user_id')
bot = telebot.TeleBot(os.getenv('TG_BOT'))
APIFY_API_TOKEN = os.getenv('APIFY_API')
CHANNEL_ID = os.getenv('CHANNEL_ID_T')
IDadmin = 617758940 # Make sure this is an integer

client = ApifyClient(APIFY_API_TOKEN)
photos_data = {}
previous_photo_data = {}  # Store previous photo data

def get_random_gelbooru_image(tags, api_key, user_id):
    params = {
        'page': 'dapi',
        's': 'post',
        'q': 'index',
        'json': 1,
        'tags': tags,
        'api_key': api_key,
        'user_id': user_id
    }
    response = requests.get("https://gelbooru.com/index.php", params=params)
    if response.ok:
        posts = response.json().get('post', [])
        if posts:
            random_post = random.choice(posts)
            image_url = random_post['file_url'] if random_post['file_url'].endswith(('jpg', 'jpeg', 'png')) else None
            source_url = random_post.get('source', 'Source not available')
            post_tags = random_post.get('tags', 'No tags')
            return response.json(), image_url, source_url, post_tags
    return {}, None, None, None

def get_random_image_url():
    global tags, api_key, user_id
    data, image_url, source_url, post_tags = get_random_gelbooru_image(" ".join(tags), api_key, user_id)
    if image_url:
        author = data['post'][0].get("tag_string_artist", "source")
        return image_url, author, source_url, post_tags
    return None, None, None, None

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
        image_url, author, source, post_tags = get_random_image_url()
        if not image_url:
            print("Image URL not found, retrying...")
            bot.send_message(IDadmin, f'Ошибка - ничего не найдено по тегам {tags}. Мб это из-за неправильных тегов, пропиши: /tag 1girl landscape ...time.sleep(10)')
            time.sleep(10)
            continue

        unique_id = str(uuid.uuid4())
        photos_data[unique_id] = {"url": image_url, "author": author, "source": source, "post_tags": post_tags}

        markup = InlineKeyboardMarkup()
        approve_button = InlineKeyboardButton("✅", callback_data=f"approve|{unique_id}")
        decline_button = InlineKeyboardButton("❌", callback_data=f"decline|{unique_id}")
        back_button = InlineKeyboardButton("↩️", callback_data="back")
        markup.add(approve_button, decline_button, back_button)

        author_link = f'<a href="{source}">{author}</a>' if source else f'{author}'

        try:
            bot.send_photo(IDadmin, image_url, caption=f'{author_link}\nTags: {post_tags}', reply_markup=markup, parse_mode='HTML')
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
    global previous_photo_data
    action, unique_id = call.data.split('|')
    photo_data = photos_data.get(unique_id)

    if photo_data:
        image_url = photo_data["url"]
        author = photo_data["author"]
        source = photo_data["source"]
        post_tags = photo_data["post_tags"]

        if action == "approve":
            author_link = f'<a href="{source}">{author}</a>' if source else f'{author}'
            bot.send_photo(CHANNEL_ID, image_url, caption=f'{author_link}', parse_mode='HTML')
            bot.answer_callback_query(call.id, "approve")
        elif action == "decline":
            bot.answer_callback_query(call.id, "decline")

        previous_photo_data = photo_data  # Save the current photo data as previous
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_photo_to_admin()
        del photos_data[unique_id]
    else:
        bot.answer_callback_query(call.id, "error.")

@bot.callback_query_handler(func=lambda call: call.data == 'back')
def handle_back(call):
    global previous_photo_data
    if previous_photo_data:
        image_url = previous_photo_data["url"]
        author = previous_photo_data["author"]
        source = previous_photo_data["source"]
        post_tags = previous_photo_data["post_tags"]

        unique_id = str(uuid.uuid4())
        photos_data[unique_id] = previous_photo_data

        markup = InlineKeyboardMarkup()
        approve_button = InlineKeyboardButton("✅", callback_data=f"approve|{unique_id}")
        decline_button = InlineKeyboardButton("❌", callback_data=f"decline|{unique_id}")
        markup.add(approve_button, decline_button)

        author_link = f'<a href="{source}">{author}</a>' if source else f'{author}'
        bot.send_photo(IDadmin, image_url, caption=f'{author_link}\nTags: {post_tags}', reply_markup=markup, parse_mode='HTML')
    else:
        bot.answer_callback_query(call.id, "No previous photo available.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('send'))
def send_photo_to_channel(call):
    _, photo_url = call.data.split('|')
    # Теперь используем правильную ссылку на твит в подписи
    tweet_url = photos_data.get(photo_url, {}).get('tweet_url', '')
    caption = f"<a href='{tweet_url}'>source</a>" if tweet_url else 'source'
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
        print("scrape done---")
        if photos:
            for photo in photos:
                unique_id = str(uuid.uuid4())
                photos_data[photo['media_url']] = {"media_url": photo['media_url'], "tweet_url": tweet_url}

                caption = f"<a href='{tweet_url}'>source</a>"
                markup = InlineKeyboardMarkup()
                send_button = InlineKeyboardButton("▶️", callback_data=f"send|{photo['media_url']}")
                markup.add(send_button)
                print("send---")
                bot.send_photo(message.chat.id, photo['media_url'], caption=caption, reply_markup=markup, parse_mode='HTML')
        else:
            bot.reply_to(message, "err(пиши 13.4).")
    except Exception as e:
        bot.reply_to(message, f"неправильная ссылка либо ошибка на стороне сервера. Пиши 13.4")
        print(e)

app = Flask(__name__)

@app.route('/' + os.getenv('TG_BOT'), methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_json())
    if update:
        bot.process_new_updates([update])
    return "!", 200

if __name__ == "__main__":
    bot.remove_webhook()
    webhook_url = os.getenv('WEBHOOK_URL')
    bot.set_webhook(url=webhook_url)
    app.run(host='0.0.0.0', port=8443)
