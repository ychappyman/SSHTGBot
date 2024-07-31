import json
import os
import asyncio
import paramiko
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import time
import re
from translations import get_translation
from language_manager import language_manager

# 从环境变量读取主机账户信息
ACCOUNTS_JSON = os.getenv('ACCOUNTS_JSON')
accounts = json.loads(ACCOUNTS_JSON) if ACCOUNTS_JSON else []

# 存储 SSH 会话和超时任务
ssh_sessions = {}
ssh_timeouts = {}
is_command_running = {}

def is_ssh_connected(chat_id):
    return chat_id in ssh_sessions and ssh_sessions[chat_id]['ssh'].get_transport().is_active()

async def handle_ssh_output(shell, update, timeout=10):
    output_buffer = ""
    prompt_pattern = r'.*[$#]\s*$'  # 修改提示符模式以匹配更广泛的情况
    
    start_time = time.time()
    command_output = []
    prompt = None
    last_sent_index = 0

    while True:
        current_time = time.time()
        if shell.recv_ready():
            chunk = shell.recv(4096).decode('utf-8', errors='ignore')
            output_buffer += chunk
            
            lines = output_buffer.split('\n')
            full_lines = lines[:-1]
            output_buffer = lines[-1]
            
            for line in full_lines:
                clean_line = clean_ansi_escape_sequences(line)
                command_output.append(clean_line)
            
            last_line = clean_ansi_escape_sequences(output_buffer)
            if re.match(prompt_pattern, last_line):
                if command_output[last_sent_index:]:
                    await update.message.reply_text('\n'.join(command_output[last_sent_index:]))
                await update.message.reply_text(last_line)
                prompt = last_line
                break
            
            if current_time - start_time > 2:  # 每2秒输出一次
                if command_output[last_sent_index:]:
                    await update.message.reply_text('\n'.join(command_output[last_sent_index:]))
                    last_sent_index = len(command_output)
                start_time = current_time
        else:
            if current_time - start_time > timeout:
                if command_output[last_sent_index:]:
                    await update.message.reply_text('\n'.join(command_output[last_sent_index:]))
                    last_sent_index = len(command_output)
                start_time = current_time
            await asyncio.sleep(0.1)

    return prompt

