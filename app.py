from quart import Quart, request, render_template, jsonify, redirect, url_for, websocket
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from functools import wraps
import logging
import os
import asyncio
import datetime
import pytz
import json
import re
import aiohttp
import random
import warnings
from cryptography.utils import CryptographyDeprecationWarning
from group_run import run_main as host_execute_main, DEFAULT_COMMAND, get_target_accounts
from upload_keys import upload_public_keys
from translations import get_translation
from language_manager import language_manager
import ssh
import group_run
import asyncssh
from aiohttp import web, WSMsgType
from aiohttp.web import middleware
from aiohttp_cors import setup as setup_cors, ResourceOptions
import paramiko
import secrets

# 忽略 cryptography 的弃用警告
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Quart(__name__)

@app.after_request
async def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

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
DEFAULT_PASSWORD = secrets.token_urlsafe(32)  # 生成一个随机的默认密码
LOGIN_PASSWORD = os.getenv('CONTROL_PANEL_PASSWORD')

host_execute_lock = asyncio.Lock()
is_executing_host = False
next_execute_time = None
startup_complete = False
welcome_message_sent = False

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

# 全局变量
BOT_ACTIVE = True
application = None
websocket_connections = {}
active_websockets = set()

def get_accounts():
    ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
    return json.loads(ACCOUNTS_JSON) if ACCOUNTS_JSON else []

async def run_bot_and_server():
    # 启动 Telegram bot
    bot_task = asyncio.create_task(setup_bot())
    
    # 配置并启动 Hypercorn 服务器
    port = int(os.environ.get('PORT', 10000))
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]
    server_task = asyncio.create_task(serve(app, config))
    
    # 等待两个任务完成（实际上它们会一直运行）
    await asyncio.gather(bot_task, server_task)

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
    
    # 重新加载所有任务，进行时间单位转换
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

# WebSocket 处理函数
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    host = request.match_info['host']
    websocket_connections[host] = ws

    # 获取主机信息
    host_info = next((h for h in get_accounts() if h['customhostname'] == host), None)
    if not host_info:
        await ws.send_str("Host not found")
        await ws.close()
        return ws

    # 创建 SSH 客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # 连接到 SSH 服务器
        await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: ssh.connect(
                host_info['sslhost'] or host_info['hostname'],
                username=host_info['ssluser'] or host_info['username'],
                password=host_info.get('password'),
                key_filename=host_info.get('secretkey'),
                timeout=10
            )
        )

        # 创建 SSH shell
        channel = ssh.invoke_shell()
        
        # 发送初始提示符
        await ws.send_str(f"Connected to {host}\n")

        async def read_ssh():
            while True:
                if channel.recv_ready():
                    data = channel.recv(1024).decode('utf-8', errors='ignore')
                    await ws.send_str(data)
                await asyncio.sleep(0.1)

        # 启动读取 SSH 输出的任务
        read_task = asyncio.create_task(read_ssh())

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if msg.data == 'close':
                        break
                    else:
                        # 执行 SSH 命令
                        channel.send(msg.data + "\n")
                elif msg.type == WSMsgType.ERROR:
                    print(f'WebSocket connection closed with exception {ws.exception()}')
                    break
        finally:
            read_task.cancel()
            try:
                await read_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        await ws.send_str(f"Error: {str(e)}")
    finally:
        if host in websocket_connections:
            del websocket_connections[host]
        ssh.close()

    await ws.close()
    return ws

@middleware
async def error_middleware(request, handler):
    try:
        response = await handler(request)
        return response
    except web.HTTPException as ex:
        return web.json_response({'error': str(ex)}, status=ex.status)
    except Exception as ex:
        return web.json_response({'error': str(ex)}, status=500)

# Bot 设置函数
async def setup_bot():
    global application
    if application is None:
        application = (
            ApplicationBuilder()
            .token(TELEGRAM_BOT_TOKEN)
            .build()
        )
        
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

        await application.initialize()
        await application.start()

        # 设置 webhook（如果使用 webhook 模式）
        if os.getenv('USE_WEBHOOK', 'False').lower() == 'true':
            webhook_url = f"{os.getenv('APP_URL')}/{os.getenv('TELEGRAM_BOT_TOKEN')}"
            await application.bot.set_webhook(webhook_url)

        # 加载并调度所有保存的任务
        tasks = load_tasks_from_config()
        for task in tasks:
            await schedule_task(task)

    return application  # 返回 application 对象

