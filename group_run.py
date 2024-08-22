import json
import asyncio
from datetime import datetime, timedelta
import os
import paramiko
import aiohttp
import logging
import re
from translations import get_translation
from language_manager import language_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 默认命令
DEFAULT_COMMAND = "source ~/.profile && pm2 resurrect"

send_update = None

def set_update_callback(callback):
    global send_update
    send_update = callback

def format_to_iso(date):
    return date.strftime('%Y-%m-%d %H:%M:%S')

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

async def execute_ssh_command(sslhost, ssluser, password, command, customhostname='', secret_key_path=None, port=22, send_messages=True):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        language = language_manager.get_language()
        logger.info(get_translation('processing_account', language).format(account=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}:{port}"))
        connection_start = asyncio.get_event_loop().time()
        
        try:
            if secret_key_path:
                private_key = paramiko.RSAKey.from_private_key_file(secret_key_path)
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: client.connect(sslhost, port=port, username=ssluser, pkey=private_key)
                    ),
                    timeout=10
                )
            else:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: client.connect(sslhost, port=port, username=ssluser, password=password)
                    ),
                    timeout=10
                )
        except asyncio.TimeoutError:
            connecting_message = get_translation('connecting_to_host', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
            if send_messages:
                await send_telegram_message(connecting_message)
            if send_update:
                await send_update(connecting_message)
            try:
                if secret_key_path:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, 
                            lambda: client.connect(sslhost, username=ssluser, pkey=private_key)
                        ),
                        timeout=20
                    )
                else:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, 
                            lambda: client.connect(sslhost, username=ssluser, password=password)
                        ),
                        timeout=20
                    )
            except asyncio.TimeoutError:
                connection_failed_message = get_translation('connection_failed', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
                if send_messages:
                    await send_telegram_message(connection_failed_message)
                if send_update:
                    await send_update(connection_failed_message)
                return None, None, "Connection Timeout", None, {'host': f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}", 'reason': "Connection Timeout"}

        logger.info(f"Executing command: {command}")
        command_start = asyncio.get_event_loop().time()
        
        async def execute_and_read():
            full_command = f"{command}; echo $?"
            stdin, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.exec_command(full_command)
            )
            output = await asyncio.get_event_loop().run_in_executor(None, stdout.read)
            error = await asyncio.get_event_loop().run_in_executor(None, stderr.read)
            return output.decode().strip(), error.decode().strip()

        try:
            output, error = await asyncio.wait_for(execute_and_read(), timeout=10)
        except asyncio.TimeoutError:
            timeout_message = get_translation('command_execution_timeout', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
            if send_messages:
                await send_telegram_message(timeout_message)
            if send_update:
                await send_update(timeout_message)
            try:
                output, error = await asyncio.wait_for(execute_and_read(), timeout=110)
            except asyncio.TimeoutError:
                execution_failed_message = get_translation('command_execution_failed', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
                if send_messages:
                    await send_telegram_message(execution_failed_message)
                if send_update:
                    await send_update(execution_failed_message)
                return None, None, f"Command Execution Timeout: {command}", command, {'host': f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}", 'reason': f"Command Execution Timeout: {command}"}
        
        command_time = asyncio.get_event_loop().time() - command_start
        if command_time > 10:
            logger.info(f"Command execution took {command_time:.2f} seconds")
        
        # 分割命令输出和退出状态
        output_lines = clean_ansi(output).splitlines()
        command_output = "\n".join(output_lines[:-1])
        exit_status = output_lines[-1]

        # 创建失败信息变量
        failure_info = None
        if exit_status != '0' or error:
            failure_info = {
                'host': f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
                'reason': clean_ansi(f"Error: {error}\nExit Status: {exit_status}")
            }

        if exit_status == '0' and not error:
            return client, command_output, None, command, failure_info
        return client, None, clean_ansi(f"Error: {error}\nExit Status: {exit_status}"), command, failure_info
    except Exception as e:
        # 处理异常情况下的失败信息
        failure_info = {
            'host': f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
            'reason': clean_ansi(str(e))
        }
        return None, None, clean_ansi(str(e)), None, failure_info
    finally:
        if client:
            client.close()

async def process_account(account, send_messages, command):
    ssluser = account.get('ssluser') or account.get('username')
    password = account.get('password')
    sslhost = account.get('sslhost') or account.get('hostname')
    customhostname = account.get('customhostname', '').lower()
    secret_key_path = account.get('secretkey')
    port = account.get('port', 22)  # 默认为 22 如果未指定
    
    now_utc = format_to_iso(datetime.utcnow())
    now_beijing = format_to_iso(datetime.utcnow() + timedelta(hours=8))
    
    language = language_manager.get_language()
    logger.info(get_translation('processing_account', language).format(account=customhostname or ssluser))
    
    try:
        client, output, error, executed_command, failure_info = await asyncio.wait_for(
            execute_ssh_command(sslhost, ssluser, password, command, customhostname, secret_key_path, port, send_messages),
            timeout=180  # 总超时时间设置为180秒（3分钟）
        )
    except asyncio.TimeoutError:
        timeout_message = get_translation('host_operation_timeout', language).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}")
        if send_messages:
            await send_telegram_message(timeout_message)
        if send_update:
            await send_update(timeout_message)
        return False, {'host': f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}", 'reason': "Operation Timeout"}
    
    if client:
        login_success_message = get_translation('host_login_success', language).format(
            host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
            beijing_time=now_beijing,
            utc_time=now_utc
        )
        logger.info(login_success_message)
        if send_messages:
            await send_telegram_message(login_success_message)
        if send_update:
            await send_update(login_success_message)
        
        if not error:
            ssh_success_message = get_translation('host_command_success', language).format(
                host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
                command=executed_command
            )
            logger.info(ssh_success_message)
            if send_messages:
                await send_telegram_message(ssh_success_message)
            if send_update:
                await send_update(ssh_success_message)
            return True, None
        else:
            ssh_error_message = get_translation('host_command_failed', language).format(
                host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
                command=executed_command,
                error=clean_ansi(error)
            )
            logger.error(ssh_error_message)
            if send_messages:
                await send_telegram_message(ssh_error_message)
            if send_update:
                await send_update(ssh_error_message)
    else:
        ssh_error_message = get_translation('host_login_failed', language).format(
            host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
            beijing_time=now_beijing,
            utc_time=now_utc,
            error=clean_ansi(error)
        )
        logger.error(ssh_error_message)
        if send_messages:
            await send_telegram_message(ssh_error_message)
        if send_update:
            await send_update(ssh_error_message)
    
    return False, failure_info

async def main(accounts, send_messages=True, command=DEFAULT_COMMAND, target='all'):
    target_accounts = get_target_accounts(accounts, target)
    tasks = [process_account(account, send_messages, command) for account in target_accounts]
    results = await asyncio.gather(*tasks)
    success_count = sum(result[0] for result in results)
    total_count = len(target_accounts)
    
    # 收集失败信息
    failed_hosts = [result[1] for result in results if result[1] is not None]
    
    language = language_manager.get_language()
    completion_message = get_translation('all_hosts_complete', language).format(success_count=success_count, total_count=total_count)
    logger.info(completion_message)
    if send_messages:
        await send_telegram_message(completion_message)
        
        # 发送失败主机统计信息
        if failed_hosts:
            failure_message = "Failed hosts:\n" + "\n".join([f"{host['host']}: {clean_ansi(host['reason'])}" for host in failed_hosts])
            await send_telegram_message(failure_message)
    
    return success_count, total_count, failed_hosts
    
async def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"发送消息到Telegram失败: {await response.text()}")
                else:
                    logger.info(f"成功发送消息到Telegram: {message[:50]}...")
    except Exception as e:
        logger.error(f"发送消息到Telegram时发生错误: {str(e)}")

