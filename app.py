import logging
from flask import Flask, request
import os
import asyncio
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from vps_reset_script import run_main as vps_reset_main, DEFAULT_COMMAND
import threading
import time
import requests
import datetime
import pytz
from ssh import handle_ssh_command, handle_exit_command, is_ssh_connected, ssh_sessions, ssh_timeouts
import random
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
AUTO_CONNECT_INTERVAL = os.getenv('AUTO_CONNECT_INTERVAL')
RENDER_APP_URL = os.getenv('RENDER_APP_URL')
RESET_INTERVAL_VARIATION = 10  # 默认为10分钟
FEEDBACK_GROUP_LINK = "https://t.me/+WIX6H-944HQzZmQ9"
CUSTOM_COMMAND = os.getenv('CUSTOM_COMMAND')
if CUSTOM_COMMAND is None or CUSTOM_COMMAND == '':
    CUSTOM_COMMAND = DEFAULT_COMMAND
CUSTOM_PATH_COMMAND = None

vps_reset_lock = threading.Lock()
is_resetting_vps = False
next_reset_time = None

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

def get_beijing_time(dt=None):
    beijing_tz = pytz.timezone('Asia/Shanghai')
    if dt is None:
        dt = datetime.datetime.now(pytz.UTC)
    elif dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(beijing_tz)

def generate_welcome_message():
    global CUSTOM_COMMAND
    CUSTOM_COMMAND = os.getenv('CUSTOM_COMMAND')
    if CUSTOM_COMMAND is None or CUSTOM_COMMAND == '':
        CUSTOM_COMMAND = DEFAULT_COMMAND
    return (
        "您好！以下是可用的命令：\n"
        "/start - 再次发送此帮助消息\n"
        "/reset - 触发 VPS 重置脚本\n"
        "/setcron <小时数> - 设置自动重置的时间间隔（例如：/setcron 24）\n"
        "/getcron - 获取当前自动重置的时间间隔和下次重置时间\n"
        "/setvartime <分钟数> - 设置重置时间的随机变化范围（例如：/setvartime 10）\n"
        "/ssh - 列出所有可用的 VPS 用户名\n"
        "/ssh <username> - 连接到指定的 VPS\n"
        "/exit - 退出当前 SSH 会话\n"
        "/setcommand - 查看要执行的自定义命令\n"
        "/setcommand <command> - 设置要执行的自定义命令（例如：/setcommand source ~/.profile && pm2 resurrect）\n"
        "/setpathcom [command] - 设置、查看或清除要在指定路径下执行的自定义命令\n"
        "   - 设置: /setpathcom pm2 resurrect\n"
        "   - 查看: /setpathcom\n"
        "   - 清除: /setpathcom clear"
    )

def create_feedback_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("问题反馈", url=FEEDBACK_GROUP_LINK, callback_data="feedback")
    ]])

def send_welcome_message_to_chat(bot):
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=welcome_message, reply_markup=reply_markup)

def start_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(generate_welcome_message())
        
def reset_vps_command(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) == TELEGRAM_CHAT_ID:
        update.message.reply_text('正在触发 VPS 重置脚本...')
        threading.Thread(target=reset_vps, args=(context.bot,)).start()
    else:
        update.message.reply_text('您没有权限使用此命令。')