async def log_and_send(bot, message):
    logger.info(message)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

async def execute_host(bot, command, target='all', send_telegram=True):
    global is_executing_host
    async with host_execute_lock:
        if is_executing_host:
            if send_telegram:
                await log_and_send(bot, get_translation('executing_command'))
            return None, None, None
        is_executing_host = True

    try:
        success_count, total_count, failed_hosts = await host_execute_main(command=command, target=target, send_messages=send_telegram)
        
        # 构建失败主机的消息
        failure_message = ""
        if failed_hosts:
            failure_message = "Failed hosts:\n" + "\n".join([f"{host['host']}: {host['reason']}" for host in failed_hosts])
        
        # 构建完整的执行结果消息
        execution_result = f"Command execution completed. Success: {success_count}/{total_count}"
        if failure_message:
            execution_result += f"\n\n{failure_message}"
        
        # 通过WebSocket发送执行结果
        await broadcast_output(execution_result)
        
        return success_count, total_count, failed_hosts
    except Exception as e:
        error_message = f"Error executing command: {str(e)}"
        await broadcast_output(error_message)
        if send_telegram:
            await log_and_send(bot, get_translation('command_error').format(error=str(e)))
        return 0, 0, []
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
    success_count, total_count, failed_hosts = await host_execute_main(send_messages=False, command=CUSTOM_COMMAND)
    next_execute_time = calculate_next_execute_time(current_time, int(AUTO_CONNECT_INTERVAL))
    
    scheduler.remove_all_jobs()
    scheduler.add_job(scheduled_execute_host, 'date', run_date=next_execute_time, args=[bot])
    
    completion_message = get_translation('scheduled_execution_complete').format(
        success_count=success_count,
        total_count=total_count,
        next_time=next_execute_time.strftime('%Y-%m-%d %H:%M:%S'),
        next_time_utc=next_execute_time.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    )
    
    if failed_hosts:
        failure_message = "Failed hosts:\n" + "\n".join([f"{host['host']}: {host['reason']}" for host in failed_hosts])
        completion_message += "\n\n" + failure_message
    
    await log_and_send(bot, completion_message)

@app.route(f"/{os.getenv('TELEGRAM_BOT_TOKEN')}", methods=['POST'])
async def telegram_webhook():
    if application and BOT_ACTIVE:
        update = Update.de_json(await request.get_json(force=True), application.bot)
        await application.process_update(update)
    return 'OK'

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
    global application, next_execute_time, active_websockets, welcome_message_sent
    
    # 设置应用程序
    application = await setup_bot()
    
    # 设置 webhook
    webhook_set = await set_webhook()
    if not webhook_set:
        logger.error(get_translation('webhook_setup_failed'))
        return

    # 设置定时任务
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

    # 初始化 WebSocket 连接集合
    active_websockets = set()

    # 只有在所有设置都完成后，才发送欢迎消息
    if not welcome_message_sent:
        await send_welcome_message_to_chat(application.bot)
        welcome_message_sent = True

