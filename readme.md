# VPS-Set-For-Telegram

## 项目简介

VPS-Set-For-Telegram 是一个基于 Telegram 的自动化工具，主要用于远程管理和重置多个 VPS（如sevr00）。该项目允许用户通过 Telegram 机器人界面执行各种操作，包括SSH连接到VPS、执行自定义命令、设置定时任务等。

### 主要功能

1. 通过 Telegram 机器人接口远程控制 VPS
2. 支持 SSH 连接到多个 VPS
3. 执行自定义命令或预设的重置脚本
4. 设置自动重置计划

## Telegram 交流群

欢迎加入我们的 Telegram 交流群，在这里您可以与其他用户讨论使用心得，获取帮助，以及了解最新的项目动态：

[加入 VPS-Set-For-Bot 交流群](https://t.me/+WIX6H-944HQzZmQ9)

## 部署方法

### 准备工作

1. 一个 Telegram 机器人 Token（可以通过 BotFather 创建）
2. 您的 Telegram 用户 ID 
3. 一个 Render 账户（用于部署）
4. 您的 VPS 账户信息（包括ssh用户名和密码、ssh地址）

### 部署步骤

1. Fork 本项目到您的 GitHub 账户。

2. 在 Render 中创建一个新的 Web Service，并连接到您 fork 的 GitHub 仓库。

3. 在 Render 的环境变量中设置以下变量：
   - `TELEGRAM_BOT_TOKEN`: 您的 Telegram 机器人 Token
   - `TELEGRAM_CHAT_ID`: 您的 Telegram 用户 ID 
   - `ACCOUNTS_JSON`: 包含 VPS 账户信息的 JSON 字符串，格式如下：
     ```json
     [
       {
         "username": "your_username1",（ssh用户名）
         "password": "your_password1",（ssh密码）
         "hostname": "your_hostname1",（ssh地址，格式示例："s5.serv00.com"）
         "path": "optional_path1"(注意最后一行此处无逗号，path这一行选填，若不设置且setpathcom已设置，会跳过path执行setcommand默认命令.
                                   格式示例："~/domains/ssgj.dns-dynamic.net/vless")
       },
       {
         "username": "your_username2",
         "password": "your_password2",
         "hostname": "your_hostname2",
         "path": "optional_path2"
       },     
       ...
     ]
     ```
   - `AUTO_CONNECT_INTERVAL`: 自动重置的时间间隔（小时），整数必填不小于1，不填写或输入0会影响通过/set_cron定时自动重置生效，部署后可在telegram中输入/set_cron 0关闭定时重置。
   - `RENDER_APP_URL`: 您的 Render 应用 URL（格式：https://*******.onrender.com,项目左上角，地址最后不要有/）
   - `CUSTOM_COMMAND`: 初始自定义执行命令（设置后，Render重新部署后不会清空自定义命令）

4. 在 Render 中docker启动。

备注：Render可以部署一个免费项目，长时间不访问会可能有50s迟缓，可以手机下载UptimeRobot免费保持活跃。

## 使用说明

### 基本命令

- `/reset`: 触发 VPS 重置脚本
- `/setcron <小时数>`: 设置自动重置的时间间隔
- `/getcron`: 获取当前自动重置的时间间隔和下次重置时间
- `/setvartime <分钟数>`: 设置重置时间的随机变化范围，默认10分钟
- `/ssh`: 列出所有可用的 VPS 用户名
- `/ssh <username>`: 连接到指定的 VPS
- `/exit`: 退出当前 SSH 会话
- `/setcommand <command>`: 设置要执行的自定义命令，默认：source ~/.profile && pm2 resurrect
- `/setpathcom [command]`: 设置、查看或清除要在指定路径下执行的自定义命令

### 注意事项

- SSH 会话有15分钟的超时时间，超时后会自动断开连接。
- 所有的操作和执行结果都会通过 Telegram 机器人实时反馈。
- 请确保您的自定义命令是安全的，不会对 VPS 造成损害。

## 故障排除

如果遇到问题，请检查以下几点：

1. 确保所有环境变量都已正确设置。
2. 检查 Render 日志以获取更详细的错误信息。
3. 确保您的 Telegram 机器人 Token 是有效的，且机器人已被添加到指定的聊天中。
4. 验证 VPS 的登录信息是否正确，包括主机名、用户名和密码。

如果问题仍然存在，请提交一个 issue 到项目的 GitHub 仓库。

## 免责声明

本项目 VPS Reset Bot 仅用于教育和研究目的。使用本工具进行任何操作都应遵守相关法律法规和服务条款。用户应对使用本工具的所有后果负全部责任。

开发者不对因使用本工具而导致的任何直接或间接损失负责，包括但不限于数据丢失、系统崩溃、安全漏洞等问题。使用本工具即表示您同意承担所有相关风险。

请谨慎使用本工具，并确保您有权限对目标 VPS 进行操作。不要将本工具用于非法用途或未经授权的系统。


