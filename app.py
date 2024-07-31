import logging
from quart import Quart, request
import os
import asyncio
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from group_run import run_main as host_execute_main, DEFAULT_COMMAND, get_target_accounts
import datetime
import pytz
import ssh
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from upload_keys import upload_public_keys
import json
import re
from translations import get_translation
from language_manager import language_manager
import aiohttp
import warnings
from cryptography.utils import CryptographyDeprecationWarning

# 忽略 cryptography 的弃用警告
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Quart(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
AUTO_CONNECT_INTERVAL = os.getenv('AUTO_CONNECT_INTERVAL', '24')
RENDER_APP_URL = os.getenv('RENDER_APP_URL')
RESET_INTERVAL_VARIATION = 10  # 默认为10分钟
FEEDBACK_GROUP_LINK = "https://t.me/+WIX6H-944HQzZmQ9"
CUSTOM_COMMAND = os.getenv('CUSTOM_COMMAND') or DEFAULT_COMMAND
CRON_TASKS_JSON = os.getenv('CRON_TASKS_JSON')
TIME_MODE = os.getenv('TIME_MODE', 'hour')  # 新增：默认为小时模式
LANGUAGE = os.getenv('LANGUAGE', 'zh')

host_execute_lock = asyncio.Lock()
is_executing_host = False
next_execute_time = None

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

# 全局变量
application = None

def get_beijing_time(dt=None):
    beijing_tz = pytz.timezone('Asia/Shanghai')
    if dt is None:
        dt = datetime.datetime.now(pytz.UTC)
    elif dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(beijing_tz)

def generate_welcome_message():
    current_mode = get_translation('hour_mode') if TIME_MODE == "hour" else get_translation('minute_mode')
    welcome_message = get_translation('welcome_message')
    return welcome_message.format(
        time_mode=current_mode,
        unit=get_translation('hour') if TIME_MODE == 'hour' else get_translation('minute'),
        variation_unit=get_translation('minute') if TIME_MODE == 'hour' else get_translation('second')
    )

def create_feedback_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_translation('feedback_button'), url=FEEDBACK_GROUP_LINK, callback_data="feedback")
    ]])

async def send_welcome_message_to_chat(bot):
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=welcome_message, reply_markup=reply_markup)

async def start_command(update: Update, context) -> None:
    await update.message.reply_text(generate_welcome_message())

async def execute_host_command(update: Update, context) -> None:
    if str(update.message.chat_id) == TELEGRAM_CHAT_ID:
        if not context.args:
            await update.message.reply_text(get_translation('grouprun_usage'))
            return
        
        command = context.args[0]
        target = 'all'
        if len(context.args) > 1:
            target = ' '.join(context.args[1:])
        
        await update.message.reply_text(get_translation('executing_command'))
        asyncio.create_task(execute_host(context.bot, command, target))
    else:
        await update.message.reply_text(get_translation('no_permission'))

async def execute_default_command(update: Update, context) -> None:
    if str(update.message.chat_id) == TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('executing_default_command'))
        asyncio.create_task(execute_host(context.bot, CUSTOM_COMMAND, 'all'))
    else:
        await update.message.reply_text(get_translation('no_permission'))

