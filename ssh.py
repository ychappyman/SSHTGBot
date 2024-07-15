# ssh.py

import json
import os
import asyncio
import paramiko
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import threading
import time
from translations import get_translation

# 从环境变量读取主机账户信息和语言设置
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
LANGUAGE = os.getenv('LANGUAGE', 'zh')
accounts = json.loads(ACCOUNTS_JSON) if ACCOUNTS_JSON else []

# 存储 SSH 会话和超时定时器
ssh_sessions = {}
ssh_timeouts = {}

def is_ssh_connected(chat_id):
    return chat_id in ssh_sessions

def connect_to_host(update: Update, context: CallbackContext, account):
    chat_id = update.effective_chat.id
    ssluser = account.get('ssluser') or account.get('username')
    password = account.get('password')
    sslhost = account.get('sslhost') or account.get('hostname')
    customhostname = account.get('customhostname', '').lower()
    secret_key_path = account.get('secretkey')

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        update.message.reply_text(get_translation('connecting_to_host', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        
        def connect():
            if secret_key_path:
                private_key = paramiko.RSAKey.from_private_key_file(secret_key_path)
                ssh.connect(sslhost, username=ssluser, pkey=private_key)
            else:
                ssh.connect(sslhost, username=ssluser, password=password)

        try:
            connect()
        except Exception:
            update.message.reply_text(get_translation('connection_failed_retrying', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
            time.sleep(5)
            connect()

        ssh_sessions[chat_id] = ssh
        update.message.reply_text(get_translation('connected_to_host', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        
        # 启动超时检查
        ssh_timeouts[chat_id] = threading.Timer(900, lambda: timeout_ssh_session(context.bot, chat_id))
        ssh_timeouts[chat_id].start()

    except Exception as e:
        update.message.reply_text(get_translation('connection_failed', LANGUAGE).format(error=str(e)))

def handle_ssh_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if len(context.args) == 0:
        host_list = []
        for account in accounts:
            customhostname = account.get('customhostname', '').lower()
            ssluser = account.get('ssluser') or account.get('username')
            sslhost = account.get('sslhost') or account.get('hostname')
            host_list.append(f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
        update.message.reply_text(get_translation('available_hosts', LANGUAGE).format(hosts="\n".join(host_list)))
    elif len(context.args) == 1:
        host_identifier = context.args[0]
        account = next((acc for acc in accounts if acc.get('customhostname', '').lower() == host_identifier.lower() or 
                        f"{acc.get('ssluser') or acc.get('username')}@{acc.get('sslhost') or acc.get('hostname')}".lower() == host_identifier.lower()), None)
        if account:
            if chat_id in ssh_sessions:
                update.message.reply_text(get_translation('active_ssh_session', LANGUAGE))
            else:
                connect_to_host(update, context, account)
        else:
            update.message.reply_text(get_translation('host_not_found', LANGUAGE).format(host=host_identifier))
    else:
        update.message.reply_text(get_translation('ssh_usage', LANGUAGE))

def handle_exit_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        ssh_sessions[chat_id].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            ssh_timeouts[chat_id].cancel()
            del ssh_timeouts[chat_id]
        update.message.reply_text(get_translation('ssh_disconnected', LANGUAGE))
    else:
        update.message.reply_text(get_translation('no_active_ssh', LANGUAGE))

def timeout_ssh_session(bot, chat_id):
    if chat_id in ssh_sessions:
        ssh_sessions[chat_id].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            del ssh_timeouts[chat_id]
        bot.send_message(chat_id=chat_id, text=get_translation('ssh_session_timeout', LANGUAGE))

def handle_command(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        command = update.message.text
        ssh = ssh_sessions[chat_id]
        try:
            stdin, stdout, stderr = ssh.exec_command(command)
            result = stdout.read().decode() + stderr.read().decode()
            if result:
                update.message.reply_text(result)
            else:
                update.message.reply_text(get_translation('command_executed', LANGUAGE))
        except Exception as e:
            update.message.reply_text(get_translation('command_execution_error', LANGUAGE).format(error=str(e)))
    else:
        update.message.reply_text(get_translation('no_active_connection', LANGUAGE))

def main() -> None:
    updater = Updater(os.getenv('TELEGRAM_BOT_TOKEN'), use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("ssh", handle_ssh_command))
    dp.add_handler(CommandHandler("exit", handle_exit_command))
    dp.add_handler(CommandHandler("exec", handle_command))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