async def send_welcome_message_to_chat(bot):
    welcome_message = generate_welcome_message()
    reply_markup = create_feedback_keyboard()
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=welcome_message, reply_markup=reply_markup)
        logger.info("Welcome message sent successfully")
    except Exception as e:
        logger.error(f"Failed to send welcome message: {str(e)}")

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
        
        success_count, total_count, failed_hosts = await host_execute_main(command=command, target=target, send_messages=False)
        
        next_run = calculate_next_execute_time(now, interval)
        completion_message = get_translation('task_execution_complete').format(
            task_id=task_id,
            target=target,
            command=command,
            success_count=success_count,
            total_count=total_count,
            next_run_beijing=next_run.strftime("%Y-%m-%d %H:%M:%S"),
            next_run_utc=next_run.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S")
        )
        
        if failed_hosts:
            failure_message = get_translation('failed_hosts') + "\n" + "\n".join([f"{host['host']}: {host['reason']}" for host in failed_hosts])
            completion_message += "\n\n" + failure_message
        
        await application.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=completion_message
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

        new_task = {
            "command": command,
            "interval": interval,
            "variation": variation,
            "target": target
        }

        task = add_task_to_config(new_task)

        # 调度新任务
        job = await schedule_task(task)

        next_run = job.next_run_time
        next_run_beijing = get_beijing_time(next_run)

        logger.info(f"New task added: ID={task['id']}, Command={command}, Interval={interval}{'h' if TIME_MODE == 'hour' else 'm'}, Variation={variation}{'m' if TIME_MODE == 'hour' else 's'}, Target={target}")
        
        task_added_message = get_translation('task_added_detailed', time_mode=TIME_MODE)
        formatted_message = task_added_message.format(
            task_id=task['id'],
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

    except ValueError:
        await update.effective_chat.send_message(get_translation('invalid_task_parameters'))
    except Exception as e:
        logger.error(f"Error adding task: {str(e)}")
        await update.effective_chat.send_message(get_translation('task_add_error'))

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.message.chat_id) != TELEGRAM_CHAT_ID:
        await update.message.reply_text(get_translation('no_permission'))
        return

    tasks = load_tasks_from_config()
    if not tasks:  # 直接检查tasks是否为空
        await update.message.reply_text(get_translation('no_tasks'))
        return

    task_list = []
    for task in tasks:  # 直接遍历tasks
        job = scheduler.get_job(f"task_{task['id']}")
        if job is None:
            continue  # 跳过已被删除的任务

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
        tasks = load_tasks_from_config() # 加载当前的任务列表
        paused_count = 0
        for task in tasks:
            job = scheduler.get_job(f"task_{task['id']}")
            if job:
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
        tasks = load_tasks_from_config() # 加载当前的任务列表
        resumed_count = 0
        for task in tasks:
            job = scheduler.get_job(f"task_{task['id']}")
            if job:
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
    if str(update.message.chat_id) != os.getenv('TELEGRAM_CHAT_ID'):
        await update.message.reply_text("You don't have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removetask <task_id>")
        return

    task_id = context.args[0]
    remove_task_from_config(task_id)
    scheduler.remove_job(f"task_{task_id}")
    await update.message.reply_text(f"Task with ID {task_id} has been removed.")

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
    
    # 更新环境变量
    os.environ['ADDED_TASKS_JSON'] = json.dumps(added_tasks)
    
    # 合并 CRON_TASKS_JSON 和 ADDED_TASKS_JSON
    all_tasks = cron_tasks.copy()
    all_tasks['tasks'].extend(added_tasks['tasks'])
    
    # 更新 CRON_TASKS_JSON 环境变量
    os.environ['CRON_TASKS_JSON'] = json.dumps(all_tasks)

def load_tasks_from_config():
    cron_tasks_json = os.getenv('CRON_TASKS_JSON', '{"tasks": [], "host_groups": {}}')
    config = json.loads(cron_tasks_json)
    tasks = config['tasks']
    for task in tasks:
        task['interval'] = int(task['interval'])
        task['variation'] = int(task['variation'])
    return tasks

def save_tasks_to_config(tasks):
    cron_tasks_json = os.getenv('CRON_TASKS_JSON', '{"tasks": [], "host_groups": {}}')
    config = json.loads(cron_tasks_json)
    config['tasks'] = tasks
    os.environ['CRON_TASKS_JSON'] = json.dumps(config)

def add_task_to_config(task):
    tasks = load_tasks_from_config()
    task['id'] = str(len(tasks) + 1)
    task['interval'] = int(task['interval'])
    task['variation'] = int(task['variation'])
    tasks.append(task)
    save_tasks_to_config(tasks)
    return task

def remove_task_from_config(task_id):
    tasks = load_tasks_from_config()
    tasks = [task for task in tasks if task['id'] != task_id]
    save_tasks_to_config(tasks)

