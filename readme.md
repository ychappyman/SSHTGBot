# Serv00 Login Bot

   This project automates the login process for serv00 accounts and executes a specified SSH command. It uses a Telegram bot for notifications and can be triggered periodically or manually.

   ## Setup

   1. Clone this repository
   2. Install dependencies: `pip install -r requirements.txt`
   3. Set up environment variables:
      - `TELEGRAM_BOT_TOKEN`
      - `TELEGRAM_CHAT_ID`
      - `CRON_SECRET`
   4. Create an `accounts.json` file with your serv00 account details
   5. Deploy to a platform like Render

   ## Usage

   - Use `/start` to get started with the Telegram bot
   - Use `/restart` to manually trigger the login script
   - Set up a cron job to periodically trigger the login script

   ## Development

   To contribute to this project:

   1. Fork the repository
   2. Create a new branch for your feature
   3. Commit your changes
   4. Push to your fork
   5. Create a pull request

   ## License

   This project is licensed under the MIT License.
   