async def set_cron(update: Update, context) -> None:
    global AUTO_CONNECT_INTERVAL, next_execute_time, RESET_INTERVAL_VARIATION, TIME_MODE

    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    if not context.args:
        interval = int(AUTO_CONNECT_INTERVAL)
        message = get_translation('current_settings', time_mode=TIME_MODE).format(
            interval=interval,
            variation=RESET_INTERVAL_VARIATION,
            interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
            variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
        )
        
        if next_execute_time:
            now = get_beijing_time()
            time_until_next_execute = next_execute_time - now
            
            message += get_translation('next_execution_time').format(
                beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
                utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
            )

            if time_until_next_execute.total_seconds() > 0:
                days, seconds = time_until_next_execute.days, time_until_next_execute.seconds
                hours, remainder = divmod(seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                if TIME_MODE == "hour":
                    message += get_translation('time_until_next_execution').format(days=days, hours=hours, minutes=minutes)
                else:
                    total_minutes = days * 24 * 60 + hours * 60 + minutes
                    message += get_translation('time_until_next_execution_minutes').format(minutes=total_minutes)
            else:
                message += get_translation('next_execution_passed')
        else:
            message += get_translation('next_execution_not_set')
        
        await update.message.reply_text(message)
        return

    if not context.args[0].isdigit():
        await update.message.reply_text(get_translation('invalid_time_unit', time_mode=TIME_MODE))
        return

    interval = int(context.args[0])

    if interval == 0:
        # 关闭循环
        AUTO_CONNECT_INTERVAL = '0'
        scheduler.remove_job('main_execution')
        next_execute_time = None
        await update.message.reply_text(get_translation('cron_disabled'))
        return

    if TIME_MODE == "hour":
        if RESET_INTERVAL_VARIATION >= interval * 60:
            await update.message.reply_text(get_translation('variation_too_large', time_mode=TIME_MODE).format(
                variation=RESET_INTERVAL_VARIATION,
                interval=interval,
                interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
                variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
            ))
            return
    else:  # minute mode
        if RESET_INTERVAL_VARIATION >= interval * 60:
            await update.message.reply_text(get_translation('variation_too_large', time_mode=TIME_MODE).format(
                variation=RESET_INTERVAL_VARIATION,
                interval=interval,
                interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
                variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
            ))
            return

    AUTO_CONNECT_INTERVAL = str(interval)
    
    # 只更新主要的定时执行任务，不影响其他任务
    main_job = scheduler.get_job('main_execution')
    if main_job:
        scheduler.remove_job('main_execution')
    
    now = get_beijing_time()
    next_execute_time = calculate_next_execute_time(now, interval)
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[context.bot], id='main_execution')
    
    await update.message.reply_text(
        get_translation('cron_set', time_mode=TIME_MODE).format(
            interval=interval,
            variation=RESET_INTERVAL_VARIATION,
            beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
            utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S"),
            interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
            variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
        )
    )
    
    logger.info(f"执行命令周期已更新为 {interval} {'小时' if TIME_MODE == 'hour' else '分钟'}，下一次执行命令时间：{next_execute_time}")

async def set_vartime(update: Update, context) -> None:
    global RESET_INTERVAL_VARIATION, AUTO_CONNECT_INTERVAL, next_execute_time, TIME_MODE

    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    if not context.args:
        await update.message.reply_text(get_translation('current_variation', time_mode=TIME_MODE).format(
            variation=RESET_INTERVAL_VARIATION,
            variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
        ))
        return

    if not context.args[0].isdigit():
        await update.message.reply_text(get_translation('invalid_time_unit', time_mode=TIME_MODE))
        return

    new_variation = int(context.args[0])

    if TIME_MODE == "hour":
        if int(AUTO_CONNECT_INTERVAL) * 60 <= new_variation:
            await update.message.reply_text(get_translation('variation_too_large', time_mode=TIME_MODE).format(
                variation=new_variation,
                interval=AUTO_CONNECT_INTERVAL,
                interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
                variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
            ))
            return
    else:  # minute mode
        if int(AUTO_CONNECT_INTERVAL) * 60 <= new_variation:
            await update.message.reply_text(get_translation('variation_too_large', time_mode=TIME_MODE).format(
                variation=new_variation,
                interval=AUTO_CONNECT_INTERVAL,
                interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
                variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
            ))
            return

    RESET_INTERVAL_VARIATION = new_variation
    await update.message.reply_text(get_translation('variation_set', time_mode=TIME_MODE).format(
        variation=RESET_INTERVAL_VARIATION,
        variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
    ))

    now = get_beijing_time()
    next_execute_time = calculate_next_execute_time(now, int(AUTO_CONNECT_INTERVAL))
    scheduler.remove_all_jobs()
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[context.bot])
    await update.message.reply_text(
        get_translation('next_execution_updated', time_mode=TIME_MODE).format(
            interval=AUTO_CONNECT_INTERVAL,
            beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
            utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S"),
            interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes')
        )
    )