def set_cron(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text('您没有权限使用此命令。')
        return

    if not context.args or not context.args[0].isdigit():
        update.message.reply_text('请提供有效的小时数，例如：/setcron 24')
        return

    interval = int(context.args[0])
    global AUTO_CONNECT_INTERVAL, next_reset_time, RESET_INTERVAL_VARIATION

    if RESET_INTERVAL_VARIATION >= interval * 60:
        update.message.reply_text(f'错误：当前偏差时间（{RESET_INTERVAL_VARIATION}分钟）大于或等于周期时间（{interval}小时）。请先使用 /setvartime 命令设置一个更小的偏差时间。')
        return

    AUTO_CONNECT_INTERVAL = str(interval)
    
    scheduler.remove_all_jobs()
    now = get_beijing_time()
    
    if interval > 0:
        next_reset_time = calculate_next_reset_time(now, interval)
        scheduler.add_job(scheduled_reset_vps, 'date', run_date=next_reset_time, args=[context.bot])
        update.message.reply_text(
            f'自动 VPS 重置间隔已设置为 {interval} 小时\n'
            f'重置时间随机变化范围: ±{RESET_INTERVAL_VARIATION} 分钟\n'
            f'下一次重置时间（已包含随机变化）：{next_reset_time.strftime("%Y-%m-%d %H:%M:%S")} (北京时间)'
        )
    else:
        next_reset_time = None
        update.message.reply_text('自动 VPS 重置已禁用')
    
    logger.info(f"自动 VPS 重置间隔已更新为 {interval} 小时，下一次重置时间：{next_reset_time}")

def get_cron(update: Update, context: CallbackContext) -> None:
    if AUTO_CONNECT_INTERVAL and int(AUTO_CONNECT_INTERVAL) > 0:
        now = get_beijing_time()
        
        message = f'当前自动 VPS 重置间隔为 {AUTO_CONNECT_INTERVAL} 小时\n'
        message += f'重置时间随机变化范围: ±{RESET_INTERVAL_VARIATION} 分钟\n'
        
        if next_reset_time:
            time_until_next_reset = next_reset_time - now
            
            message += f'下一次重置时间（已包含随机变化）：{next_reset_time.strftime("%Y-%m-%d %H:%M:%S")} (北京时间)\n'
            
            if time_until_next_reset.total_seconds() > 0:
                days, seconds = time_until_next_reset.days, time_until_next_reset.seconds
                hours, remainder = divmod(seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                message += f'距离下次重置还有：{days}天 {hours}小时 {minutes}分钟'
            else:
                message += '下次重置时间已过，正在重新调度...'
                set_cron(update, context)
        else:
            message += '下一次重置时间尚未设置'
        
        update.message.reply_text(message)
    else:
        update.message.reply_text('当前未设置自动 VPS 重置间隔')

def set_vartime(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text('您没有权限使用此命令。')
        return

    if not context.args or not context.args[0].isdigit():
        update.message.reply_text('请提供有效的分钟数，例如：/setvartime 10')
        return

    new_variation = int(context.args[0])
    global RESET_INTERVAL_VARIATION, AUTO_CONNECT_INTERVAL

    if AUTO_CONNECT_INTERVAL and int(AUTO_CONNECT_INTERVAL) > 0:
        if new_variation >= int(AUTO_CONNECT_INTERVAL) * 60:
            update.message.reply_text(f'错误：偏差时间（{new_variation}分钟）必须小于周期时间（{AUTO_CONNECT_INTERVAL}小时）')
            return

    RESET_INTERVAL_VARIATION = new_variation
    update.message.reply_text(f'重置时间随机变化范围已设置为 ±{RESET_INTERVAL_VARIATION} 分钟')

    if AUTO_CONNECT_INTERVAL and int(AUTO_CONNECT_INTERVAL) > 0:
        now = get_beijing_time()
        global next_reset_time
        next_reset_time = calculate_next_reset_time(now, int(AUTO_CONNECT_INTERVAL))
        scheduler.remove_all_jobs()
        scheduler.add_job(scheduled_reset_vps, 'date', run_date=next_reset_time, args=[context.bot])
        update.message.reply_text(
            f'自动 VPS 重置间隔保持为 {AUTO_CONNECT_INTERVAL} 小时\n'
            f'下一次重置时间（已包含新的随机变化）：{next_reset_time.strftime("%Y-%m-%d %H:%M:%S")} (北京时间)'
        )

def set_command(update: Update, context: CallbackContext) -> None:
    global CUSTOM_COMMAND
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text('您没有权限使用此命令。')
        return

    if not context.args:
        update.message.reply_text(f'要执行的自定义命令为：{CUSTOM_COMMAND}')
        return

    CUSTOM_COMMAND = ' '.join(context.args)
    update.message.reply_text(f'自定义命令已设置为：{CUSTOM_COMMAND}')

def set_path_command(update: Update, context: CallbackContext) -> None:
    global CUSTOM_PATH_COMMAND
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text('您没有权限使用此命令。')
        return

    if not context.args:
        # 查看当前设置
        if CUSTOM_PATH_COMMAND:
            update.message.reply_text(f'当前设置的 pathcom 命令是：{CUSTOM_PATH_COMMAND}')
        else:
            update.message.reply_text('当前没有设置 pathcom 命令。')
    elif context.args[0].lower() == 'clear':
        # 清除设置
        if CUSTOM_PATH_COMMAND:
            CUSTOM_PATH_COMMAND = None
            update.message.reply_text('pathcom 命令已清除。')
        else:
            update.message.reply_text('当前没有设置 pathcom 命令，无需清除。')
    else:
        # 设置新的命令
        CUSTOM_PATH_COMMAND = ' '.join(context.args)
        update.message.reply_text(f'自定义路径命令已设置为：{CUSTOM_PATH_COMMAND}')

def handle_message(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if is_ssh_connected(chat_id):
        ssh = ssh_sessions[chat_id]
        command = update.message.text
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            result = stdout.read().decode() + stderr.read().decode()
            update.message.reply_text(result or "命令执行完毕，无输出")
            
            if chat_id in ssh_timeouts:
                ssh_timeouts[chat_id].cancel()
            ssh_timeouts[chat_id] = threading.Timer(900, lambda: timeout_ssh_session(context.bot, chat_id))
            ssh_timeouts[chat_id].start()
        except Exception as e:
            update.message.reply_text(f"执行命令时出错：{str(e)}")
    else:
        send_welcome_message(update, context)

def send_welcome_message(update: Update, context: CallbackContext) -> None:
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    update.message.reply_text(welcome_message, reply_markup=reply_markup)

def setup_bot():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("reset", reset_vps_command))
    dp.add_handler(CommandHandler("setcron", set_cron))
    dp.add_handler(CommandHandler("getcron", get_cron))
    dp.add_handler(CommandHandler("setvartime", set_vartime))
    dp.add_handler(CommandHandler("ssh", handle_ssh_command))
    dp.add_handler(CommandHandler("exit", handle_exit_command))
    dp.add_handler(CommandHandler("setcommand", set_command))
    dp.add_handler(CommandHandler("setpathcom", set_path_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    return updater

bot_updater = setup_bot()

def log_and_send(bot, message):
    logger.info(message)
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

def reset_vps(bot):
    global is_resetting_vps
    with vps_reset_lock:
        if is_resetting_vps:
            log_and_send(bot, 'VPS 重置脚本已在运行中，请稍后再试。')
            return
        is_resetting_vps = True

    try:
        vps_reset_main(command=CUSTOM_COMMAND, global_path=CUSTOM_PATH_COMMAND)
    except Exception as e:
        log_and_send(bot, f'VPS 重置过程中出现错误：{str(e)}')
    finally:
        with vps_reset_lock:
            is_resetting_vps = False

def calculate_next_reset_time(current_time, interval_hours):
    base_time = current_time + datetime.timedelta(hours=interval_hours)
    variation_minutes = random.uniform(-RESET_INTERVAL_VARIATION, RESET_INTERVAL_VARIATION)
    return base_time + datetime.timedelta(minutes=variation_minutes)

def scheduled_reset_vps(bot):
    global next_reset_time
    current_time = get_beijing_time()
    log_and_send(bot, f'开始执行定时 VPS 重置... (当前北京时间: {current_time.strftime("%Y-%m-%d %H:%M:%S")})')
    success_count, total_count = vps_reset_main(send_messages=False, command=CUSTOM_COMMAND, global_path=CUSTOM_PATH_COMMAND)
    next_reset_time = calculate_next_reset_time(current_time, int(AUTO_CONNECT_INTERVAL))
    
    scheduler.remove_all_jobs()
    scheduler.add_job(scheduled_reset_vps, 'date', run_date=next_reset_time, args=[bot])
    
    log_and_send(bot, f"VPS 重置完成。成功执行命令的 VPS 数量：{success_count}/{total_count}。下一次重置时间: {next_reset_time.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_updater.bot)
    bot_updater.dispatcher.process_update(update)
    return 'OK'

@app.route('/')
def home():
    return "VPS 重置 Bot 正在运行！"

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

if __name__ == '__main__':
    webhook_set = set_webhook()
    
    if webhook_set:
        send_welcome_message_to_chat(bot_updater.bot)
    else:
        logger.error("Webhook 设置失败，不发送欢迎消息")
    
    if AUTO_CONNECT_INTERVAL and int(AUTO_CONNECT_INTERVAL) > 0:
        interval = int(AUTO_CONNECT_INTERVAL)
        now = get_beijing_time()
        next_reset_time = calculate_next_reset_time(now, interval)
        scheduler.add_job(scheduled_reset_vps, 'date', run_date=next_reset_time, args=[bot_updater.bot])
        scheduler.start()
        logger.info(f"自动 VPS 重置已启用，间隔为 {interval} 小时，下一次重置时间：{next_reset_time.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    else:
        logger.info("自动 VPS 重置未启用，可以使用 /setcron 命令来设置")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
