import discord
from discord import app_commands
from discord.ext import commands
import json
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError

with open("config.json") as f:
    config = json.load(f)

GOOGLE_SHEET_NAME = config["GOOGLE_SHEET_NAME"]
GOOGLE_CREDENTIALS_FILE = config["GOOGLE_CREDENTIALS_FILE"]
WORKSHEET_NAME = config["WORKSHEET_NAME"]
MANAGEMENT_ROLE_ID = int(config["MANAGEMENT_ROLE_ID"])

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
CREDS = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
CLIENT = gspread.authorize(CREDS)
SHEET = CLIENT.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)

class Warn(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def next_warning(self, current: str) -> str:
        if not current or current.strip().lower() == "none":
            return "Written Warning x1"
        c = current.strip().lower()
        if "written warning x1" in c:
            return "Written Warning x2"
        if "written warning x2" in c:
            return "Written Warning x3"
        if "written warning x3" in c:
            return "Suspension"
        if "suspension" in c:
            return "Suspension"
        return "Written Warning x1"

    @app_commands.command(name="warn", description="Warn a staff member and update the database.")
    @app_commands.describe(user="Member to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        if not isinstance(interaction.user, discord.Member) or not any(r.id == MANAGEMENT_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("You do not have permission to use this command.")
            return

        await interaction.response.defer()

        dm_ok = True
        try:
            await user.send(f"You have received a warning in Creamy Dreams.\n\nReason: {reason}. \n\nIf you wish to appeal this action, please open up a support ticket in our communications server.")
        except:
            dm_ok = False

        try:
            names = SHEET.col_values(4)
            target = user.display_name.strip().lower()
            row_index = None
            for i, name in enumerate(names, start=1):
                if name and name.strip().lower() == target:
                    row_index = i
                    break

            if row_index is None:
                await interaction.followup.send(f"❌ User **{user.display_name}** was not found in column D.")
                return

            current = SHEET.cell(row_index, 8).value
            new_value = self.next_warning(current or "")
            SHEET.update_cell(row_index, 8, new_value)

            tail = "" if dm_ok else " (DM failed)"
            await interaction.followup.send(f"{user.mention} warned → **{new_value}**. \n\nReason: {reason}{tail}")
        except APIError as e:
            await interaction.followup.send(f"Google Sheets error: {e}")
        except Exception as e:
            await interaction.followup.send(f"Unexpected error: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Warn(bot))