def edit_task_in_config(task_id, updated_task):
    tasks = load_tasks_from_config()
    for i, task in enumerate(tasks):
        if task['id'] == task_id:
            tasks[i] = updated_task
            break
    save_tasks_to_config(tasks)

async def remove_webhook():
    bot = Bot(TELEGRAM_BOT_TOKEN)
    await bot.delete_webhook()

def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not request.cookies.get('authenticated'):
            return redirect(url_for('login'))
        return await f(*args, **kwargs)
    return decorated_function

@app.route('/health')
async def health_check():
    utc_time = datetime.datetime.now(pytz.UTC)
    beijing_time = utc_time.astimezone(pytz.timezone('Asia/Shanghai'))
    
    utc_str = utc_time.strftime("%Y-%m-%d %H:%M:%S")
    beijing_str = beijing_time.strftime("%Y-%m-%d %H:%M:%S")
    
    return f"OK - Server is running. UTC time: {utc_str}, Beijing time: {beijing_str}", 200

@app.route('/login', methods=['GET', 'POST'])
async def login():
    if not LOGIN_PASSWORD or LOGIN_PASSWORD == DEFAULT_PASSWORD:
        return "Control panel access is not configured. Please set the CONTROL_PANEL_PASSWORD environment variable.", 403

    if request.method == 'POST':
        form = await request.form
        if form.get('password') == LOGIN_PASSWORD:
            response = redirect(url_for('home'))
            # 在这里修改 set_cookie 的调用
            response.set_cookie('authenticated', 'true', httponly=True, secure=True, samesite='Strict')
            return response
        else:
            return await render_template('login.html', error='Invalid password')
    return await render_template('login.html')

@app.route('/logout')
@login_required
async def logout():
    response = redirect(url_for('login'))
    # 在这里添加 delete_cookie 的调用
    response.delete_cookie('authenticated', httponly=True, secure=True, samesite='Strict')
    return response

@app.route('/')
@login_required
async def home():
    if not LOGIN_PASSWORD or LOGIN_PASSWORD == DEFAULT_PASSWORD:
        return "Control panel access is not configured. Please set the CONTROL_PANEL_PASSWORD environment variable.", 403
    return await render_template('index.html', authenticated=True)

@app.route('/api/start_bot', methods=['POST'])
async def start_bot():
    global BOT_ACTIVE, application
    if not BOT_ACTIVE:
        BOT_ACTIVE = True
        if application is None:
            application = await setup_bot()
        webhook_set = await set_webhook()
        if webhook_set:
            return jsonify({"status": "success", "message": "Bot started and webhook set successfully"})
        else:
            return jsonify({"status": "warning", "message": "Bot started but webhook setting failed"})
    return jsonify({"status": "info", "message": "Bot is already running"})

@app.route('/api/stop_bot', methods=['POST'])
async def stop_bot():
    global BOT_ACTIVE
    if BOT_ACTIVE:
        BOT_ACTIVE = False
        await remove_webhook()
        return jsonify({"status": "success", "message": "Bot stopped and webhook removed successfully"})
    return jsonify({"status": "info", "message": "Bot is not running"})

@app.route('/api/bot_status')
async def get_bot_status():
    return jsonify({"status": "active" if BOT_ACTIVE else "inactive"})

@app.route('/api/execute_default_command', methods=['POST'])
@login_required
async def web_execute_default_command():
    try:
        if application:
            # 设置更新回调
            group_run.set_update_callback(broadcast_output)
            
            result = await execute_host(application.bot, CUSTOM_COMMAND, 'all', send_telegram=False)
            if result is None:
                return jsonify({"status": "error", "message": "Execute host returned None"})
            
            success_count, total_count, failed_hosts = result
            
            return jsonify({
                "status": "success", 
                "message": f"Default command execution completed. Success: {success_count}/{total_count}",
            })
        else:
            return jsonify({"status": "error", "message": "Bot is not running"})
    except Exception as e:
        error_message = f"Error executing command: {str(e)}"
        await broadcast_output(error_message)
        return jsonify({"status": "error", "message": error_message})
    finally:
        # 清除更新回调
        group_run.set_update_callback(None)