async def set_command(update: Update, context) -> None:
    global CUSTOM_COMMAND
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    if not context.args:
        await update.message.reply_text(get_translation('custom_command').format(command=CUSTOM_COMMAND))
        return

    CUSTOM_COMMAND = ' '.join(context.args)
    await update.message.reply_text(get_translation('custom_command_set').format(command=CUSTOM_COMMAND))

async def change_language(update: Update, context) -> None:
    if len(context.args) == 1:
        new_language = context.args[0].lower()
        if new_language in ['zh', 'en']:
            language_manager.set_language(new_language)
            await update.message.reply_text(get_translation('language_changed').format(language=new_language))
            # 在这里添加发送欢迎消息的代码
            await send_welcome_message(update, context)
        else:
            await update.message.reply_text(get_translation('language_not_supported'))
    else:
        current_language_name = "中文" if language_manager.get_language() == "zh" else "English"
        await update.message.reply_text(get_translation('current_language').format(language=current_language_name))
        await update.message.reply_text(get_translation('language_usage'))

async def switch_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global TIME_MODE, AUTO_CONNECT_INTERVAL, RESET_INTERVAL_VARIATION, next_execute_time
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    # 保存当前任务的状态
    current_tasks = load_tasks()
    task_statuses = {}
    for task in current_tasks['tasks']:
        job = scheduler.get_job(f"task_{task['id']}")
        task_statuses[task['id']] = job.next_run_time is not None if job else False

    # 切换模式
    TIME_MODE = "minute" if TIME_MODE == "hour" else "hour"
    current_mode = get_translation('hour_mode') if TIME_MODE == "hour" else get_translation('minute_mode')
    
    # 删除所有现有任务
    scheduler.remove_all_jobs()
    
    # 重新加载所有任务
    for task in current_tasks['tasks']:
        job = await schedule_task(task)
        
        # 恢复任务的原始状态
        if not task_statuses.get(task['id'], True):
            job.pause()
    
    # 更新主要的定时执行任务
    interval = int(AUTO_CONNECT_INTERVAL)
    now = get_beijing_time()
    next_execute_time = calculate_next_execute_time(now, interval)
    
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[context.bot], id='main_execution')
    
    # 准备并发送切换模式的消息
    mode_switched_message = get_translation('mode_switched').format(time_mode=current_mode)
    next_execution_message = get_translation('next_execution_updated', time_mode=TIME_MODE).format(
        interval=interval,
        beijing_time=next_execute_time.strftime("%Y-%m-%d %H:%M:%S"),
        utc_time=next_execute_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S"),
        interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes')
    )
    
    full_message = f"{mode_switched_message}\n\n{next_execution_message}"
    await update.message.reply_text(full_message)
    
    # 记录日志
    logger.info(f"时间单位模式已切换为 {current_mode}。所有任务已更新并保持原有状态。下一次主要执行时间：{next_execute_time}")
    
    # 自动执行 /listtasks 命令
    await list_tasks(update, context)

    # 保存更新后的任务
    save_tasks(current_tasks)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Sorry, something went wrong. The error has been logged and we'll look into it.")

async def setup_bot():
    global application
    if application is None:
        application = (
            ApplicationBuilder()
            .token(TELEGRAM_BOT_TOKEN)
            .build()
        )
        await application.initialize()
        await application.start()
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("grouprun", execute_host_command))
        application.add_handler(CommandHandler("grouprundefault", execute_default_command))
        application.add_handler(CommandHandler("setcron", set_cron))
        application.add_handler(CommandHandler("setvartime", set_vartime))
        application.add_handler(CommandHandler("ssh", ssh.handle_ssh_command))
        application.add_handler(CommandHandler("exit", ssh.handle_exit_command))
        application.add_handler(CommandHandler("setcommand", set_command))
        application.add_handler(CommandHandler("uploadkeys", upload_public_keys))
        application.add_handler(CommandHandler("language", change_language))
        application.add_handler(CommandHandler("addtask", add_task))
        application.add_handler(CommandHandler("listtasks", list_tasks))
        application.add_handler(CommandHandler("removetask", remove_task))
        application.add_handler(CommandHandler("pausetask", pause_task))
        application.add_handler(CommandHandler("resumetask", resume_task))
        application.add_handler(CommandHandler("switchmode", switch_mode))  # 新增：切换时间单位模式
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
    
    return application