def get_target_accounts(accounts, target):
    if target == 'all':
        return accounts
    
    cron_tasks = json.loads(os.getenv('CRON_TASKS_JSON', '{}'))
    host_groups = cron_tasks.get('host_groups', {})
    
    target_accounts = []
    targets = target.split(',')
    
    for t in targets:
        t = t.strip()
        if t.startswith('group:'):
            group_name = t[6:]
            if group_name in host_groups:
                group_hosts = host_groups[group_name]
                target_accounts.extend([account for account in accounts if account.get('customhostname', '').lower() in group_hosts])
        elif t.startswith('+') or t.startswith('-'):
            n = int(t[1:])
            target_accounts.extend(accounts[:n] if t.startswith('+') else accounts[-n:])
        else:
            target_accounts.extend([account for account in accounts if account.get('customhostname', '').lower() == t.lower() or
                                    f"{account.get('ssluser', account.get('username'))}@{account.get('sslhost', account.get('hostname'))}".lower() == t.lower()])
    
    return list({account['customhostname']: account for account in target_accounts}.values())  # Remove duplicates

async def run_main(send_messages=True, command=DEFAULT_COMMAND, target='all'):
    accounts_json = os.getenv('ACCOUNTS_JSON')
    if accounts_json:
        accounts = json.loads(accounts_json)
        return await main(accounts, send_messages, command, target)
    else:
        language = language_manager.get_language()
        logger.error(get_translation('no_accounts_json', language))
        return 0, 0, []
        
if __name__ == "__main__":
    asyncio.run(run_main())