@app.route('/api/execute_group_run', methods=['POST'])
@login_required
async def web_execute_group_run():
    try:
        data = await request.json
        command = data.get('command')
        target = data.get('target', 'all')

        if not command:
            return jsonify({"status": "error", "message": "Command is required"})

        if application:
            # 设置更新回调
            group_run.set_update_callback(broadcast_output)
            
            result = await execute_host(application.bot, command, target, send_telegram=False)
            if result is None:
                return jsonify({"status": "error", "message": "Execute host returned None"})
            
            success_count, total_count, failed_hosts = result
            
            return jsonify({
                "status": "success", 
                "message": f"Group run command execution completed. Success: {success_count}/{total_count}",
            })
        else:
            return jsonify({"status": "error", "message": "Bot is not running"})
    except Exception as e:
        error_message = f"Error executing group run command: {str(e)}"
        await broadcast_output(error_message)
        return jsonify({"status": "error", "message": error_message})
    finally:
        # 清除更新回调
        group_run.set_update_callback(None)

@app.route('/api/add_task', methods=['POST'])
@login_required
async def web_add_task():
    data = await request.json
    task = {
        "command": data.get('command'),
        "interval": int(data.get('interval')),  # 确保这是一个整数
        "variation": int(data.get('variation')),  # 确保这是一个整数
        "target": data.get('target', 'all')
    }
    task = add_task_to_config(task)
    await schedule_task(task)
    return jsonify({"status": "success", "message": "Task added successfully", "task": task})

@app.route('/api/remove_task', methods=['POST'])
@login_required
async def web_remove_task():
    data = await request.json
    task_id = data.get('id')
    remove_task_from_config(task_id)
    scheduler.remove_job(f"task_{task_id}")
    return jsonify({"status": "success", "message": "Task removed successfully"})

@app.route('/api/edit_task', methods=['POST'])
@login_required
async def edit_task():
    data = await request.json
    task_id = data.get('id')
    tasks = load_tasks_from_config()
    for i, task in enumerate(tasks):
        if task['id'] == task_id:
            # 确保 interval 和 variation 是整数
            data['interval'] = int(data['interval'])
            data['variation'] = int(data['variation'])
            tasks[i] = data
            save_tasks_to_config(tasks)
            await schedule_task(data)
            return jsonify({"status": "success", "message": "Task updated successfully"})
    return jsonify({"status": "error", "message": "Task not found"})

@app.route('/api/get_tasks')
@login_required
async def get_tasks():
    tasks = load_tasks_from_config()
    return jsonify({"tasks": tasks, "timeMode": TIME_MODE})

@app.route('/config', methods=['GET'])
@login_required
async def config_page():
    return await render_template('config.html')

@app.route('/api/get_config', methods=['GET'])
@login_required
async def get_config():
    accounts_json = os.getenv('ACCOUNTS_JSON', '[]')
    cron_tasks_json = os.getenv('CRON_TASKS_JSON', '{"tasks": [], "host_groups": {}}')
    return jsonify({
        'ACCOUNTS_JSON': json.loads(accounts_json),
        'CRON_TASKS_JSON': json.loads(cron_tasks_json)
    })

@app.route('/api/save_config', methods=['POST'])
@login_required
async def save_config():
    data = await request.json
    os.environ['ACCOUNTS_JSON'] = json.dumps(data['ACCOUNTS_JSON'])
    os.environ['CRON_TASKS_JSON'] = json.dumps(data['CRON_TASKS_JSON'])
    return jsonify({"status": "success", "message": "Configuration saved successfully"})

@app.route('/api/download_config', methods=['GET'])
@login_required
async def download_config():
    config = {
        'ACCOUNTS_JSON': json.loads(os.getenv('ACCOUNTS_JSON', '[]')),
        'CRON_TASKS_JSON': json.loads(os.getenv('CRON_TASKS_JSON', '{"tasks": [], "host_groups": {}}'))
    }
    return jsonify(config)

@app.route('/hosts')
@login_required
async def hosts_page():
    accounts = json.loads(os.environ.get('ACCOUNTS_JSON', '[]'))
    return await render_template('hosts.html', hosts=accounts)

