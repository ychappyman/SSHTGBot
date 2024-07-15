import logging
from flask import Flask, request
import os
import asyncio
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from group_run import run_main as host_execute_main, DEFAULT_COMMAND
import threading
import time
import requests
import datetime
import pytz
from ssh import handle_ssh_command, handle_exit_command, is_ssh_connected, ssh_sessions, ssh_timeouts
import random
from apscheduler.schedulers.background import BackgroundScheduler
from upload_keys import upload_public_keys
import json
from translations import get_translation
from language_manager import language_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

LANGUAGE = os.getenv('LANGUAGE', 'zh')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
AUTO_CONNECT_INTERVAL = os.getenv('AUTO_CONNECT_INTERVAL', '24')
RENDER_APP_URL = os.getenv('RENDER_APP_URL')
RESET_INTERVAL_VARIATION = 10  # 默认为10分钟
FEEDBACK_GROUP_LINK = "https://t.me/+WIX6H-944HQzZmQ9"
CUSTOM_COMMAND = os.getenv('CUSTOM_COMMAND') or DEFAULT_COMMAND
CUSTOM_PATH_COMMAND = None

host_execute_lock = threading.Lock()
is_executing_host = False
next_execute_time = None

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

def get_beijing_time(dt=None):
    beijing_tz = pytz.timezone('Asia/Shanghai')
    if dt is None:
        dt = datetime.datetime.now(pytz.UTC)
    elif dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(beijing_tz)

def generate_welcome_message():
    return get_translation('welcome_message', LANGUAGE)

def create_feedback_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_translation('feedback_button', LANGUAGE), url=FEEDBACK_GROUP_LINK, callback_data="feedback")
    ]])

def send_welcome_message_to_chat(bot):
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=welcome_message, reply_markup=reply_markup)

def start_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(generate_welcome_message())
        
def execute_host_command(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) == TELEGRAM_CHAT_ID:
        update.message.reply_text(get_translation('executing_command', LANGUAGE))
        threading.Thread(target=execute_host, args=(context.bot,)).start()
    else:
        update.message.reply_text(get_translation('no_permission', LANGUAGE))