async def log_and_send(bot, message):
    logger.info(message)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

async def execute_host(bot, command, target='all'):
    global is_executing_host
    async with host_execute_lock:
        if is_executing_host:
            await log_and_send(bot, get_translation('executing_command'))
            return
        is_executing_host = True

    try:
        await host_execute_main(command=command, target=target, send_messages=True)
    except Exception as e:
        await log_and_send(bot, get_translation('command_error').format(error=str(e)))
    finally:
        async with host_execute_lock:
            is_executing_host = False

def calculate_next_execute_time(current_time, interval):
    if TIME_MODE == "hour":
        base_time = current_time + datetime.timedelta(hours=interval)
        variation_minutes = random.uniform(-RESET_INTERVAL_VARIATION, RESET_INTERVAL_VARIATION)
        return base_time + datetime.timedelta(minutes=variation_minutes)
    else:  # minute mode
        base_time = current_time + datetime.timedelta(minutes=interval)
        variation_seconds = random.uniform(-RESET_INTERVAL_VARIATION, RESET_INTERVAL_VARIATION)
        return base_time + datetime.timedelta(seconds=variation_seconds)

async def scheduled_execute_host(bot):
    global next_execute_time
    current_time = get_beijing_time()
    await log_and_send(bot, get_translation('scheduled_execution_start').format(
        beijing_time=current_time.strftime("%Y-%m-%d %H:%M:%S"),
        utc_time=current_time.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
    ))
    success_count, total_count = await host_execute_main(send_messages=False, command=CUSTOM_COMMAND)
    next_execute_time = calculate_next_execute_time(current_time, int(AUTO_CONNECT_INTERVAL))
    
    scheduler.remove_all_jobs()
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[bot])
    
    await log_and_send(bot, get_translation('scheduled_execution_complete').format(
        success_count=success_count,
        total_count=total_count,
        next_time=next_execute_time.strftime('%Y-%m-%d %H:%M:%S'),
        next_time_utc=next_execute_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    ))

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
async def webhook():
    global application
    if application is None:
        application = await setup_bot()
    
    update = Update.de_json(await request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'OK'

@app.route('/')
async def home():
    return get_translation('bot_running')

async def set_webhook():
    if not RENDER_APP_URL:
        logger.error("错误：RENDER_APP_URL 环境变量未设置")
        return False

    webhook_url = f"{RENDER_APP_URL}/{TELEGRAM_BOT_TOKEN}"
    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(telegram_api_url) as response:
            if response.status == 200:
                result = await response.json()
                if result.get("ok"):
                    logger.info("Webhook 设置成功")
                    return True
                else:
                    logger.error(f"Webhook 设置失败: {result.get('description')}")
                    return False
            else:
                logger.error(f"请求失败，状态码: {response.status}")
                return False

def get_account_info(identifier):
    accounts = json.loads(ACCOUNTS_JSON)
    for account in accounts:
        if account.get('customhostname', '').lower() == identifier.lower() or \
           f"{account.get('ssluser', account.get('username'))}@{account.get('sslhost', account.get('hostname'))}".lower() == identifier.lower():
            return account
    return None

@app.before_serving
async def startup():
    global application, next_execute_time
    application = await setup_bot()
    webhook_set = await set_webhook()
    
    if webhook_set:
        await send_welcome_message_to_chat(application.bot)
    else:
        logger.error(get_translation('webhook_setup_failed'))
    
    interval = int(AUTO_CONNECT_INTERVAL)
    now = get_beijing_time()
    next_execute_time = calculate_next_execute_time(now, interval)
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[application.bot], id='main_execution')
    
    # 加载并调度所有任务
    tasks = load_tasks()
    for task in tasks['tasks']:
        await schedule_task(task)
    
    scheduler.start()
    logger.info(f"定时执行命令已启用，间隔为 {interval} {'小时' if TIME_MODE == 'hour' else '分钟'}，下一次执行命令时间：北京时间 {next_execute_time.strftime('%Y-%m-%d %H:%M:%S')}(UTC时间：{next_execute_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')})")