@app.route('/api/get_hosts')
@login_required
async def get_hosts():
    accounts = json.loads(os.environ.get('ACCOUNTS_JSON', '[]'))
    formatted_accounts = []
    for account in accounts:
        formatted_account = {
            'customhostname': account.get('customhostname', ''),
            'username': account.get('ssluser') or account.get('username', ''),
            'hostname': account.get('sslhost') or account.get('hostname', ''),
            'port': account.get('port', 22),  # 默认端口为 22
            'password': account.get('password', ''),
            'secretkey': account.get('secretkey', ''),
            'publickey': account.get('publickey', '')
        }
        formatted_accounts.append(formatted_account)
    return jsonify(formatted_accounts)

@app.route('/api/add_host', methods=['POST'])
@login_required
async def add_host():
    new_host = await request.json
    accounts = json.loads(os.environ.get('ACCOUNTS_JSON', '[]'))
    accounts.append(new_host)
    os.environ['ACCOUNTS_JSON'] = json.dumps(accounts)
    return jsonify({"status": "success", "message": "Host added successfully"})

@app.route('/api/edit_host', methods=['POST'])
@login_required
async def edit_host():
    updated_host = await request.json
    original_customhostname = updated_host.pop('originalCustomhostname', None)
    accounts = json.loads(os.environ.get('ACCOUNTS_JSON', '[]'))
    for i, host in enumerate(accounts):
        if host['customhostname'] == original_customhostname:
            accounts[i] = updated_host
            break
    os.environ['ACCOUNTS_JSON'] = json.dumps(accounts)
    return jsonify({"status": "success", "message": "Host updated successfully"})

@app.route('/api/delete_host', methods=['POST'])
@login_required
async def delete_host():
    host_to_delete = await request.json
    accounts = json.loads(os.environ.get('ACCOUNTS_JSON', '[]'))
    accounts = [host for host in accounts if host['customhostname'] != host_to_delete['customhostname']]
    os.environ['ACCOUNTS_JSON'] = json.dumps(accounts)
    return jsonify({"status": "success", "message": "Host deleted successfully"})

@app.websocket('/ws/output')
async def output_websocket():
    ws = websocket._get_current_object()
    active_websockets.add(ws)
    try:
        while True:
            # 保持连接打开，但不期望接收任何消息
            await ws.receive()
    except asyncio.CancelledError:
        # 正常的断开连接情况
        pass
    finally:
        active_websockets.remove(ws)

async def broadcast_output(message):
    for ws in list(active_websockets):  # 创建副本以避免在迭代时修改集合
        try:
            await ws.send_json({
                'type': 'output',
                'message': message
            })
        except Exception:
            # 如果发送失败，移除这个WebSocket连接
            active_websockets.remove(ws)

@app.websocket('/ws/ssh/<string:host>')
async def ssh_websocket(host):
    try:
        # 获取主机信息
        host_info = next((h for h in get_accounts() if h['customhostname'] == host), None)
        if not host_info:
            await websocket.send(json.dumps({"error": "Host not found"}))
            return

        # 创建 SSH 客户端
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # 连接到 SSH 服务器
            ssh.connect(
                host_info.get('sslhost') or host_info.get('hostname'),
                username=host_info.get('ssluser') or host_info.get('username'),
                password=host_info.get('password'),
                key_filename=host_info.get('secretkey'),
                port=int(host_info.get('port', 22)),
                timeout=10
            )

            # 创建 SSH shell
            channel = ssh.invoke_shell()

            async def reader():
                while True:
                    if channel.recv_ready():
                        data = channel.recv(1024).decode('utf-8', errors='ignore')
                        await websocket.send(json.dumps({"data": data}))
                    await asyncio.sleep(0.1)

            async def writer():
                while True:
                    data = await websocket.receive()
                    channel.send(data + "\n")

            await asyncio.gather(reader(), writer())

        finally:
            ssh.close()

    except Exception as e:
        await websocket.send(json.dumps({"error": str(e)}))

if __name__ == '__main__':
    asyncio.run(run_bot_and_server())
