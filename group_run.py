# group_run.py

import json
import asyncio
from datetime import datetime, timedelta
import os
import paramiko
import aiohttp
import logging
import traceback
from translations import get_translation

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
LANGUAGE = os.getenv('LANGUAGE', 'zh')

# 默认命令
DEFAULT_COMMAND = "source ~/.profile && pm2 resurrect"

def format_to_iso(date):
    return date.strftime('%Y-%m-%d %H:%M:%S')

async def execute_ssh_command(sslhost, ssluser, password, command, global_path, customhostname='', vps_path=None, secret_key_path=None):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        logger.info(get_translation('processing_account', LANGUAGE).format(account=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        connection_start = asyncio.get_event_loop().time()
        
        try:
            if secret_key_path:
                private_key = paramiko.RSAKey.from_private_key_file(secret_key_path)
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: client.connect(sslhost, username=ssluser, pkey=private_key)
                    ),
                    timeout=10
                )
            else:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: client.connect(sslhost, username=ssluser, password=password)
                    ),
                    timeout=10
                )
        except asyncio.TimeoutError:
            await send_telegram_message(get_translation('connecting_to_host', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
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
                await send_telegram_message(get_translation('connection_failed', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
                return None, None, "Connection Timeout", None
        
        if global_path:
            if vps_path:  # 如果主机有自己的路径设置
                cd_command = f"cd {vps_path} && "
                full_command = cd_command + global_path
            else:  # 如果主机没有自己的路径设置
                full_command = command  # 使用普通的setcommand命令
        else:
            full_command = command

        logger.info(f"Executing command: {full_command}")
        command_start = asyncio.get_event_loop().time()
        
        async def execute_and_read():
            stdin, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.exec_command(full_command)
            )
            output = await asyncio.get_event_loop().run_in_executor(None, stdout.read)
            error = await asyncio.get_event_loop().run_in_executor(None, stderr.read)
            return output.decode(), error.decode()

        try:
            output, error = await asyncio.wait_for(execute_and_read(), timeout=10)
        except asyncio.TimeoutError:
            await send_telegram_message(get_translation('command_execution_timeout', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
            try:
                output, error = await asyncio.wait_for(execute_and_read(), timeout=110)
            except asyncio.TimeoutError:
                await send_telegram_message(get_translation('command_execution_failed', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
                return None, None, f"Command Execution Timeout: {full_command}", full_command
        
        command_time = asyncio.get_event_loop().time() - command_start
        if command_time > 10:
            logger.info(f"Command execution took {command_time:.2f} seconds")
        
        if not error:
            return client, output, None, full_command
        return client, None, error, full_command
    except Exception as e:
        logger.error(get_translation('host_operation_error', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}", error=str(e), traceback=traceback.format_exc()))
        return None, None, str(e), None
    finally:
        if client:
            client.close()

async def process_account(account, send_messages, command, global_path):
    ssluser = account.get('ssluser') or account.get('username')
    password = account.get('password')
    sslhost = account.get('sslhost') or account.get('hostname')
    vps_path = account.get('path')
    customhostname = account.get('customhostname', '').lower()
    secret_key_path = account.get('secretkey')
    
    now_utc = format_to_iso(datetime.utcnow())
    now_beijing = format_to_iso(datetime.utcnow() + timedelta(hours=8))
    
    logger.info(get_translation('processing_account', LANGUAGE).format(account=customhostname or ssluser))
    
    try:
        client, output, error, full_command = await asyncio.wait_for(
            execute_ssh_command(sslhost, ssluser, password, command, global_path, customhostname, vps_path, secret_key_path),
            timeout=180  # 总超时时间设置为180秒（3分钟）
        )
    except asyncio.TimeoutError:
        await send_telegram_message(get_translation('host_operation_timeout', LANGUAGE).format(host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"))
        return False
    except Exception as e:
        error_message = get_translation('host_operation_error', LANGUAGE).format(
            host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
            error=str(e),
            traceback=traceback.format_exc()
        )
        logger.error(error_message)
        await send_telegram_message(error_message)
        return False
    
    if client:
        login_success_message = get_translation('host_login_success', LANGUAGE).format(
            host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
            beijing_time=now_beijing,
            utc_time=now_utc
        )
        logger.info(login_success_message)
        if send_messages:
            await send_telegram_message(login_success_message)
        
        if not error:
            ssh_success_message = get_translation('host_command_success', LANGUAGE).format(
                host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
                command=full_command
            )
            logger.info(ssh_success_message)
            if send_messages:
                await send_telegram_message(ssh_success_message)
            return True
        else:
            ssh_error_message = get_translation('host_command_failed', LANGUAGE).format(
                host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
                command=full_command,
                error=error
            )
            logger.error(ssh_error_message)
            if send_messages:
                await send_telegram_message(ssh_error_message)
    else:
        ssh_error_message = get_translation('host_login_failed', LANGUAGE).format(
            host=f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}",
            beijing_time=now_beijing,
            utc_time=now_utc,
            error=error
        )
        logger.error(ssh_error_message)
        if send_messages:
            await send_telegram_message(ssh_error_message)
    
    return False

async def main(accounts, send_messages=True, command=DEFAULT_COMMAND, global_path=None):
    tasks = [process_account(account, send_messages, command, global_path) for account in accounts]
    results = await asyncio.gather(*tasks)
    success_count = sum(results)
    total_count = len(accounts)
    
    completion_message = get_translation('all_hosts_complete', LANGUAGE).format(success_count=success_count, total_count=total_count)
    logger.info(completion_message)
    if send_messages:
        await send_telegram_message(completion_message)
    return success_count, total_count

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

def run_main(send_messages=True, command=DEFAULT_COMMAND, global_path=None):
    accounts_json = os.getenv('ACCOUNTS_JSON')
    if accounts_json:
        accounts = json.loads(accounts_json)
        return asyncio.run(main(accounts, send_messages, command, global_path))
    else:
        logger.error(get_translation('no_accounts_json', LANGUAGE))
        return 0, 0

if __name__ == "__main__":
    run_main()
