<h1 align="center">SSHTGBot</h1>
<h3 align="center"><span style="font-size: 0.9em;"><a href="/README.md">简体中文</a></span> / <span style="font-size: 0.9em;">English</span></h3>

## Project Overview

SSHTGBot is a Telegram-based automation tool primarily designed for remote management and scheduled or manual execution of commands on multiple hosts (such as serv00). This project allows users to perform various operations through a Telegram bot interface, including SSH connections to hosts, execution of custom commands in bulk, and setting up scheduled tasks.

### Key Features

1. Remote control of hosts via Telegram bot interface
2. Support for SSH connections to multiple hosts
3. Execution of custom commands or predefined scripts
4. Scheduling of script execution tasks
5. Support for key-based authentication
6. Support for bulk public key upload
7. Support for scheduled task management (New)
8. Support for host grouping (New)
9. Support for time mode switching (hours/minutes) (New)

## Telegram Discussion Group

We welcome you to join our Telegram discussion group. Here you can discuss usage experiences with other users, get help, and stay updated on the latest project developments:

[Join SSHTGBot Discussion Group](https://t.me/+WIX6H-944HQzZmQ9)

## Deployment Method

### Prerequisites

1. A Telegram bot Token. Search for BotFather in Telegram, create a new Bot, and obtain the API Token.
2. Your Telegram user ID. To get this: Send a message to the Bot, then visit `https://api.telegram.org/bot<Your_API Token>/getUpdates` to obtain the Chat ID.
3. A Render account (for deployment)
4. Your host account information (including SSH username, password, and SSH address)

### Deployment Steps

1. Fork this project to your GitHub account.

2. Create a new Web Service in Render and connect it to your forked GitHub repository.

3. Set the following environment variables in Render:
   - `LAUNUAGE`:zh/en, Default language is Chinese
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot Token
   - `TELEGRAM_CHAT_ID`: Your Telegram user ID 
   - `ACCOUNTS_JSON`: JSON string containing host account information, formatted as follows:
     ```json
     [
       {
         "customhostname": "customhostname1", (Custom host name, recommended to set)
         "ssluser": "your_ssluser1", (SSH username)
         "password": "your_password1", (SSH password)
         "sslhost": "your_sslhost1", (SSH address, format example: "s5.serv00.com")
         "secretkey": "private key path 1 including private key file", (Optional, used to upload private key to render, set in Secret Files under render environment variables. Format example: /etc/secrets/<filename>. For security, it's recommended to delete SSH login password and public key after setting private key and uploading public key)
         "publickey": "public key path 1 including public key file, file extension .pub" (Optional, note no comma at the end of this line. Used to upload public key to SSH host, set in Secret Files under render environment variables. Format example: /etc/secrets/<filename>)
       },
       {
         "customhostname": "customhostname2",
         "ssluser": "your_ssluser2",
         "password": "your_password2",
         "sslhost": "your_sslhost2",
         "secretkey": "private key path 2",
         "publickey": "public key path 2"
       },     
       ...
     ]
     ```
   - `AUTO_CONNECT_INTERVAL`: Cycle time for scheduled tasks, optional, integer default 24, can be disabled by entering /set_cron 0 in telegram after deployment.
   - `RENDER_APP_URL`: Your Render application URL (format: https://*******.onrender.com, top left of the project, no / at the end of the address)
   - `CUSTOM_COMMAND`: Initial custom execution command (when set, custom commands will not be cleared after Render redeploys)
   - `TIME_MODE`: Time unit mode (hour/minute) sets whether the cycle unit is hours or minutes, minute mode allows for more precise control, default is hour mode.
   - `CRON_TASKS_JSON`: Scheduled tasks and host group configuration (New), formatted as follows:
     ```json
     {
         "tasks": [
             {
                 "id": "1", (Task number)
                 "command": "uptime", (Custom command)
                 "interval": 1, (Cycle time, hours in hour mode, minutes in minute mode)
                 "variation": 10, (Deviation time, minutes in hour mode, seconds in minute mode)
                 "target": "all"
             },
             {
                 "id": "2",
                 "command": "df -h",
                 "interval": 1,
                 "variation": 5,
                 "target": "+3" (First three hosts in ACCOUNTS_JSON, -3 would indicate the last 3 hosts)
             },
             {
                 "id": "3",
                 "command": "custom_command",
                 "interval": 1,
                 "variation": 2,
                 "target": "flypig,maxjiu,group:group2" (Host groups need to be prefixed with group:)
             }
         ],
         "host_groups": {
             "group1": [
                 "flypig",
                 "maxjiu"
             ],
             "group2": [
                 "hycl",
                 "happyboy"
             ]
         }
     }
     ```

4. Start Docker in Render.

Note: Render allows deployment of one free project, which may experience a 50s delay if not accessed for a long time. You can download UptimeRobot on your phone to keep it active for free.

## Usage Instructions

### Basic Commands

- `/language` - Switch language
- `/start` - Send this help message again (entering non-command characters will also push help)
- `/grouprundeault` - Trigger batch execution of commands on hosts
- `/setcron <hours>` - Set and view the cycle for executing commands (e.g., /setcron 24)
- `/setvartime <minutes>` - Set and view the random variation range for the command execution cycle (e.g., /setvartime 10)
- `/ssh` - List all available hosts
- `/ssh <customhostname or ssluser@sslhost>` - Connect to the specified host
- `/exit` - Exit the current SSH session
- `/setcommand <command>` - Set the custom command to execute (e.g., /setcommand source ~/.profile && pm2 resurrect)
- `/uploadkeys` - Bulk upload public keys to remote hosts (For security, it's recommended to delete SSH login password and public key after setting private key and uploading public key)

### New Commands (Scheduled Task Management)

- `/grouprun <command> [target]` - Execute custom command on specified hosts
  - Example: /addtask pwd all
  - Parameter description:
    - `target`: Target hosts (optional, default is "all", see Host Grouping and Target Selection for specific usage)
- `/addtask <command> <interval> <variation> [target]` - Add a new scheduled task
  - Example: /addtask uptime 2 10 all
  - Parameter description:
    - `interval`: Execution interval (hours or minutes, depending on current mode)
    - `variation`: Random variation range (minutes or seconds, depending on current mode)
    - `target`: Target hosts (optional, default is "all", see Host Grouping and Target Selection for specific usage)
- `/listtasks` - List all scheduled tasks
- `/removetask <task_id>` - Remove the specified scheduled task
- `/pausetask <task_id>` - Pause the specified scheduled task
- `/resumetask <task_id>` - Resume the specified scheduled task
- `/switchmode` - Switch time unit mode (hours/minutes), default is hour mode for compatibility.

### Host Grouping and Target Selection

When adding tasks or executing commands, you can specify target hosts in the following ways:

- `all`: All hosts
- `+N`: Select the first N hosts in ACCOUNTS_JSON (e.g., `+3`)
- `-N`: Select the last N hosts in ACCOUNTS_JSON (e.g., `-2`)
- `customhostname1,customhostname2,...`: Specify multiple hosts
- `group:group_name`: Use predefined host groups (configured in CRON_TASKS_JSON)

### Notes

- SSH sessions have a 15-minute timeout, after which the connection will automatically disconnect.
- All operations and execution results will be reported in real-time through the Telegram bot.
- Please ensure your custom commands are safe and will not cause damage to the hosts.
- The execution time of scheduled tasks may have slight deviations, this is designed to avoid all tasks executing simultaneously.

## Troubleshooting

If you encounter issues, please check the following points:

1. Ensure all environment variables are correctly set.
2. Check the Render logs for more detailed error information.
3. Make sure your Telegram bot Token is valid and the bot has been added to the specified chat.
4. Verify that the login information for the hosts is correct, including hostname, username, and password.
5. Check if the format of ACCOUNTS_JSON and CRON_TASKS_JSON is correct, ensuring all required fields are filled.

If the problem persists, please submit an issue to the project's GitHub repository.

## Disclaimer

This project is for educational and research purposes only. Any operations using this tool should comply with relevant laws, regulations, and service terms. Users are fully responsible for all consequences of using this tool.

The developers are not responsible for any direct or indirect losses caused by the use of this tool, including but not limited to data loss, system crashes, security vulnerabilities, and other issues. By using this tool, you agree to assume all related risks.

Please use this tool with caution and ensure you have permission to operate on the target hosts. Do not use this tool for illegal purposes or on unauthorized systems.
