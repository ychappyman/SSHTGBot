import json
import paramiko
import os
from telegram import Update
from telegram.ext import ContextTypes
from translations import get_translation
from language_manager import language_manager

async def upload_public_keys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    language = language_manager.get_language()
    
    if str(chat_id) != os.getenv('TELEGRAM_CHAT_ID'):
        await update.message.reply_text(get_translation('no_permission', language))
        return

    accounts_json = os.getenv('ACCOUNTS_JSON')
    if not accounts_json:
        await update.message.reply_text(get_translation('accounts_json_not_set', language))
        return

    try:
        accounts = json.loads(accounts_json)
    except json.JSONDecodeError:
        await update.message.reply_text(get_translation('accounts_json_error', language))
        return

    results = []
    for account in accounts:
        customhostname = account.get('customhostname', '').lower()
        sslhost = account.get('sslhost') or account.get('hostname')
        ssluser = account.get('ssluser') or account.get('username')
        password = account.get('password')
        public_key_path = account.get('publickey')
        host_identifier = f"{customhostname + ': ' if customhostname else ''}{ssluser}@{sslhost}"

        if not public_key_path:
            results.append(get_translation('no_public_key', language).format(host=host_identifier))
            continue

        if not password:
            results.append(get_translation('no_login_password', language).format(host=host_identifier))
            continue

        try:
            with open(public_key_path, 'r') as f:
                public_key = f.read().strip()

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(sslhost, username=ssluser, password=password)
            ssh.exec_command(f'mkdir -p ~/.ssh && echo "{public_key}" >> ~/.ssh/authorized_keys')
            ssh.close()

            results.append(get_translation('public_key_upload_success', language).format(host=host_identifier))
        except Exception as e:
            results.append(get_translation('public_key_upload_failed', language).format(host=host_identifier, error=str(e)))

    await update.message.reply_text("\n".join(results))

if __name__ == "__main__":
    print("This script is intended to be imported and used by the main Telegram bot script.")