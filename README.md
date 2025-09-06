# Creamy Dreams Discord Bot

A Discord bot designed to manage shifts abd run automation tasks on the database.

Created by SimplyBeario  
Discord: b3ari0

---

## Features

- Slash command `/addtodb` for management to add users to the database
- Slash command `/warn` for management to warn an employee and have it add to the db
- Slash command `/fire` for management to remove users from the database and log the employment
- Slash command `/shift` for employees to log their shifts, and have it add to the db automatically
- Google Sheets integration to track employee data (activity, rank, etc.)

---

## Setup Instructions

1. **Install requirements**

Make sure you have Python 3.10+ installed. Then install dependencies with:

pip install -r requirements.txt

2. **Edit `config.json`**

This file holds all the bot's configuration details. See the section below for explanations of each key.


3. **Run the bot**

Start the bot using:

python main.py

---


## config.json Explained

Here’s what each key in the `config.json` file is used for:

`TOKEN` – Your Discord bot token, create one using the discord developer portal

`GUILD_ID` – The ID of your Discord server

`MANAGEMENT_ROLE_ID` – Role required to review applications and use /employee

`SHIFT_CHANNEL_ID` - Channel where shifts are logged

`GOOGLE_SHEET_NAME` – The name of your Google Sheet file (keep the same)

`GOOGLE_CREDENTIALS_FILE` – Name of the service account JSON file (keep the same)

`WORKSHEET_NAME` - Name of the first google sheet (keep the same)

`EMPLOYMENT_WORKSHEET_NAME` - Name of the second google sheet (keep the same)
