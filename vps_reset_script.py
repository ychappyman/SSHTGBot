import json
import asyncio
from datetime import datetime, timedelta
import os
import paramiko
import aiohttp
import logging
import traceback

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 默认命令
DEFAULT_COMMAND = "source ~/.profile && pm2 resurrect"

def format_to_iso(date):
    return date.strftime('%Y-%m-%d %H:%M:%S')

async def execute_ssh_command(hostname, username, password, command, global_path, vps_path=None):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        logger.info(f"Connecting to {hostname}")
        connection_start = asyncio.get_event_loop().time()
        
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: client.connect(hostname, username=username, password=password)
                ),
                timeout=10
            )
        except asyncio.TimeoutError:
            await send_telegram_message(f"{username} VPS连接中...，请等待30s")
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: client.connect(hostname, username=username, password=password)
                    ),
                    timeout=20
                )
            except asyncio.TimeoutError:
                await send_telegram_message(f"{username} VPS连接超时。")
                return None, None, "Connection Timeout", None
        
        if global_path:
            if vps_path:  # 如果VPS有自己的路径设置
                cd_command = f"cd {vps_path} && "
                full_command = cd_command + global_path
            else:  # 如果VPS没有自己的路径设置
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
            await send_telegram_message(f"{username} VPS执行命令中...，请等待120s")
            try:
                output, error = await asyncio.wait_for(execute_and_read(), timeout=110)
            except asyncio.TimeoutError:
                await send_telegram_message(f"{username} VPS执行命令超时。")
                return None, None, f"Command Execution Timeout: {full_command}", full_command
        
        command_time = asyncio.get_event_loop().time() - command_start
        if command_time > 10:
            logger.info(f"Command execution took {command_time:.2f} seconds")
        
        if not error:
            return client, output, None, full_command
        return client, None, error, full_command
    except Exception as e:
        logger.error(f"Error executing SSH command: {str(e)}")
        return None, None, str(e), None
    finally:
        if client:
            client.close()
            
async def process_account(account, send_messages, command, global_path):
    username = account['username']
    password = account['password']
    hostname = account['hostname']
    vps_path = account.get('path')
    
    now_utc = format_to_iso(datetime.utcnow())
    now_beijing = format_to_iso(datetime.utcnow() + timedelta(hours=8))
    
    logger.info(f"Processing account: {username}")
    
    try:
        client, output, error, full_command = await asyncio.wait_for(
            execute_ssh_command(hostname, username, password, command, global_path, vps_path),
            timeout=180  # 总超时时间设置为180秒（3分钟）
        )
    except asyncio.TimeoutError:
        await send_telegram_message(f"{username} VPS操作总时间超过3分钟，已退出。")
        return False
    except Exception as e:
        error_message = f"{username} VPS操作出错：\n{str(e)}\n{traceback.format_exc()}"
        logger.error(error_message)
        await send_telegram_message(error_message)
        return False
    
    if client:
        login_success_message = f'{hostname}账号 {username} 于北京时间 {now_beijing}（UTC时间 {now_utc}）登录成功。'
        logger.info(login_success_message)
        if send_messages:
            await send_telegram_message(login_success_message)
        
        if not error:
            ssh_success_message = f'{username}: {hostname} 已成功执行命令: {full_command}'
            logger.info(ssh_success_message)
            if send_messages:
                await send_telegram_message(ssh_success_message)
            return True
        else:
            ssh_error_message = f'在 {hostname} 上执行命令失败。命令: {full_command}\n错误: {error}'
            logger.error(ssh_error_message)
            if send_messages:
                await send_telegram_message(ssh_error_message)
    else:
        ssh_error_message = f'{hostname}账号 {username} 于北京时间 {now_beijing}（UTC时间 {now_utc}）登录失败。错误: {error}'
        logger.error(ssh_error_message)
        if send_messages:
            await send_telegram_message(ssh_error_message)
    
    return False
    
async def main(accounts, send_messages=True, command=DEFAULT_COMMAND, global_path=None):
    tasks = [process_account(account, send_messages, command, global_path) for account in accounts]
    results = await asyncio.gather(*tasks)
    success_count = sum(results)
    total_count = len(accounts)
    
    completion_message = f'所有VPS账号操作完成！成功执行命令的VPS数量：{success_count}/{total_count}'
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
        logger.error("No ACCOUNTS_JSON environment variable set")
        return 0, 0

if __name__ == "__main__":
    run_main()
