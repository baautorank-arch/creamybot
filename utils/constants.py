import json

with open("config.json") as f:
    config = json.load(f)

TOKEN = config["TOKEN"]
GUILD_ID = int(config["GUILD_ID"])
MANAGEMENT_ROLE_ID = int(config["MANAGEMENT_ROLE_ID"])