async def connect_to_host(update: Update, context: ContextTypes.DEFAULT_TYPE, host_info):
    chat_id = update.effective_chat.id
    ssluser = host_info.get('ssluser') or host_info.get('username')
    password = host_info.get('password')
    sslhost = host_info.get('sslhost') or host_info.get('hostname')
    customhostname = host_info.get('customhostname', '').lower()
    secret_key_path = host_info.get('secretkey')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        await update.message.reply_text(get_translation('connecting_to_host').format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        
        if secret_key_path:
            private_key = paramiko.RSAKey.from_private_key_file(secret_key_path)
            await asyncio.get_event_loop().run_in_executor(None, lambda: ssh.connect(sslhost, username=ssluser, pkey=private_key, timeout=10, auth_timeout=10, banner_timeout=10))
        elif password:
            await asyncio.get_event_loop().run_in_executor(None, lambda: ssh.connect(sslhost, username=ssluser, password=password, timeout=10, auth_timeout=10, banner_timeout=10))
        else:
            await asyncio.get_event_loop().run_in_executor(None, lambda: ssh.connect(sslhost, username=ssluser, timeout=10, auth_timeout=10, banner_timeout=10))
        
        shell = ssh.invoke_shell()
        
        # 添加 50 秒超时逻辑
        try:
            prompt = await asyncio.wait_for(handle_ssh_output(shell, update), timeout=50)
        except asyncio.TimeoutError:
            await update.message.reply_text(get_translation('SSH_CONNECTION_TIMEOUT'))
            ssh.close()
            return

        ssh_sessions[chat_id] = {
            'ssh': ssh,
            'shell': shell,
            'buffer': '',
            'prompt': prompt
        }
        
        # 启动 SSH 超时任务
        ssh_timeouts[chat_id] = asyncio.create_task(timeout_ssh_session(context.bot, chat_id))
    except paramiko.AuthenticationException:
        await update.message.reply_text(get_translation('auth_failed'))
    except Exception as e:
        error_message = str(e)
        if not error_message:
            error_message = "Unknown error occurred"
        await update.message.reply_text(get_translation('connection_failed').format(error=error_message))

async def handle_ssh_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    
    if len(context.args) == 0:
        # 显示可用主机列表
        host_list = []
        for account in accounts:
            customhostname = account.get('customhostname', '').lower()
            ssluser = account.get('ssluser') or account.get('username')
            sslhost = account.get('sslhost') or account.get('hostname')
            host_list.append(f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
        
        message = get_translation('available_hosts').format(hosts="\n".join(host_list))
        message += "\n\n" + get_translation('ssh_usage')
        await update.message.reply_text(message)
    elif len(context.args) == 1:
        host_identifier = context.args[0]
        
        # 检查是否是预定义主机
        account = next((acc for acc in accounts if acc.get('customhostname', '').lower() == host_identifier.lower() or 
                        f"{acc.get('ssluser') or acc.get('username')}@{acc.get('sslhost') or acc.get('hostname')}".lower() == host_identifier.lower()), None)
        
        if account:
            # 连接预定义主机
            if chat_id in ssh_sessions:
                await update.message.reply_text(get_translation('active_ssh_session'))
            else:
                await connect_to_host(update, context, account)
        else:
            # 处理自定义主机连接
            if '@' in host_identifier:
                ssluser, sslhost = host_identifier.split('@')
                
                context.user_data['awaiting_ssh_password'] = {
                    'ssluser': ssluser,
                    'sslhost': sslhost
                }
                await update.message.reply_text(get_translation('enter_password'))
            else:
                await update.message.reply_text(get_translation('invalid_host_format'))
    else:
        await update.message.reply_text(get_translation('ssh_usage'))

async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    
    if 'awaiting_ssh_password' in context.user_data:
        password = update.message.text
        host_info = context.user_data['awaiting_ssh_password']
        host_info['password'] = password
        del context.user_data['awaiting_ssh_password']
        
        # 删除密码消息
        await update.message.delete()
        
        await connect_to_host(update, context, host_info)

async def handle_exit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        if chat_id in is_command_running and is_command_running[chat_id]:
            # 如果有命令正在执行，我们需要强制关闭连接
            ssh_sessions[chat_id]['ssh'].close()
            await update.message.reply_text(get_translation('ssh_force_disconnected'))
        else:
            ssh_sessions[chat_id]['shell'].close()
            ssh_sessions[chat_id]['ssh'].close()
            await update.message.reply_text(get_translation('ssh_disconnected'))
        
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            ssh_timeouts[chat_id].cancel()
            del ssh_timeouts[chat_id]
        if chat_id in is_command_running:
            del is_command_running[chat_id]
    else:
        await update.message.reply_text(get_translation('no_active_ssh'))

async def start_ssh_timeout(bot, chat_id):
    if chat_id in ssh_timeouts:
        ssh_timeouts[chat_id].cancel()
    ssh_timeouts[chat_id] = asyncio.create_task(timeout_ssh_session(bot, chat_id))

async def timeout_ssh_session(bot, chat_id):
    await asyncio.sleep(900)  # 15 minutes timeout
    if chat_id in ssh_sessions:
        session = ssh_sessions[chat_id]
        session['shell'].close()
        session['ssh'].close()
        del ssh_sessions[chat_id]
        if chat_id in ssh_timeouts:
            del ssh_timeouts[chat_id]
        if chat_id in is_command_running:
            del is_command_running[chat_id]
        await bot.send_message(chat_id=chat_id, text=get_translation('ssh_session_timeout'))

async def handle_ssh_command_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in ssh_sessions:
        command = update.message.text
        session = ssh_sessions[chat_id]
        shell = session['shell']
        
        if command.lower() == '/exit':
            await handle_exit_command(update, context)
            return

        try:
            is_command_running[chat_id] = True

            # 清空之前的缓冲区
            while shell.recv_ready():
                shell.recv(4096)

            # 发送命令
            shell.send(command + '\n')
            
            # 使用 handle_ssh_output 处理所有命令
            prompt = await handle_ssh_output(shell, update)
            session['prompt'] = prompt

            # 命令执行完毕后，再次清空缓冲区
            while shell.recv_ready():
                shell.recv(4096)

            # 重置超时任务
            if chat_id in ssh_timeouts:
                ssh_timeouts[chat_id].cancel()
            ssh_timeouts[chat_id] = asyncio.create_task(timeout_ssh_session(context.bot, chat_id))
            
        except Exception as e:
            error_message = str(e)
            if not error_message:
                error_message = "Unknown error occurred"
            await update.message.reply_text(get_translation('command_execution_error').format(error=error_message))
        finally:
            is_command_running[chat_id] = False
    else:
        await update.message.reply_text(get_translation('no_active_connection'))

def clean_ansi_escape_sequences(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

async def main() -> None:
    application = Application.builder().token(os.getenv('TELEGRAM_BOT_TOKEN')).build()

    application.add_handler(CommandHandler("ssh", handle_ssh_command))
    application.add_handler(CommandHandler("exit", handle_exit_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ssh_command_execution))

    await application.initialize()
    await application.start()
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