@app.after_serving
async def shutdown():
    global application
    if application:
        await application.stop()
    scheduler.shutdown()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.text:
        return

    chat_id = update.effective_chat.id
    message_text = update.effective_message.text
    
    # 检查是否正在等待 SSH 密码
    if context.user_data.get('awaiting_ssh_password'):
        await ssh.handle_password_input(update, context)
        return

    # 检查是否有活跃的 SSH 连接
    if ssh.is_ssh_connected(chat_id):
        await ssh.handle_ssh_command_execution(update, context)
        return

    # 处理命令
    if message_text.startswith('/'):
        command = message_text.split()[0].lower()
        valid_commands = ['/start', '/grouprun', '/grouprundefault', '/setcron', '/setvartime', 
                          '/ssh', '/exit', '/setcommand', '/uploadkeys', '/language', '/addtask', 
                          '/listtasks', '/removetask', '/pausetask', '/resumetask', '/switchmode']
        
        if command not in valid_commands:
            await update.effective_message.reply_text(get_translation('unknown_command'))
            return
        # 如果是有效命令，让它继续传递给相应的命令处理器
        return
    
    # 处理非命令消息
    await send_welcome_message(update, context)
        
async def send_welcome_message(update: Update, context) -> None:
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def schedule_task(task):
    interval = task['interval']
    variation = task['variation']
    
    async def task_function():
        task_id = task['id']
        command = task['command']
        target = task['target']
        now = get_beijing_time()
        await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=get_translation('task_execution_start').format(
                task_id=task_id,
                target=target,
                command=command,
                beijing_time=now.strftime("%Y-%m-%d %H:%M:%S"),
                utc_time=now.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        
        success_count, total_count = await host_execute_main(command=command, target=target, send_messages=False)
        
        next_run = calculate_next_execute_time(now, interval)
        await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=get_translation('task_execution_complete').format(
                task_id=task_id,
                target=target,
                command=command,
                success_count=success_count,
                total_count=total_count,
                next_run_beijing=next_run.strftime("%Y-%m-%d %H:%M:%S"),
                next_run_utc=next_run.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
            )
        )
    
    trigger = IntervalTrigger(
        hours=interval if TIME_MODE == "hour" else 0,
        minutes=interval if TIME_MODE == "minute" else 0,
        jitter=variation * 60 if TIME_MODE == "hour" else variation
    )
    
    job = scheduler.add_job(
        task_function,
        trigger=trigger,
        id=f"task_{task['id']}",
        replace_existing=True
    )
    return job

def load_accounts():
    if ACCOUNTS_JSON:
        try:
            return json.loads(ACCOUNTS_JSON)
        except json.JSONDecodeError:
            logger.error("Failed to parse ACCOUNTS_JSON")
    return []

def load_host_groups():
    if CRON_TASKS_JSON:
        try:
            cron_tasks = json.loads(CRON_TASKS_JSON)
            return cron_tasks.get("host_groups", {})
        except json.JSONDecodeError:
            logger.error("Failed to parse CRON_TASKS_JSON")
    return {}

def validate_target(target):
    accounts = load_accounts()
    host_groups = load_host_groups()
    
    valid_hosts = set(account.get('customhostname', '').lower() for account in accounts if 'customhostname' in account)
    valid_hosts.update(f"{account.get('ssluser', account.get('username'))}@{account.get('sslhost', account.get('hostname'))}".lower() for account in accounts)
    
    targets = target.split(',')
    for t in targets:
        t = t.strip().lower()
        if t == 'all':
            continue
        if t.startswith('+') or t.startswith('-'):
            try:
                int(t[1:])
                continue
            except ValueError:
                return False
        if t.startswith('group:'):
            group_name = t[6:]
            if group_name not in host_groups:
                return False
        elif t not in valid_hosts:
            return False
    return True

