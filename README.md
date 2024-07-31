<h1 align="center">SSHTGBot</h1>
<h3 align="center"><span style="font-size: 0.9em;">简体中文</span> / <a href="/.github/README_en.md" style="font-size: 0.9em;">English</a></h3>

## 项目简介

SSHTGBot 是一个基于 Telegram 的自动化工具，主要用于远程管理和定时、手动执行命令到多个主机（如sevr00）。该项目允许用户通过 Telegram 机器人界面执行各种操作，包括SSH连接到主机、执行批量自定义命令、设置定时任务等。

### 主要功能

1. 通过 Telegram 机器人接口远程控制主机
2. 支持 SSH 连接到多个主机
3. 执行自定义命令或预设的脚本
4. 设置定时执行脚本任务
5. 支持密钥登录
6. 支持批量上传公钥
7. 支持定时任务管理（新增）
8. 支持主机分组（新增）
9. 支持时间模式切换（小时/分钟）（新增）

## Telegram 交流群

欢迎加入我们的 Telegram 交流群，在这里您可以与其他用户讨论使用心得，获取帮助，以及了解最新的项目动态：

[加入SSHTGBot交流群](https://t.me/+WIX6H-944HQzZmQ9)

## 部署方法

### 准备工作

1. 一个 Telegram 机器人 Token。在 Telegram 中搜索BotFather，创建新 Bot，并获取 API Token。
2. 您的 Telegram 用户 ID。获取方式：向 Bot 发送一条消息，访问`https://api.telegram.org/bot<Your_API Token>/getUpdates`获取 Chat ID。
3. 一个 Render 账户（用于部署）
4. 您的主机账户信息（包括ssh用户名和密码、ssh地址）

### 部署步骤

1. Fork 本项目到您的 GitHub 账户。

2. 在 Render 中创建一个新的 Web Service，并连接到您 fork 的 GitHub 仓库。

3. 在 Render 的环境变量中设置以下变量：
   - `TELEGRAM_BOT_TOKEN`: 必填，您的 Telegram 机器人 Token
   - `TELEGRAM_CHAT_ID`: 必填，您的 Telegram 用户 ID 
   - `ACCOUNTS_JSON`:可选，建议设置， 包含主机账户信息的 JSON 字符串，格式如下：
     ```json
     [
       {
         "customhostname": "customhostname1",(自定义主机名称,建议设置)
         "ssluser": "your_ssluser1",（ssh用户名）
         "password": "your_password1",（ssh密码）
         "sslhost": "your_sslhost1",（ssh地址，格式示例："s5.serv00.com"）
         "secretkey": "私钥路径1包括私钥文件",（选填，用于上传私钥至render，在render环境变量下Secret Files中设置。格式示例：/etc/secrets/<filename>，设置私钥及上传公钥后为保证使用安全建议删除ssh登录密码和公钥）
         "publickey": "公钥路径1包括公钥文件，文件后缀.pub"（选填，注意最后一行此处无逗号。用于上传公钥至ssh主机，在render环境变量下Secret Files中设置。格式示例：/etc/secrets/<filename>）
       },
       {
         "customhostname": "customhostname2",
         "ssluser": "your_ssluser2",
         "password": "your_password2",
         "sslhost": "your_sslhost2",
         "secretkey": "私钥路径2",
         "publickey": "公钥路径2"
       },     
       ...
     ]
     ```
   - `RENDER_APP_URL`: 必填，您的 Render 应用 URL（格式：https://*******.onrender.com，项目左上角，地址最后不要有/）
   - `LAUNUAGE`: 可选，zh/en,默认语言为中文
   - `AUTO_CONNECT_INTERVAL`: 可选，定时任务的周期时间，选填，整数默认24，部署后可在telegram中输入/set_cron 0关闭定时任务。
   - `CUSTOM_COMMAND`: 可选，初始自定义执行命令（设置后，Render重新部署后不会清空自定义命令）
   - `TIME_MODE`:可选， 时间单位模式(hour/minute)周期单位设置为小时还是分钟，分钟可更精确控制，默认为小时模式。
   - `CRON_TASKS_JSON`:可选， 定时任务和主机分组配置（新增），格式如下：
     ```json
     {
         "tasks": [
             {
                 "id": "1",（任务编号）
                 "command": "uptime",（自定义命令）
                 "interval": 1,（周期时间，小时模式为小时，分钟模式为分钟）
                 "variation": 10,（偏差时间，小时模式为分钟，分钟模式为秒）
                 "target": "all"
             },
             {
                 "id": "2",
                 "command": "df -h",
                 "interval": 1,
                 "variation": 5,
                 "target": "+3"（ACCOUNTS_JSON前三个主机,-3则表示后3个主机）
             },
             {
                 "id": "3",
                 "command": "custom_command",
                 "interval": 1,
                 "variation": 2,
                 "target": "flypig,maxjiu,group:group2"（主机组前需要加group:）
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

4. 在 Render 中docker启动。

备注：Render可以部署一个免费项目，长时间不访问会可能有50s迟缓，可以手机下载UptimeRobot免费保持活跃。

## 使用说明

### 基本命令

- `/language` - 切换语言 (Switch language)
- `/start` - 再次发送此帮助消息（输入非命令字符也可推送帮助）
- `/grouprundeault` - 触发批量主机执行命令
- `/setcron <小时数>` - 设置、查看执行命令的周期（例如：/setcron 24）
- `/setvartime <分钟数>` - 设置、查看执行命令周期的随机变化范围（例如：/setvartime 10）
- `/ssh` - 列出所有可用的主机
- `/ssh <customhostname 或 ssluser@sslhost>` - 连接到指定的主机
- `/exit` - 退出当前 SSH 会话
- `/setcommand <command>` - 设置要执行的自定义命令（例如：/setcommand source ~/.profile && pm2 resurrect）
- `/uploadkeys` - 批量上传公钥到远程主机（设置私钥及上传公钥后为保证使用安全建议删除ssh登录密码和公钥）

### 新增命令（定时任务管理）

- ` /grouprun <命令> [目标]` - 执行自定义命令到指定主机
  - 例如：/addtask pwd all
  - 参数说明：
    - `目标`: 目标主机（可选，默认为 "all"，具体使用见主机分组和目标选择）
- `/addtask <命令> <周期> <偏差> [目标]` - 添加新的定时任务
  - 例如：/addtask uptime 2 10 all
  - 参数说明：
    - `周期`: 执行间隔（小时或分钟，取决于当前模式）
    - `偏差`: 随机变化范围（分钟或秒，取决于当前模式）
    - `目标`: 目标主机（可选，默认为 "all"，具体使用见主机分组和目标选择）
- `/listtasks` - 列出所有定时任务
- `/removetask <task_id>` - 删除指定的定时任务
- `/pausetask <task_id>` - 暂停指定的定时任务
- `/resumetask <task_id>` - 恢复指定的定时任务
- `/switchmode` - 切换时间单位模式（小时/分钟），为保证兼容性，默认为小时模式。

### 主机分组和目标选择

在添加任务或执行命令时，可以使用以下方式指定目标主机：

- `all`: 所有主机
- `+N`: 选择ACCOUNTS_JSON前 N 个主机（例如：`+3`）
- `-N`: 选择ACCOUNTS_JSON后 N 个主机（例如：`-2`）
- `customhostname1,customhostname2,...`: 指定多个主机
- `group:group_name`: 使用预定义的主机组（在 CRON_TASKS_JSON 中配置group_name）

### 注意事项

- SSH 会话有15分钟的超时时间，超时后会自动断开连接。
- 所有的操作和执行结果都会通过 Telegram 机器人实时反馈。
- 请确保您的自定义命令是安全的，不会对主机造成损害。
- 定时任务的执行时间可能会有轻微偏差，这是为了避免所有任务同时执行而设计的。

## 故障排除

如果遇到问题，请检查以下几点：

1. 确保所有环境变量都已正确设置。
2. 检查 Render 日志以获取更详细的错误信息。
3. 确保您的 Telegram 机器人 Token 是有效的，且机器人已被添加到指定的聊天中。
4. 验证主机的登录信息是否正确，包括主机名、用户名和密码。
5. 检查ACCOUNTS_JSON、CRON_TASKS_JSON 的格式是否正确，确保所有必需字段都已填写。

如果问题仍然存在，请提交一个 issue 到项目的 GitHub 仓库。

## 免责声明

本项目仅用于教育和研究目的。使用本工具进行任何操作都应遵守相关法律法规和服务条款。用户应对使用本工具的所有后果负全部责任。

开发者不对因使用本工具而导致的任何直接或间接损失负责，包括但不限于数据丢失、系统崩溃、安全漏洞等问题。使用本工具即表示您同意承担所有相关风险。

请谨慎使用本工具，并确保您有权限对目标主机进行操作。不要将本工具用于非法用途或未经授权的系统。
