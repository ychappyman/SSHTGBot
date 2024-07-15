[English Version](/README.md)

# SSHTGBot

## 项目简介

SSHTGBot 是一个基于 Telegram 的自动化工具，主要用于远程管理和定时、手动执行命令到多个主机（如sevr00）。该项目允许用户通过 Telegram 机器人界面执行各种操作，包括SSH连接到主机、执行批量自定义命令、设置定时任务等。

### 主要功能

1. 通过 Telegram 机器人接口远程控制主机
2. 支持 SSH 连接到多个主机
3. 执行自定义命令或预设的脚本
4. 设置定时执行脚本任务
5. 支持密钥登录
6. 支持批量上传公钥

## Telegram 交流群

欢迎加入我们的 Telegram 交流群，在这里您可以与其他用户讨论使用心得，获取帮助，以及了解最新的项目动态：

[加入SSHTGBot交流群](https://t.me/+WIX6H-944HQzZmQ9)

## 部署方法

### 准备工作

1. 一个 Telegram 机器人 Token。在 Telegram 中搜索 @BotFather，创建新 Bot，并获取 API Token。
2. 您的 Telegram 用户 ID。获取方式：向 Bot 发送一条消息，访问 https://api.telegram.org/bot<your bot token>/getupdates 获取 Chat ID。
3. 一个 Render 账户（用于部署）
4. 您的主机账户信息（包括ssh用户名和密码、ssh地址）

### 部署步骤

1. Fork 本项目到您的 GitHub 账户。

2. 在 Render 中创建一个新的 Web Service，并连接到您 fork 的 GitHub 仓库。

3. 在 Render 的环境变量中设置以下变量：
   - `LAUNUAGE`: 默认语言为中文
   - `TELEGRAM_BOT_TOKEN`: 您的 Telegram 机器人 Token
   - `TELEGRAM_CHAT_ID`: 您的 Telegram 用户 ID 
   - `ACCOUNTS_JSON`: 包含主机账户信息的 JSON 字符串，格式如下：
     ```json
     [
       {
         "customhostname": "customhostname1",
         "ssluser": "your_ssluser1",
         "password": "your_password1",
         "sslhost": "your_sslhost1",
         "secretkey": "render Secret Files secretkey 路径1",
         "publickey": "render Secret Files publickey 路径1文件后缀.pub",
         "path": "optional_path1"
       },
       {
         "customhostname": "customhostname2",
         "ssluser": "your_ssluser2",
         "password": "your_password2",
         "sslhost": "your_sslhost2",
         "secretkey": "render Secret Files secretkey 路径2",
         "publickey": "render Secret Files publickey 路径2",
         "path": "optional_path2"
       },     
       ...
     ]
     ```
   - `AUTO_CONNECT_INTERVAL`: 自动重置的时间间隔（小时），选填，整数默认24，部署后可在telegram中输入/set_cron 0关闭定时重置。
   - `RENDER_APP_URL`: 您的 Render 应用 URL（格式：https://*******.onrender.com，项目左上角，地址最后不要有/）
   - `CUSTOM_COMMAND`: 初始自定义执行命令（设置后，Render重新部署后不会清空自定义命令）

4. 在 Render 中docker启动。

备注：Render可以部署一个免费项目，长时间不访问会可能有50s迟缓，可以手机下载UptimeRobot免费保持活跃。

## 使用说明

### 基本命令

- `/language` - 切换语言 (Switch language)
- `/start` - 再次发送此帮助消息（输入非命令字符也可推送帮助）
- `/grouprun` - 触发批量主机执行命令
- `/setcron <小时数>` - 设置、查看执行命令的周期（例如：/setcron 24）
- `/setvartime <分钟数>` - 设置、查看执行命令周期的随机变化范围（例如：/setvartime 10）
- `/ssh` - 列出所有可用的主机
- `/ssh <customhostname 或 ssluser@sslhost>` - 连接到指定的主机
- `/exit` - 退出当前 SSH 会话
- `/setcommand <command>` - 设置要执行的自定义命令（例如：/setcommand source ~/.profile && pm2 resurrect）
- `/setpathcom [command]` - 设置、查看或清除要在指定路径下执行的自定义命令
   - 设置: `/setpathcom pm2 resurrect`
   - 查看: `/setpathcom`
   - 清除: `/setpathcom clear`
- `/uploadkeys` - 批量上传公钥到远程主机（设置密钥及上传公钥后为保证使用安全建议删除ssh登录密码和公钥）

### 注意事项

- SSH 会话有15分钟的超时时间，超时后会自动断开连接。
- 所有的操作和执行结果都会通过 Telegram 机器人实时反馈。
- 请确保您的自定义命令是安全的，不会对主机造成损害。

## 故障排除

如果遇到问题，请检查以下几点：

1. 确保所有环境变量都已正确设置。
2. 检查 Render 日志以获取更详细的错误信息。
3. 确保您的 Telegram 机器人 Token 是有效的，且机器人已被添加到指定的聊天中。
4. 验证主机的登录信息是否正确，包括主机名、用户名和密码。

如果问题仍然存在，请提交一个 issue 到项目的 GitHub 仓库。

## 免责声明

本项目仅用于教育和研究目的。使用本工具进行任何操作都应遵守相关法律法规和服务条款。用户应对使用本工具的所有后果负全部责任。

开发者不对因使用本工具而导致的任何直接或间接损失负责，包括但不限于数据丢失、系统崩溃、安全漏洞等问题。使用本工具即表示您同意承担所有相关风险。

请谨慎使用本工具，并确保您有权限对目标主机进行操作。不要将本工具用于非法用途或未经授权的系统。