def validate_task(task):
    required_fields = ['id', 'command', 'interval', 'variation', 'target']
    for field in required_fields:
        if field not in task:
            logger.warning(f"Task is missing required field: {field}")
            return False
    return True

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        logger.error("Received update without effective_chat")
        return

    if str(update.effective_chat.id) != TELEGRAM_CHAT_ID:
        await update.effective_chat.send_message(get_translation('no_permission'))
        return

    if not update.message or not update.message.text:
        logger.error("Received update without message text")
        await update.effective_chat.send_message(get_translation('invalid_command'))
        return

    args = re.split(r'\s+', update.message.text.strip())[1:]
    
    if len(args) < 3:
        time_mode = get_translation('hour_mode') if TIME_MODE == "hour" else get_translation('minute_mode')
        interval_unit = get_translation('hour') if TIME_MODE == 'hour' else get_translation('minute')
        variation_unit = get_translation('minute') if TIME_MODE == 'hour' else get_translation('second')
    
        usage_message = get_translation('addtask_usage').format(
            time_mode=time_mode,
            interval_unit=interval_unit,
            variation_unit=variation_unit
        )
    
        await update.effective_chat.send_message(usage_message)
        return

    try:
        command = args[0]
        interval = int(args[1])
        variation = int(args[2])
        target = ' '.join(args[3:]) if len(args) > 3 else 'all'

        # 验证 interval 和 variation
        if interval <= 0:
            await update.effective_chat.send_message(get_translation('invalid_interval', time_mode=TIME_MODE).format(
                interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes')
            ))
            return
        if variation < 0 or (TIME_MODE == "hour" and variation >= interval * 60) or (TIME_MODE == "minute" and variation >= interval * 60):
            await update.effective_chat.send_message(get_translation('invalid_variation', time_mode=TIME_MODE).format(
                variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
            ))
            return

        # 验证 target
        if not validate_target(target):
            await update.effective_chat.send_message(get_translation('invalid_target'))
            return

        tasks = load_tasks()
        new_task = {
            "id": str(len(tasks['tasks']) + 1),
            "command": command,
            "interval": interval,
            "variation": variation,
            "target": target
        }

        if validate_task(new_task):
            tasks['tasks'].append(new_task)
            save_tasks(tasks)

            # 调度新任务
            job = await schedule_task(new_task)

            next_run = job.next_run_time
            next_run_beijing = get_beijing_time(next_run)

            logger.info(f"New task added: ID={new_task['id']}, Command={command}, Interval={interval}{'h' if TIME_MODE == 'hour' else 'm'}, Variation={variation}{'m' if TIME_MODE == 'hour' else 's'}, Target={target}")
            
            task_added_message = get_translation('task_added_detailed', time_mode=TIME_MODE)
            formatted_message = task_added_message.format(
                task_id=new_task['id'],
                command=command,
                interval=interval,
                variation=variation,
                target=target,
                next_run=next_run_beijing.strftime('%Y-%m-%d %H:%M:%S'),
                next_run_utc=next_run.strftime('%Y-%m-%d %H:%M:%S'),
                interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
                variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
            )
            await update.effective_chat.send_message(formatted_message)
        else:
            await update.effective_chat.send_message(get_translation('invalid_task_format'))
    except ValueError:
        await update.effective_chat.send_message(get_translation('invalid_task_parameters'))
    except Exception as e:
        logger.error(f"Error adding task: {str(e)}")
        await update.effective_chat.send_message(get_translation('task_add_error'))

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    tasks = load_tasks()
    if not tasks['tasks']:
        await update.message.reply_text(get_translation('no_tasks'))
        return

    task_list = []
    for task in tasks['tasks']:
        job = scheduler.get_job(f"task_{task['id']}")
        status = get_translation('active') if job and job.next_run_time else get_translation('paused')
        next_run = job.next_run_time if job else None
        next_run_beijing = get_beijing_time(next_run) if next_run else None
        
        task_info_template = get_translation('task_info', time_mode=TIME_MODE)
        task_info = task_info_template.format(
            id=task['id'],
            command=task['command'],
            interval=task['interval'],
            variation=task['variation'],
            target=task['target'],
            next_run=next_run_beijing.strftime('%Y-%m-%d %H:%M:%S') if next_run_beijing else get_translation('not_scheduled'),
            next_run_utc=next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else get_translation('not_scheduled'),
            status=status,
            interval_unit=get_translation('hours') if TIME_MODE == 'hour' else get_translation('minutes'),
            variation_unit=get_translation('minutes') if TIME_MODE == 'hour' else get_translation('seconds')
        )
        task_list.append(task_info)

    full_message = get_translation('task_list_header') + "\n\n" + "\n\n".join(task_list)
    
    if len(full_message) > 4096:
        messages = [full_message[i:i+4096] for i in range(0, len(full_message), 4096)]
        for message in messages:
            await update.message.reply_text(message)
    else:
        await update.message.reply_text(full_message)

