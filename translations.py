from language_manager import language_manager
import logging

logger = logging.getLogger(__name__)

translations = {
    'zh': {
        # App.py translations
        'welcome_message': "您好！当前时间单位模式：{time_mode}，以下是可用的命令：\n"
                       "/start - 再次发送此帮助消息（输入非命令字符也可推送帮助）\n"
                       "/grouprundefault - 执行默认命令（通过/setcommand设置）\n"
                       "/setcommand <command> - 设置要执行的自定义命令\n"
                       "/setcron <时间> - 设置定时执行间隔（当前单位为{unit}）\n"
                       "/setvartime <时间> - 设置时间变化范围（当前单位为{variation_unit}）\n"
                       "/ssh - 列出所有可用的主机\n"
                       "/ssh <customhostname 或 ssluser@sslhost> - 连接到指定的主机\n"
                       "/exit - 退出当前 SSH 会话\n"
                       "/uploadkeys - 批量上传公钥到远程主机\n"
                       "/grouprun <命令> [目标] - 触发批量主机执行命令\n"
                       "/addtask - 添加新的定时任务\n"
                       "/listtasks - 列出所有定时任务\n"
                       "/removetask - 删除指定的定时任务\n"
                       "/pausetask <任务ID 或 all> - 暂停指定任务或所有任务\n"
                       "/resumetask <任务ID 或 all> - 恢复指定任务或所有任务\n"      
                       "/switchmode - 切换时间单位模式（小时/分钟）\n"
                       "/language - 切换语言 (Switch language)",
        'feedback_button': "问题反馈",
        'no_permission': "您没有权限使用此命令。",
        'unknown_command': '命令错误，请仔细核查。',
        'executing_command': "正在触发批量主机执行命令...",
        'executing_default_command': "正在执行默认命令...",
        'current_settings': "当前执行命令的周期为 {interval} {interval_unit}\n"
                            "执行命令周期随机变化范围: ±{variation} {variation_unit}\n",
        'time_until_next_execution_minutes': "距离下次执行命令还有：{minutes}分钟",
        'next_execution_time': "下一次执行命令时间（已包含随机变化）：北京时间 {beijing_time}(UTC时间：{utc_time})\n",
        'time_until_next_execution': "距离下次执行命令还有：{days}天 {hours}小时 {minutes}分钟",
        'next_execution_passed': "下次执行命令已过，正在重新调度...",
        'next_execution_not_set': "下一次执行命令时间尚未设置",
        'invalid_time_unit': "请提供有效的{time_mode}数，例如：/setcron 24",
        'variation_too_large': "错误：当前随机变化范围（{variation}{variation_unit}）大于或等于周期时间（{interval}{interval_unit}）。请先使用 /setvartime 命令设置一个更小的随机变化范围。",
        'cron_set': "执行命令周期已设置为 {interval} {interval_unit}\n"
                    "执行命令周期的随机变化范围: ±{variation} {variation_unit}\n"
                    "下一次执行命令时间（已包含随机变化）：北京时间 {beijing_time}(UTC时间：{utc_time})",
        'current_variation': "当前执行命令周期的随机变化范围为 ±{variation} {variation_unit}",
        'variation_set': "执行命令周期的随机变化范围已设置为 ±{variation} {variation_unit}",
        'next_execution_updated': "执行命令周期保持为 {interval} {interval_unit}\n"
                                  "下一次执行命令时间（已包含新的随机变化）：北京时间 {beijing_time}(UTC时间：{utc_time})",
        'custom_command': "要执行的自定义命令为：{command}",
        'custom_command_set': "自定义命令已设置为：{command}",
        'command_executed': "命令执行完毕，无输出",
        'command_error': "执行命令时出错：{error}",
        'language_changed': "语言已切换为{language}。",
        'language_not_supported': "不支持的语言。目前支持的语言：中文(zh)，英文(en)",
        'webhook_setup_failed': "Webhook 设置失败，不发送欢迎消息",
        'scheduled_execution_start': "开始执行定时命令... (当前北京时间: {beijing_time})(UTC时间：{utc_time})",
        'scheduled_execution_complete': "定时执行命令完成。成功执行命令的主机数量：{success_count}/{total_count}。下一次执行命令时间:北京时间 {next_time}(UTC时间：{next_time_utc})",
        'bot_running': "批量定时执行 Bot 正在运行！",
        'grouprun_usage': "使用方法: /grouprun <命令> [目标]\n"
                          "目标可以是：\n"
                          "- 'all' 表示所有主机（默认）\n"
                          "- '+n' 或 '-n' 表示前n个或后n个主机\n"
                          "- 逗号分隔的主机名列表\n"
                          "- 逗号分隔的组名列表（以 'group:' 为前缀）\n"
                          "- 以上类型的组合，用逗号分隔\n"
                          "如果不指定目标，默认为 'all'",
        'addtask_usage': "使用方法: /addtask <命令> <周期> <偏差> [目标]\n"
                         "目标可以是：\n"
                         "- 'all' 表示所有主机（默认）\n"
                         "- '+n' 或 '-n' 表示前n个或后n个主机\n"
                         "- 逗号分隔的主机名列表\n"
                         "- 逗号分隔的组名列表（以 'group:' 为前缀）\n"
                         "- 以上类型的组合，用逗号分隔\n"
                         "如果不指定目标，默认为 'all'\n"
                         "当前模式为{time_mode}，周期单位为{interval_unit}，偏差单位为{variation_unit}",
        'task_added_detailed': "新任务已添加：\n"
                               "ID: {task_id}\n"
                               "命令: {command}\n"
                               "间隔: {interval}{interval_unit}\n"
                               "变化范围: ±{variation}{variation_unit}\n"
                               "目标: {target}\n"
                               "下次执行时间: {next_run} (北京时间){next_run_utc} (UTC)",
        'no_tasks': "当前没有定时任务",
        'task_list_header': "任务列表：",
        'task_info': ("ID: {id}\n"
                  "命令: {command}\n"
                  "间隔: {interval}{interval_unit}\n"
                  "变化范围: ±{variation}{variation_unit}\n"
                  "目标: {target}\n"
                  "下次执行时间: {next_run} (北京时间){next_run_utc} (UTC)\n"
                  "状态: {status}"),
        'hours': "小时",
        'minutes': "分钟",
        'seconds': "秒",
        'hour': "小时",
        'minute': "分钟",
        'second': "秒",
        'active': "活动",
        'paused': "暂停",
        'not_scheduled': "未调度",
        'hour_mode': "小时模式",
        'minute_mode': "分钟模式",
        'task_list': "当前的定时任务列表：",
        'removetask_usage': "使用方法: /removetask <任务ID>",
        'task_removed': "任务 {task_id} 已被删除",
        'task_not_found': "找不到任务 {task_id}",
        'invalid_target': '无效的目标。请确保所有主机名或组名都是有效的。',
        'invalid_interval': '无效的间隔时间。间隔时间必须大于0{interval_unit}。',
        'invalid_variation': '无效的偏差时间。偏差时间必须大于等于0{variation_unit}且小于间隔时间。',
        'cron_disabled': '定时执行已关闭。',
        'task_execution_start': "任务<{task_id}>：{target} 开始执行定时命令 <{command}>... (当前北京时间: {beijing_time})(UTC时间：{utc_time})",
        'task_execution_complete': "任务<{task_id}>：{target} 定时执行命令 <{command}> 完成，成功执行命令的主机数量：{success_count}/{total_count}。下一次执行命令时间: 北京时间 {next_run_beijing}(UTC时间：{next_run_utc})",
        'pausetask_usage': '使用方法: /pausetask <任务ID 或 all>',
        'resumetask_usage': '使用方法: /resumetask <任务ID 或 all>',
        'all_tasks_paused': '所有任务已暂停，共 {count} 个任务。',
        'all_tasks_resumed': '所有任务已恢复，共 {count} 个任务。',
        'task_paused': '任务 {task_id} 已暂停',
        'task_resumed': '任务 {task_id} 已重新启动',
        'task_not_found': '未找到任务 {task_id}',
        'mode_switched': '时间单位模式已切换为 {time_mode}。所有任务已更新。',

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
        'SSH_CONNECTION_TIMEOUT': "SSH 连接超时，超过 50 秒未响应。",
        'ssh_force_disconnected': "已强制断开 SSH 连接。如果有正在运行的命令，它可能仍在远程主机上继续执行。",

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
        'welcome_message': "Hello! Current time unit mode: {time_mode}, here are the available commands:\n"
                       "/start - Send this help message again (non-command input will also trigger help)\n"
                       "/grouprundefault - Execute the default command (set by /setcommand)\n"
                       "/setcommand <command> - Set the custom command to execute\n"
                       "/setcron <time> - Set the execution interval (current unit is {unit})\n"
                       "/setvartime <time> - Set the time variation range (current unit is {variation_unit})\n"
                       "/ssh - List all available hosts\n"
                       "/ssh <customhostname or ssluser@sslhost> - Connect to a specific host\n"
                       "/exit - Exit the current SSH session\n"
                       "/uploadkeys - Batch upload public keys to remote hosts\n"
                       "/grouprun <command> [target] - Trigger batch execution of commands on hosts\n"
                       "/addtask - Add a new scheduled task\n"
                       "/listtasks - List all scheduled tasks\n"
                       "/removetask - Remove a specified task\n"
                       "/pausetask <task ID or all> - Pause specified task or all tasks\n"
                       "/resumetask <task ID or all> - Resume specified task or all tasks\n"
                       "/switchmode - Switch time unit mode (Hour/Minute)\n"
                       "/language - Switch language (切换语言)",
        'feedback_button': "Feedback",
        'no_permission': "You don't have permission to use this command.",
        'unknown_command': 'Command error, please check carefully.',
        'executing_command': "Triggering batch command execution on hosts...",
        'executing_default_command': "Executing default command...",
        'current_settings': "Current command execution interval: {interval} {interval_unit}\n"
                            "Random variation range for execution interval: ±{variation} {variation_unit}\n",
        'time_until_next_execution_minutes': "Time until next execution: {minutes} minutes",
        'next_execution_time': "Next command execution time (including random variation): Beijing time {beijing_time} (UTC time: {utc_time})\n",
        'time_until_next_execution': "Time until next execution: {days} days {hours} hours {minutes} minutes",
        'next_execution_passed': "Next execution time has passed, rescheduling...",
        'next_execution_not_set': "Next execution time is not set",
        'invalid_time_unit': "Please provide a valid number of {time_mode}, e.g., /setcron 24",
        'variation_too_large': "Error: Current random variation range ({variation} {variation_unit}) is greater than or equal to the interval ({interval} {interval_unit}). Please use /setvartime to set a smaller variation range first.",
        'cron_set': "Command execution interval set to {interval} {interval_unit}\n"
                    "Random variation range for execution interval: ±{variation} {variation_unit}\n"
                    "Next command execution time (including random variation): Beijing time {beijing_time} (UTC time: {utc_time})",
        'current_variation': "Current random variation range for command execution interval: ±{variation} {variation_unit}",
        'variation_set': "Random variation range for command execution interval set to ±{variation} {variation_unit}",
        'next_execution_updated': "Command execution interval remains {interval} {interval_unit}\n"
                                  "Next command execution time (including new random variation): Beijing time {beijing_time} (UTC time: {utc_time})",
        'custom_command': "Custom command to execute: {command}",
        'custom_command_set': "Custom command set to: {command}",
        'command_executed': "Command executed successfully, no output",
        'command_error': "Error executing command: {error}",
        'language_changed': "Language changed to {language}.",
        'language_not_supported': "Language not supported. Currently supported languages: Chinese (zh), English (en)",
        'webhook_setup_failed': "Webhook setup failed, not sending welcome message",
        'scheduled_execution_start': "Starting scheduled command execution... (Current Beijing time: {beijing_time})(UTC time: {utc_time})",
        'scheduled_execution_complete': "Scheduled command execution completed. Successfully executed on {success_count}/{total_count} hosts. Next execution time: Beijing time {next_time} (UTC time: {next_time_utc})",
        'bot_running': "Batch scheduled execution Bot is running!",
        'grouprun_usage': "Usage: /grouprun <command> [target]\n"
                          "Target can be:\n"
                          "- 'all' for all hosts (default)\n"
                          "- '+n' or '-n' for the first or last n hosts\n"
                          "- Comma-separated list of hostnames\n"
                          "- Comma-separated list of group names (prefixed with 'group:')\n"
                          "- Combination of the above, separated by commas\n"
                          "If no target is specified, 'all' is used by default",
        'addtask_usage': "Usage: /addtask <command> <interval> <variation> [target]\n"
                         "Target can be:\n"
                         "- 'all' for all hosts (default)\n"
                         "- '+n' or '-n' for the first or last n hosts\n"
                         "- Comma-separated list of hostnames\n"
                         "- Comma-separated list of group names (prefixed with 'group:')\n"
                         "- Combination of the above, separated by commas\n"
                         "If no target is specified, 'all' is used by default\n"
                         "Current mode is {time_mode}, interval unit is {interval_unit}, variation unit is {variation_unit}",
        'task_added': "Task added, ID: {task_id}",
        'task_added_detailed': "New task added:\n"
                               "ID: {task_id}\n"
                               "Command: {command}\n"
                               "Interval: {interval}{interval_unit}\n"
                               "Variation: ±{variation}{variation_unit}\n"
                               "Target: {target}\n"
                               "Next run: {next_run} (Beijing time)\n"
                               "          {next_run_utc} (UTC)",
        'no_tasks': "There are currently no scheduled tasks",
        'task_list_header': "Task List:",
        'task_info': ("ID: {id}\n"
                  "Command: {command}\n"
                  "Interval: {interval}{interval_unit}\n"
                  "Variation: ±{variation}{variation_unit}\n"
                  "Target: {target}\n"
                  "Next execution: {next_run} (Beijing Time){next_run_utc} (UTC)\n"
                  "Status: {status}"),
        'hours': "hours",
        'minutes': "minutes",
        'seconds': "seconds",
        'hour': "hour",
        'minute': "minute",
        'second': "second",
        'active': "Active",
        'paused': "Paused",
        'not_scheduled': "Not scheduled",
        'hour_mode': "hour-mode",
        'minute_mode': "minute-mode",
        'task_list': "Current list of scheduled tasks:",
        'removetask_usage': "Usage: /removetask <task_id>",
        'task_removed': "Task {task_id} has been removed",
        'task_not_found': "Task {task_id} not found",
        'invalid_target': 'Invalid target. Please ensure all hostnames or group names are valid.',
        'invalid_interval': 'Invalid interval. The interval must be greater than 0 {interval_unit}.',
        'invalid_variation': 'Invalid variation. The variation must be greater than or equal to 0 {variation_unit} and less than the interval.',
        'cron_disabled': 'Scheduled execution has been disabled.',
        'task_execution_start': "Task <{task_id}>: {target} starts executing scheduled command <{command}>... (Current Beijing time: {beijing_time})(UTC time: {utc_time})",
        'task_execution_complete': "Task <{task_id}>: {target} completed scheduled command <{command}>, number of hosts successfully executed: {success_count}/{total_count}. Next execution time: Beijing time {next_run_beijing}(UTC time: {next_run_utc})",
        'pausetask_usage': 'Usage: /pausetask <task ID or all>',
        'resumetask_usage': 'Usage: /resumetask <task ID or all>',
        'all_tasks_paused': 'All tasks have been paused, total {count} tasks.',
        'all_tasks_resumed': 'All tasks have been resumed, total {count} tasks.',
        'task_paused': 'Task {task_id} has been paused',
        'task_resumed': 'Task {task_id} has been resumed',
        'task_not_found': 'Task {task_id} not found',
        'mode_switched': 'Time unit mode has been switched to {time_mode}. All tasks have been updated.',

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
        'SSH_CONNECTION_TIMEOUT': "SSH connection timed out after 50 seconds.",
        'ssh_force_disconnected': "SSH connection forcibly disconnected. If there was a running command, it may still be executing on the remote host.",

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

def get_translation(key, language=None, **kwargs):
    if language is None:
        language = language_manager.get_language()

    # 如果指定的语言不存在，使用英文作为后备
    translation = translations.get(language, translations['en']).get(key, translations['en'].get(key, key))

    # 不进行格式化，直接返回翻译字符串
    return translation