def set_cron(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text(get_translation('no_permission', LANGUAGE))
        return

    global AUTO_CONNECT_INTERVAL, next_execute_time, RESET_INTERVAL_VARIATION

    if not context.args:
        # Display current settings
        interval = int(AUTO_CONNECT_INTERVAL)
        message = get_translation('current_settings', LANGUAGE).format(interval=interval, variation=RESET_INTERVAL_VARIATION)
        
        if next_execute_time:
            now = get_beijing_time()
            time_until_next_execute = next_execute_time - now
            
            message += get_translation('next_execution_time', LANGUAGE).format(
                beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
                utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
            )
            
            if time_until_next_execute.total_seconds() > 0:
                days, seconds = time_until_next_execute.days, time_until_next_execute.seconds
                hours, remainder = divmod(seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                message += get_translation('time_until_next_execution', LANGUAGE).format(days=days, hours=hours, minutes=minutes)
            else:
                message += get_translation('next_execution_passed', LANGUAGE)
        else:
            message += get_translation('next_execution_not_set', LANGUAGE)
        
        update.message.reply_text(message)
        return

    if not context.args[0].isdigit():
        update.message.reply_text(get_translation('invalid_hours', LANGUAGE))
        return

    interval = int(context.args[0])

    if RESET_INTERVAL_VARIATION >= interval * 60:
        update.message.reply_text(get_translation('variation_too_large', LANGUAGE).format(variation=RESET_INTERVAL_VARIATION, interval=interval))
        return

    AUTO_CONNECT_INTERVAL = str(interval)
    
    scheduler.remove_all_jobs()
    now = get_beijing_time()
    
    next_execute_time = calculate_next_execute_time(now, interval)
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[context.bot])
    update.message.reply_text(
        get_translation('cron_set', LANGUAGE).format(
            interval=interval,
            variation=RESET_INTERVAL_VARIATION,
            beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
            utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    
    logger.info(f"执行命令周期已更新为 {interval} 小时，下一次执行命令时间：{next_execute_time}")

def set_vartime(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text(get_translation('no_permission', LANGUAGE))
        return

    global RESET_INTERVAL_VARIATION, AUTO_CONNECT_INTERVAL

    if not context.args:
        update.message.reply_text(get_translation('current_variation', LANGUAGE).format(variation=RESET_INTERVAL_VARIATION))
        return

    if not context.args[0].isdigit():
        update.message.reply_text(get_translation('invalid_minutes', LANGUAGE))
        return

    new_variation = int(context.args[0])

    if int(AUTO_CONNECT_INTERVAL) * 60 <= new_variation:
        update.message.reply_text(get_translation('variation_too_large', LANGUAGE).format(variation=new_variation, interval=AUTO_CONNECT_INTERVAL))
        return

    RESET_INTERVAL_VARIATION = new_variation
    update.message.reply_text(get_translation('variation_set', LANGUAGE).format(variation=RESET_INTERVAL_VARIATION))

    now = get_beijing_time()
    global next_execute_time
    next_execute_time = calculate_next_execute_time(now, int(AUTO_CONNECT_INTERVAL))
    scheduler.remove_all_jobs()
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[context.bot])
    update.message.reply_text(
        get_translation('next_execution_updated', LANGUAGE).format(
            interval=AUTO_CONNECT_INTERVAL,
            beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
            utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
        )
    )

def set_command(update: Update, context: CallbackContext) -> None:
    global CUSTOM_COMMAND
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text(get_translation('no_permission', LANGUAGE))
        return

    if not context.args:
        update.message.reply_text(get_translation('custom_command', LANGUAGE).format(command=CUSTOM_COMMAND))
        return

    CUSTOM_COMMAND = ' '.join(context.args)
    update.message.reply_text(get_translation('custom_command_set', LANGUAGE).format(command=CUSTOM_COMMAND))

def set_path_command(update: Update, context: CallbackContext) -> None:
    global CUSTOM_PATH_COMMAND
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text(get_translation('no_permission', LANGUAGE))
        return

    if not context.args:
        if CUSTOM_PATH_COMMAND:
            update.message.reply_text(get_translation('current_pathcom', LANGUAGE).format(command=CUSTOM_PATH_COMMAND))
        else:
            update.message.reply_text(get_translation('no_pathcom', LANGUAGE))
    elif context.args[0].lower() == 'clear':
        if CUSTOM_PATH_COMMAND:
            CUSTOM_PATH_COMMAND = None
            update.message.reply_text(get_translation('pathcom_cleared', LANGUAGE))
        else:
            update.message.reply_text(get_translation('no_pathcom_to_clear', LANGUAGE))
    else:
        CUSTOM_PATH_COMMAND = ' '.join(context.args)
        update.message.reply_text(get_translation('pathcom_set', LANGUAGE).format(command=CUSTOM_PATH_COMMAND))
        
def handle_message(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if is_ssh_connected(chat_id):
        ssh = ssh_sessions[chat_id]
        command = update.message.text
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            result = stdout.read().decode() + stderr.read().decode()
            update.message.reply_text(result or get_translation('command_executed', LANGUAGE))
            
            if chat_id in ssh_timeouts:
                ssh_timeouts[chat_id].cancel()
            ssh_timeouts[chat_id] = threading.Timer(900, lambda: timeout_ssh_session(context.bot, chat_id))
            ssh_timeouts[chat_id].start()
        except Exception as e:
            update.message.reply_text(get_translation('command_error', LANGUAGE).format(error=str(e)))
    else:
        send_welcome_message(update, context)

def send_welcome_message(update: Update, context: CallbackContext) -> None:
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    update.message.reply_text(welcome_message, reply_markup=reply_markup)

def change_language(update: Update, context: CallbackContext) -> None:
    global LANGUAGE
    if len(context.args) == 1:
        new_language = context.args[0].lower()
        if new_language in ['zh', 'en']:
            LANGUAGE = new_language
            language_manager.set_language(LANGUAGE)
            update.message.reply_text(get_translation('language_changed', LANGUAGE).format(language=LANGUAGE))
        else:
            update.message.reply_text(get_translation('language_not_supported', LANGUAGE))
    else:
        current_language_name = "中文" if language_manager.get_language() == "zh" else "English"
        update.message.reply_text(get_translation('current_language', LANGUAGE).format(language=current_language_name))
        update.message.reply_text(get_translation('language_usage', LANGUAGE))

def setup_bot():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("grouprun", execute_host_command))
    dp.add_handler(CommandHandler("setcron", set_cron))
    dp.add_handler(CommandHandler("setvartime", set_vartime))
    dp.add_handler(CommandHandler("ssh", handle_ssh_command))
    dp.add_handler(CommandHandler("exit", handle_exit_command))
    dp.add_handler(CommandHandler("setcommand", set_command))
    dp.add_handler(CommandHandler("setpathcom", set_path_command))
    dp.add_handler(CommandHandler("uploadkeys", upload_public_keys))
    dp.add_handler(CommandHandler("language", change_language))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    return updater

bot_updater = setup_bot()

def log_and_send(bot, message):
    logger.info(message)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

def execute_host(bot):
    global is_executing_host
    with host_execute_lock:
        if is_executing_host:
            log_and_send(bot, get_translation('executing_command', LANGUAGE))
            return
        is_executing_host = True

    try:
        host_execute_main(command=CUSTOM_COMMAND, global_path=CUSTOM_PATH_COMMAND)
    except Exception as e:
        log_and_send(bot, get_translation('command_error', LANGUAGE).format(error=str(e)))
    finally:
        with host_execute_lock:
            is_executing_host = False

def calculate_next_execute_time(current_time, interval_hours):
    base_time = current_time + datetime.timedelta(hours=interval_hours)
    variation_minutes = random.uniform(-RESET_INTERVAL_VARIATION, RESET_INTERVAL_VARIATION)
    return base_time + datetime.timedelta(minutes=variation_minutes)

def scheduled_execute_host(bot):
    global next_execute_time
    current_time = get_beijing_time()
    log_and_send(bot, get_translation('scheduled_execution_start', LANGUAGE).format(
        beijing_time=current_time.strftime("%Y-%m-%d %H:%M:%S"),
        utc_time=current_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
    ))
    success_count, total_count = host_execute_main(send_messages=False, command=CUSTOM_COMMAND, global_path=CUSTOM_PATH_COMMAND)
    next_execute_time = calculate_next_execute_time(current_time, int(AUTO_CONNECT_INTERVAL))
    
    scheduler.remove_all_jobs()
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[bot])
    
    log_and_send(bot, get_translation('scheduled_execution_complete', LANGUAGE).format(
        success_count=success_count,
        total_count=total_count,
        next_time=next_execute_time.strftime('%Y-%m-%d %H:%M:%S'),
        next_time_utc=next_execute_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    ))

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_updater.bot)
    bot_updater.dispatcher.process_update(update)
    return 'OK'

@app.route('/')
def home():
    return get_translation('bot_running', LANGUAGE)

def set_webhook():
    if not RENDER_APP_URL:
        logger.error("错误：RENDER_APP_URL 环境变量未设置")
        return False

    webhook_url = f"{RENDER_APP_URL}/{TELEGRAM_BOT_TOKEN}"
    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}"
    response = requests.get(telegram_api_url)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("ok"):
            logger.info("Webhook 设置成功")
            return True
        else:
            logger.error(f"Webhook 设置失败: {result.get('description')}")
            return False
    else:
        logger.error(f"请求失败，状态码: {response.status_code}")
        return False

def get_account_info(identifier):
    accounts = json.loads(ACCOUNTS_JSON)
    for account in accounts:
        if account.get('customhostname', '').lower() == identifier.lower() or \
           f"{account.get('ssluser', account.get('username'))}@{account.get('sslhost', account.get('hostname'))}".lower() == identifier.lower():
            return account
    return None

if __name__ == '__main__':
    webhook_set = set_webhook()
    
    if webhook_set:
        send_welcome_message_to_chat(bot_updater.bot)
    else:
        logger.error(get_translation('webhook_setup_failed', LANGUAGE))
    
    interval = int(AUTO_CONNECT_INTERVAL)
    now = get_beijing_time()
    next_execute_time = calculate_next_execute_time(now, interval)
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[bot_updater.bot])
    scheduler.start()
    logger.info(f"定时执行命令已启用，间隔为 {interval} 小时，下一次执行命令时间：北京时间 {next_execute_time.strftime('%Y-%m-%d %H:%M:%S')}(UTC时间：{next_execute_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')})")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