async def pause_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    if not context.args:
        await update.message.reply_text(get_translation('pausetask_usage'))
        return

    task_id = context.args[0].lower()

    if task_id == 'all':
        paused_count = 0
        for job in scheduler.get_jobs():
            if job.id.startswith('task_'):
                job.pause()
                paused_count += 1
        await update.message.reply_text(get_translation('all_tasks_paused').format(count=paused_count))
    else:
        job = scheduler.get_job(f"task_{task_id}")
        if job:
            job.pause()
            await update.message.reply_text(get_translation('task_paused').format(task_id=task_id))
        else:
            await update.message.reply_text(get_translation('task_not_found').format(task_id=task_id))

async def resume_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    if not context.args:
        await update.message.reply_text(get_translation('resumetask_usage'))
        return

    task_id = context.args[0].lower()

    if task_id == 'all':
        resumed_count = 0
        for job in scheduler.get_jobs():
            if job.id.startswith('task_'):
                job.resume()
                resumed_count += 1
        await update.message.reply_text(get_translation('all_tasks_resumed').format(count=resumed_count))
    else:
        job = scheduler.get_job(f"task_{task_id}")
        if job:
            job.resume()
            await update.message.reply_text(get_translation('task_resumed').format(task_id=task_id))
        else:
            await update.message.reply_text(get_translation('task_not_found').format(task_id=task_id))

async def remove_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    if not context.args:
        await update.message.reply_text(get_translation('removetask_usage'))
        return

    task_id = context.args[0]
    tasks = load_tasks()
    original_length = len(tasks['tasks'])
    tasks['tasks'] = [task for task in tasks['tasks'] if task['id'] != task_id]
    
    if len(tasks['tasks']) == original_length:
        await update.message.reply_text(get_translation('task_not_found').format(task_id=task_id))
    else:
        save_tasks(tasks)
        # 停止被移除的任务
        scheduler.remove_job(f"task_{task_id}")
        await update.message.reply_text(get_translation('task_removed').format(task_id=task_id))

def load_tasks():
    tasks = {"tasks": []}
    
    # 首先加载 CRON_TASKS_JSON 中的任务
    if CRON_TASKS_JSON:
        try:
            cron_tasks = json.loads(CRON_TASKS_JSON)
            tasks["tasks"] = cron_tasks.get("tasks", [])
        except json.JSONDecodeError:
            logger.error("Failed to parse CRON_TASKS_JSON")
    
    # 然后加载通过 /addtask 添加的任务
    added_tasks_json = os.getenv('ADDED_TASKS_JSON', '{"tasks": []}')
    try:
        added_tasks = json.loads(added_tasks_json)
        tasks["tasks"].extend(added_tasks.get("tasks", []))
    except json.JSONDecodeError:
        logger.error("Failed to parse ADDED_TASKS_JSON")
    
    return tasks

def save_tasks(tasks):
    # 只保存通过 /addtask 添加的任务
    cron_tasks = json.loads(CRON_TASKS_JSON) if CRON_TASKS_JSON else {"tasks": []}
    cron_task_ids = {task['id'] for task in cron_tasks.get('tasks', [])}
    
    added_tasks = {"tasks": [task for task in tasks['tasks'] if task['id'] not in cron_task_ids]}
    
    os.environ['ADDED_TASKS_JSON'] = json.dumps(added_tasks)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
