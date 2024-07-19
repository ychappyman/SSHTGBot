from language_manager import language_manager

translations = {
    'zh': {
        # App.py translations
        'welcome_message': "您好！以下是可用的命令：\n"
                           "/language - 切换语言 (Switch language)\n"
                           "/start - 再次发送此帮助消息（输入非命令字符也可推送帮助）\n"
                           "/grouprun - 触发批量主机执行命令\n"
                           "/setcron <小时数> - 设置、查看执行命令的周期（例如：/setcron 24）\n"
                           "/setvartime <分钟数> - 设置、查看执行命令周期的随机变化范围（例如：/setvartime 10）\n"
                           "/ssh - 列出所有可用的主机\n"
                           "/ssh <customhostname 或 ssluser@sslhost> - 连接到指定的主机\n"
                           "/exit - 退出当前 SSH 会话\n"
                           "/setcommand <command> - 设置要执行的自定义命令（例如：/setcommand source ~/.profile && pm2 resurrect）\n"
                           "/setpathcom [command] - 设置、查看或清除要在指定路径下执行的自定义命令\n"
                           "   - 设置: /setpathcom pm2 resurrect\n"
                           "   - 查看: /setpathcom\n"
                           "   - 清除: /setpathcom clear\n"
                           "/uploadkeys - 批量上传公钥到远程主机",
        'feedback_button': "问题反馈",
        'no_permission': "您没有权限使用此命令。",
        'executing_command': "正在触发批量主机执行命令...",
        'current_settings': "当前执行命令的周期为 {interval} 小时\n"
                            "执行命令周期随机变化范围: ±{variation} 分钟\n",
        'next_execution_time': "下一次执行命令时间（已包含随机变化）：北京时间 {beijing_time}(UTC时间：{utc_time})\n",
        'time_until_next_execution': "距离下次执行命令还有：{days}天 {hours}小时 {minutes}分钟",
        'next_execution_passed': "下次执行命令已过，正在重新调度...",
        'next_execution_not_set': "下一次执行命令时间尚未设置",
        'invalid_hours': "请提供有效的小时数，例如：/setcron 24",
        'variation_too_large': "错误：当前随机变化范围（{variation}分钟）大于或等于周期时间（{interval}小时）。请先使用 /setvartime 命令设置一个更小的随机变化范围。",
        'cron_set': "执行命令周期已设置为 {interval} 小时\n"
                    "执行命令周期的随机变化范围: ±{variation} 分钟\n"
                    "下一次执行命令时间（已包含随机变化）：北京时间 {beijing_time}(UTC时间：{utc_time})",
        'current_variation': "当前执行命令周期的随机变化范围为 ±{variation} 分钟",
        'invalid_minutes': "请提供有效的分钟数，例如：/setvartime 10",
        'variation_set': "执行命令周期的随机变化范围已设置为 ±{variation} 分钟",
        'next_execution_updated': "执行命令周期保持为 {interval} 小时\n"
                                  "下一次执行命令时间（已包含新的随机变化）：北京时间 {beijing_time}(UTC时间：{utc_time})",
        'custom_command': "要执行的自定义命令为：{command}",
        'custom_command_set': "自定义命令已设置为：{command}",
        'current_pathcom': "当前设置的 pathcom 命令是：{command}",
        'no_pathcom': "当前没有设置 pathcom 命令。",
        'pathcom_cleared': "pathcom 命令已清除。",
        'no_pathcom_to_clear': "当前没有设置 pathcom 命令，无需清除。",
        'pathcom_set': "自定义路径命令已设置为：{command}",
        'command_executed': "命令执行完毕，无输出",
        'command_error': "执行命令时出错：{error}",
        'language_changed': "语言已切换为{language}。",
        'language_not_supported': "不支持的语言。目前支持的语言：中文(zh)，英文(en)",
        'webhook_setup_failed': "Webhook 设置失败，不发送欢迎消息",
        'scheduled_execution_start': "开始执行定时命令... (当前北京时间: {beijing_time})(UTC时间：{utc_time})",
        'scheduled_execution_complete': "定时执行命令完成。成功执行命令的主机数量：{success_count}/{total_count}。下一次执行命令时间:北京时间 {next_time}(UTC时间：{next_time_utc})",
        'bot_running': "批量定时执行 Bot 正在运行！",

        # SSH.py translations
        'connecting_to_host': "正在连接到{host}主机...",
        'connection_failed_retrying': "连接{host}主机失败，正在重试...",
        'connected_to_host': "已连接到{host}主机",
        'connection_failed': "连接失败：{error}",
        'available_hosts': "可用的主机：\n{hosts}",
        'host_not_found': "找不到主机：{host}",
        'active_ssh_session': "已有活动的 SSH 会话，请先使用 /exit 退出",
        'ssh_usage': "使用方法：/ssh 或 /ssh <customhostname 或 ssluser@sslhost>",
        'ssh_disconnected': "已断开 SSH 连接",
        'no_active_ssh': "当前没有活动的 SSH 连接",
        'ssh_session_timeout': "SSH 会话已超时，连接已断开",
        'command_execution_error': "执行命令时出错：{error}",
        'no_active_connection': "没有活动的 SSH 连接，请先使用 /ssh 连接到主机",
        'enter_password': "请输入密码（消息将在短时间后自动删除）：",
        'changed_directory': "已切换到目录：{dir}",
        'reconnected': "已重新连接到主机。",
        'reconnect_failed': "重新连接失败：{error}",

        # Group_run.py translations
        'processing_account': "正在处理账户: {account}",
        'host_operation_error': "{host}主机操作出错：\n{error}\n{traceback}",
        'host_login_success': "{host}主机于北京时间 {beijing_time}（UTC时间 {utc_time}）登录成功。",
        'host_command_success': "{host}主机已成功执行命令: {command}",
        'host_command_failed': "在{host}主机上执行命令失败。命令: {command}\n错误: {error}",
        'host_login_failed': "{host}主机于北京时间 {beijing_time}（UTC时间 {utc_time}）登录失败。错误: {error}",
        'all_hosts_complete': "所有主机执行命令完成！成功执行命令的主机数量：{success_count}/{total_count}",
        'no_accounts_json': "未设置 ACCOUNTS_JSON 环境变量",
        'command_execution_timeout': "{host}主机执行命令超时，正在重试...",
        'command_execution_failed': "{host}主机执行命令失败。",
        'host_operation_timeout': "{host}主机操作总时间超过3分钟，已退出。",

        # Upload_keys.py translations
        'accounts_json_not_set': 'ACCOUNTS_JSON 环境变量未设置。',
        'accounts_json_error': 'ACCOUNTS_JSON 格式错误。',
        'no_public_key': "{host} 无publickey",
        'no_login_password': "{host} 无登录密码",
        'public_key_upload_success': "{host} publickey上传成功",
        'public_key_upload_failed': "{host} publickey上传失败: {error}",

        # Switch language
        'current_language': "当前语言是：{language}",
        'language_usage': "使用 /language zh 切换到中文，或 /language en 切换到英文。"
    },
    'en': {
        # App.py translations
        'welcome_message': "Hello! Here are the available commands:\n"
                           "/language - Switch language (切换语言)\n"
                           "/start - Send this help message again (non-command input will also trigger help)\n"
                           "/grouprun - Trigger batch execution of commands on hosts\n"
                           "/setcron <hours> - Set or view the command execution interval (e.g., /setcron 24)\n"
                           "/setvartime <minutes> - Set or view the random variation range for command execution interval (e.g., /setvartime 10)\n"
                           "/ssh - List all available hosts\n"
                           "/ssh <customhostname or ssluser@sslhost> - Connect to a specific host\n"
                           "/exit - Exit the current SSH session\n"
                           "/setcommand <command> - Set the custom command to execute (e.g., /setcommand source ~/.profile && pm2 resurrect)\n"
                           "/setpathcom [command] - Set, view, or clear the custom command to be executed in a specific path\n"
                           "   - Set: /setpathcom pm2 resurrect\n"
                           "   - View: /setpathcom\n"
                           "   - Clear: /setpathcom clear\n"
                           "/uploadkeys - Batch upload public keys to remote hosts",
        'feedback_button': "Feedback",
        'no_permission': "You don't have permission to use this command.",
        'executing_command': "Triggering batch command execution on hosts...",
        'current_settings': "Current command execution interval: {interval} hours\n"
                            "Random variation range for execution interval: ±{variation} minutes\n",
        'next_execution_time': "Next command execution time (including random variation): Beijing time {beijing_time} (UTC time: {utc_time})\n",
        'time_until_next_execution': "Time until next execution: {days} days {hours} hours {minutes} minutes",
        'next_execution_passed': "Next execution time has passed, rescheduling...",
        'next_execution_not_set': "Next execution time is not set",
        'invalid_hours': "Please provide a valid number of hours, e.g., /setcron 24",
        'variation_too_large': "Error: Current random variation range ({variation} minutes) is greater than or equal to the interval ({interval} hours). Please use /setvartime to set a smaller variation range first.",
        'cron_set': "Command execution interval set to {interval} hours\n"
                    "Random variation range for execution interval: ±{variation} minutes\n"
                    "Next command execution time (including random variation): Beijing time {beijing_time} (UTC time: {utc_time})",
        'current_variation': "Current random variation range for command execution interval: ±{variation} minutes",
        'invalid_minutes': "Please provide a valid number of minutes, e.g., /setvartime 10",
        'variation_set': "Random variation range for command execution interval set to ±{variation} minutes",
        'next_execution_updated': "Command execution interval remains {interval} hours\n"
                                  "Next command execution time (including new random variation): Beijing time {beijing_time} (UTC time: {utc_time})",
        'custom_command': "Custom command to execute: {command}",
        'custom_command_set': "Custom command set to: {command}",
        'current_pathcom': "Current pathcom command: {command}",
        'no_pathcom': "No pathcom command is currently set.",
        'pathcom_cleared': "Pathcom command has been cleared.",
        'no_pathcom_to_clear': "No pathcom command is currently set, nothing to clear.",
        'pathcom_set': "Custom path command set to: {command}",
        'command_executed': "Command executed successfully, no output",
        'command_error': "Error executing command: {error}",
        'language_changed': "Language changed to {language}.",
        'language_not_supported': "Language not supported. Currently supported languages: Chinese (zh), English (en)",
        'webhook_setup_failed': "Webhook setup failed, not sending welcome message",
        'scheduled_execution_start': "Starting scheduled command execution... (Current Beijing time: {beijing_time})(UTC time: {utc_time})",
        'scheduled_execution_complete': "Scheduled command execution completed. Successfully executed on {success_count}/{total_count} hosts. Next execution time: Beijing time {next_time} (UTC time: {next_time_utc})",
        'bot_running': "Batch scheduled execution Bot is running!",

        # SSH.py translations
        'connecting_to_host': "Connecting to host {host}...",
        'connection_failed_retrying': "Connection to {host} failed, retrying...",
        'connected_to_host': "Connected to host {host}",
        'connection_failed': "Connection failed: {error}",
        'available_hosts': "Available hosts:\n{hosts}",
        'host_not_found': "Host not found: {host}",
        'active_ssh_session': "An active SSH session exists. Please use /exit first.",
        'ssh_usage': "Usage: /ssh or /ssh <customhostname or ssluser@sslhost>",
        'ssh_disconnected': "SSH connection disconnected",
        'no_active_ssh': "No active SSH connection",
        'ssh_session_timeout': "SSH session timed out, connection closed",
        'command_execution_error': "Error executing command: {error}",
        'no_active_connection': "No active SSH connection. Please use /ssh to connect to a host first.",
        'enter_password': "Please enter the password (this message will be deleted shortly):",
        'changed_directory': "Changed directory to: {dir}",
        'reconnected': "Reconnected to the host.",
        'reconnect_failed': "Failed to reconnect: {error}",

        # Group_run.py translations
        'processing_account': "Processing account: {account}",
        'host_operation_error': "Error in host operation for {host}:\n{error}\n{traceback}",
        'host_login_success': "Successfully logged in to {host} at Beijing time {beijing_time} (UTC time {utc_time}).",
        'host_command_success': "Successfully executed command on {host}: {command}",
        'host_command_failed': "Failed to execute command on {host}. Command: {command}\nError: {error}",
        'host_login_failed': "Failed to log in to {host} at Beijing time {beijing_time} (UTC time {utc_time}). Error: {error}",
        'all_hosts_complete': "Command execution completed on all hosts! Successfully executed on {success_count}/{total_count} hosts",
        'no_accounts_json': "ACCOUNTS_JSON environment variable not set",
        'command_execution_timeout': "Command execution timeout for {host}, retrying...",
        'command_execution_failed': "Command execution failed for {host}.",
        'host_operation_timeout': "Host operation for {host} exceeded 3 minutes, exiting.",

        # Upload_keys.py translations
        'accounts_json_not_set': 'ACCOUNTS_JSON environment variable is not set.',
        'accounts_json_error': 'ACCOUNTS_JSON format error.',
        'no_public_key': "No public key for {host}",
        'no_login_password': "No login password for {host}",
        'public_key_upload_success': "Public key uploaded successfully for {host}",
        'public_key_upload_failed': "Failed to upload public key for {host}: {error}",

        # Switch language
        'current_language': "Current language is: {language}",
        'language_usage': "Use /language zh to switch to Chinese, or /language en to switch to English."
    }
}

def get_translation(key, language=None):
    if language is None:
        language = language_manager.get_language()

    # 如果指定的语言不存在，使用中文作为后备
    return translations.get(language, translations['zh']).get(key, translations['zh'].get(key, key))
