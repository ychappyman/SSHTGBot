<h1 align="center">SSHTGBot</h1>
<h3 align="center"><span style="font-size: 0.9em;"><a href="/README.md">简体中文</a></span> / <span style="font-size: 0.9em;">English</span></h3>

## Project Introduction

SSHTGBot is a Telegram-based automation tool primarily used for remote management and scheduled or manual execution of commands on multiple hosts (such as sevr00). This project allows users to perform various operations through a Telegram bot interface, including SSH connections to hosts, executing batch custom commands, setting up scheduled tasks, and more.

### Main Features

1. Remote control of hosts through Telegram bot interface
2. Support for SSH connections to multiple hosts
3. Execute custom commands or preset scripts
4. Set up scheduled script execution tasks
5. Support for key-based login
6. Support for batch public key upload

## Telegram Discussion Group

Welcome to join our Telegram discussion group, where you can discuss usage experiences with other users, get help, and learn about the latest project updates:

[Join SSHTGBot Discussion Group](https://t.me/+WIX6H-944HQzZmQ9)

## Deployment Method

### Preparations

1. A Telegram bot Token. Search for BotFather in Telegram, create a new Bot, and obtain the API Token.
2. Your Telegram user ID. To obtain: Send a message to the Bot, visit `https://api.telegram.org/bot<your_bot_token>/getUpdates` to get the Chat ID.
3. A Render account (for deployment)
4. Your host account information (including SSH username, password, and SSH address)

### Deployment Steps

1. Fork this project to your GitHub account.

2. Create a new Web Service in Render and connect it to your forked GitHub repository.

3. Set the following variables in Render's environment variables:
   - `LAUNUAGE`: Default language is Chinese
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot Token
   - `TELEGRAM_CHAT_ID`: Your Telegram user ID
   - `ACCOUNTS_JSON`: JSON string containing host account information, formatted as follows:
     ```json
     [
       {
         "customhostname": "customhostname1",(custom hostname, recommended to set)
         "ssluser": "your_ssluser1",(SSH username)
         "password": "your_password1",(SSH password)
         "sslhost": "your_sslhost1",(SSH address, format example: "s5.serv00.com")
         "secretkey": "render Secret Files secretkey path1",(Set under render environment variables. Format example: /etc/secrets/<filename>)
         "publickey": "render Secret Files publickey path1 file suffix .pub",(Set under render environment variables. Format example: /etc/secrets/<filename>)
         "path": "optional_path1"(Note: no comma at the end of this last line. This path line is optional. If not set and setpathcom is set, it will skip path and execute the default setcommand command.
                               Format example: "~/domains/ssgj.dns-dynamic.net/vless")
       },
       {
         "customhostname": "customhostname2",
         "ssluser": "your_ssluser2",
         "password": "your_password2",
         "sslhost": "your_sslhost2",
         "secretkey": "render Secret Files secretkey path2",
         "publickey": "render Secret Files publickey path2",
         "path": "optional_path2"
       },     
       ...
     ]
     ```
   - `AUTO_CONNECT_INTERVAL`: Time interval for automatic reset (hours), optional, default is 24, can be turned off by entering /set_cron 0 in Telegram after deployment.
   - `RENDER_APP_URL`: Your Render application URL (format: https://*******.onrender.com, in the upper left corner of the project, do not include a / at the end of the address)
   - `CUSTOM_COMMAND`: Initial custom execution command (after setting, the custom command will not be cleared after Render redeployment)

4. Start Docker in Render.

Note: Render can deploy one free project, but there may be a 50s delay if not accessed for a long time. You can download UptimeRobot on your phone to keep it active for free.

## Usage Instructions

### Basic Commands

- `/language` - Switch language
- `/start` - Send this help message again (entering non-command characters can also push help)
- `/grouprun` - Trigger batch host command execution
- `/setcron <hours>` - Set and view the command execution cycle (e.g., /setcron 24)
- `/setvartime <minutes>` - Set and view the random variation range for the command execution cycle (e.g., /setvartime 10)
- `/ssh` - List all available hosts
- `/ssh <customhostname or ssluser@sslhost>` - Connect to the specified host
- `/exit` - Exit the current SSH session
- `/setcommand <command>` - Set the custom command to be executed (e.g., /setcommand source ~/.profile && pm2 resurrect)
- `/setpathcom [command]` - Set, view, or clear the custom command to be executed in the specified path
   - Set: `/setpathcom pm2 resurrect`
   - View: `/setpathcom`
   - Clear: `/setpathcom clear`
- `/uploadkeys` - Batch upload public keys to remote hosts (after setting keys and uploading public keys, it is recommended to delete SSH login passwords and public keys for security)

### Notes

- SSH sessions have a 15-minute timeout, after which the connection will automatically disconnect.
- All operations and execution results will be reported in real-time through the Telegram bot.
- Please ensure that your custom commands are safe and will not cause damage to the hosts.

## Troubleshooting

If you encounter problems, please check the following points:

1. Ensure all environment variables are correctly set.
2. Check Render logs for more detailed error information.
3. Make sure your Telegram bot Token is valid and the bot has been added to the specified chat.
4. Verify that the host login information is correct, including hostname, username, and password.

If the problem persists, please submit an issue to the project's GitHub repository.

## Disclaimer

This project is for educational and research purposes only. Any operations using this tool should comply with relevant laws, regulations, and service terms. Users are fully responsible for all consequences of using this tool.

The developers are not responsible for any direct or indirect losses caused by using this tool, including but not limited to data loss, system crashes, security vulnerabilities, and other issues. By using this tool, you agree to assume all related risks.

Please use this tool with caution and ensure you have permission to operate on the target hosts. Do not use this tool for illegal purposes or on unauthorized systems.
