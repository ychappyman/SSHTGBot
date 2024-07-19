import json
import os
import asyncio
import paramiko
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import threading
import time
import re
from translations import get_translation

# 从环境变量读取主机账户信息
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
accounts = json.loads(ACCOUNTS_JSON) if ACCOUNTS_JSON else []

# 存储 SSH 会话和超时定时器
ssh_sessions = {}
ssh_timeouts = {}

def is_ssh_connected(chat_id):
    return chat_id in ssh_sessions and ssh_sessions[chat_id]['ssh'].get_transport().is_active()

def connect_to_host(update: Update, context: CallbackContext, host_info, language):
    chat_id = update.effective_chat.id
    ssluser = host_info.get('ssluser') or host_info.get('username')
    password = host_info.get('password')
    sslhost = host_info.get('sslhost') or host_info.get('hostname')
    customhostname = host_info.get('customhostname', '').lower()
    secret_key_path = host_info.get('secretkey')

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        update.message.reply_text(get_translation('connecting_to_host', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        
        def connect():
            if secret_key_path:
                private_key = paramiko.RSAKey.from_private_key_file(secret_key_path)
                ssh.connect(sslhost, username=ssluser, pkey=private_key,
                            timeout=30, auth_timeout=20, banner_timeout=20)
            elif password:
                ssh.connect(sslhost, username=ssluser, password=password,
                            timeout=30, auth_timeout=20, banner_timeout=20)
            else:
                # 尝试使用当前用户的默认私钥
                ssh.connect(sslhost, username=ssluser,
                            timeout=30, auth_timeout=20, banner_timeout=20)
            
            return ssh.invoke_shell()

        try:
            shell = connect()
        except paramiko.AuthenticationException:
            update.message.reply_text(get_translation('auth_failed', language))
            return
        except Exception:
            update.message.reply_text(get_translation('connection_failed_retrying', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
            time.sleep(5)
            try:
                shell = connect()
            except paramiko.AuthenticationException:
                update.message.reply_text(get_translation('auth_failed', language))
                return
            except Exception as e:
                raise e

        # 执行初始化命令
        init_commands = [
            "source ~/.profile"
        ]
        for cmd in init_commands:
            shell.send(cmd + '\n')
            time.sleep(0.5)

        # 清除初始化命令的输出
        time.sleep(1)
        while shell.recv_ready():
            shell.recv(4096)

        ssh_sessions[chat_id] = {
            'ssh': ssh,
            'shell': shell,
            'buffer': ''
        }
        update.message.reply_text(get_translation('connected_to_host', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        
        ssh_timeouts[chat_id] = threading.Timer(900, lambda: timeout_ssh_session(context.bot, chat_id, language))
        ssh_timeouts[chat_id].start()

    except Exception as e:
        update.message.reply_text(get_translation('connection_failed', language).format(error=str(e)))

def handle_ssh_command(update: Update, context: CallbackContext) -> None:
    language = context.bot_data.get('language', 'zh')
    chat_id = update.effective_chat.id
    
    if len(context.args) == 0:
        # 显示可用主机列表
        host_list = []
        for account in accounts:
            customhostname = account.get('customhostname', '').lower()
            ssluser = account.get('ssluser') or account.get('username')
            sslhost = account.get('sslhost') or account.get('hostname')
            host_list.append(f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
        
        message = get_translation('available_hosts', language).format(hosts="\n".join(host_list))
        message += "\n\n" + get_translation('ssh_usage', language)
        update.message.reply_text(message)
    elif len(context.args) == 1:
        host_identifier = context.args[0]
        
        # 检查是否是预定义主机
        account = next((acc for acc in accounts if acc.get('customhostname', '').lower() == host_identifier.lower() or 
                        f"{acc.get('ssluser') or acc.get('username')}@{acc.get('sslhost') or acc.get('hostname')}".lower() == host_identifier.lower()), None)
        
        if account:
            # 连接预定义主机
            if chat_id in ssh_sessions:
                update.message.reply_text(get_translation('active_ssh_session', language))
            else:
                connect_to_host(update, context, account, language)
        else:
            # 处理自定义主机连接
            if '@' in host_identifier:
                ssluser, sslhost = host_identifier.split('@')
                
                context.user_data['awaiting_ssh_password'] = {
                    'ssluser': ssluser,
                    'sslhost': sslhost
                }
                update.message.reply_text(get_translation('enter_password', language))
            else:
                update.message.reply_text(get_translation('invalid_host_format', language))
    else:
        update.message.reply_text(get_translation('ssh_usage', language))

def handle_password_input(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    language = context.bot_data.get('language', 'zh')
    
    if 'awaiting_ssh_password' in context.user_data:
        password = update.message.text
        host_info = context.user_data['awaiting_ssh_password']
        host_info['password'] = password
        del context.user_data['awaiting_ssh_password']
        
        # 删除密码消息
        update.message.delete()
        
        connect_to_host(update, context, host_info, language)

def handle_exit_command(update: Update, context: CallbackContext) -> None:
    language = context.bot_data.get('language', 'zh')
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        session = ssh_sessions[chat_id]
        session['shell'].close()
        session['ssh'].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            ssh_timeouts[chat_id].cancel()
            del ssh_timeouts[chat_id]
        update.message.reply_text(get_translation('ssh_disconnected', language))
    else:
        update.message.reply_text(get_translation('no_active_ssh', language))

def timeout_ssh_session(bot, chat_id, language):
    if chat_id in ssh_sessions:
        session = ssh_sessions[chat_id]
        session['shell'].close()
        session['ssh'].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            del ssh_timeouts[chat_id]
        bot.send_message(chat_id=chat_id, text=get_translation('ssh_session_timeout', language))

def handle_ssh_command_execution(update: Update, context: CallbackContext) -> None:
    language = context.bot_data.get('language', 'zh')
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        command = update.message.text
        session = ssh_sessions[chat_id]
        shell = session['shell']
        
        try:
            # 发送命令
            shell.send(command + '\n')
            
            # 等待输出
            time.sleep(1)  # 给命令更多执行时间
            
            # 读取输出
            output = ""
            while shell.recv_ready():
                chunk = shell.recv(4096).decode('utf-8', errors='ignore')
                output += chunk
                if len(chunk) < 4096:
                    time.sleep(0.1)  # 短暂等待，确保所有输出都被读取
                    if not shell.recv_ready():
                        break

            # 清理输出
            output = clean_ansi_escape_sequences(output)
            
            # 分离命令、输出和提示符
            lines = output.split('\n')
            prompt_line = lines[-1] if lines else ""
            output_lines = lines[1:-1] if len(lines) > 2 else []
            
            # 构建响应消息
            response = f"$ {command}\n"
            if output_lines:
                response += "\n".join(output_lines) + "\n"
            response += prompt_line
            
            if response.strip():
                chunks = split_long_message(response.strip())
                for chunk in chunks:
                    update.message.reply_text(chunk)
            else:
                update.message.reply_text(get_translation('command_executed_no_output', language))
            
            # 重置超时定时器
            if chat_id in ssh_timeouts:
                ssh_timeouts[chat_id].cancel()
            ssh_timeouts[chat_id] = threading.Timer(900, lambda: timeout_ssh_session(context.bot, chat_id, language))
            ssh_timeouts[chat_id].start()
            
        except Exception as e:
            update.message.reply_text(get_translation('command_execution_error', language).format(error=str(e)))
    else:
        update.message.reply_text(get_translation('no_active_connection', language))

def clean_ansi_escape_sequences(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def split_long_message(message, max_length=4000):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

def main() -> None:
    updater = Updater(os.getenv('TELEGRAM_BOT_TOKEN'), use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("ssh", handle_ssh_command))
    dp.add_handler(CommandHandler("exit", handle_exit_command))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
