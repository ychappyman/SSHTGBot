import json
import os
import asyncio
import paramiko
from telegram import Update
from telegram.ext import CallbackContext
import threading
import time

# 从环境变量读取 VPS 账户信息
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
accounts = json.loads(ACCOUNTS_JSON) if ACCOUNTS_JSON else []

# 存储 SSH 会话和超时定时器
ssh_sessions = {}
ssh_timeouts = {}

def is_ssh_connected(chat_id):
    return chat_id in ssh_sessions

def handle_ssh_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if len(context.args) == 0:
        usernames = [account['username'] for account in accounts]
        update.message.reply_text(f"可用的 VPS 用户名：\n{', '.join(usernames)}")
    elif len(context.args) == 1:
        username = context.args[0]
        account = next((acc for acc in accounts if acc['username'] == username), None)
        if account:
            if chat_id in ssh_sessions:
                update.message.reply_text("已有活动的 SSH 会话，请先使用 /exit 退出")
            else:
                # 使用线程来运行连接操作
                threading.Thread(target=connect_to_vps, args=(update, context, account)).start()
        else:
            update.message.reply_text(f"找不到用户名为 {username} 的 VPS")
    else:
        update.message.reply_text("使用方法：/ssh 或 /ssh <username>")

def connect_to_vps(update: Update, context: CallbackContext, account):
    chat_id = update.effective_chat.id
    username = account['username']
    password = account['password']
    hostname = account['hostname']

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        update.message.reply_text(f"正在连接到 {username}@{hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=30)
        ssh_sessions[chat_id] = ssh
        update.message.reply_text(f"已连接到 {username}@{hostname}")
        
        # 启动超时检查
        ssh_timeouts[chat_id] = threading.Timer(900, lambda: timeout_ssh_session(context.bot, chat_id))
        ssh_timeouts[chat_id].start()

    except Exception as e:
        update.message.reply_text(f"连接失败：{str(e)}")

def handle_exit_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        ssh_sessions[chat_id].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            ssh_timeouts[chat_id].cancel()
            del ssh_timeouts[chat_id]
        update.message.reply_text("已断开 SSH 连接")
    else:
        update.message.reply_text("当前没有活动的 SSH 连接")

def timeout_ssh_session(bot, chat_id):
    if chat_id in ssh_sessions:
        ssh_sessions[chat_id].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            del ssh_timeouts[chat_id]
        bot.send_message(chat_id=chat_id, text="SSH 会话已超时，连接已断开")
