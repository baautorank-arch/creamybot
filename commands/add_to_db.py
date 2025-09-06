import discord
from discord import app_commands
from discord.ext import commands
import gspread
import json
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from datetime import datetime

with open("config.json") as f:
    config = json.load(f)

GOOGLE_SHEET_NAME = config["GOOGLE_SHEET_NAME"]
GOOGLE_CREDENTIALS_FILE = config["GOOGLE_CREDENTIALS_FILE"]
WORKSHEET_NAME = config["WORKSHEET_NAME"]
MANAGEMENT_ROLE_ID = int(config["MANAGEMENT_ROLE_ID"])

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDS = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
CLIENT = gspread.authorize(CREDS)
SHEET = CLIENT.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)

service = build("sheets", "v4", credentials=CREDS)
spreadsheet_id = CLIENT.open(GOOGLE_SHEET_NAME).id
sheet_id = SHEET.id

def management_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.CheckFailure("This command can only be used in a server.")
        if not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("This command can only be used by server members.")
        if any(r.id == MANAGEMENT_ROLE_ID for r in interaction.user.roles):
            return True
        raise app_commands.CheckFailure("You must have a management role to use this command.")
    return app_commands.check(predicate)

def insert_formatted_row(after_row: int):
    requests = [
        {
            "insertDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": after_row,
                    "endIndex": after_row + 1,
                },
                "inheritFromBefore": True,
            }
        }
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()

def copy_borders(from_row: int, to_row: int):
    requests = [
        {
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": to_row - 1,
                    "endRowIndex": to_row,
                    "startColumnIndex": 2,
                    "endColumnIndex": 8,
                },
                "top": {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}},
                "bottom": {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}},
                "left": {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}},
                "right": {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}},
                "innerHorizontal": {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}},
                "innerVertical": {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}},
            }
        }
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()

class AddToDB(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="addtodb", description="Add a new staff member to the database as Baker.")
    @app_commands.guild_only()
    @management_only()
    async def addtodb(self, interaction: discord.Interaction, roblox_username: str, wb_plate: str):
        await interaction.response.defer(ephemeral=True)
        try:
            values = SHEET.get_all_values()
            COL_RANK = 3
            COL_USERNAME = 4
            COL_WBPLATE = 5
            COL_HIREDATE = 6
            COL_MINUTES = 7
            COL_DISCIPLINARY = 8
            baker_rows = []
            for i, row in enumerate(values):
                if len(row) >= COL_RANK and row[COL_RANK - 1].strip().lower() == "baker":
                    baker_rows.append(i + 1)
            today_date = datetime.now().strftime("%m/%d/%Y")
            if not baker_rows:
                new_row = ["", "", "Baker", roblox_username, wb_plate, today_date, 0, "None"]
                SHEET.append_row(new_row, value_input_option="USER_ENTERED")
                await interaction.followup.send(
                    f"✅ Added **{roblox_username}** with plate `{wb_plate}` as a new Baker (new row created).",
                    ephemeral=True
                )
                return
            placed = False
            for row_idx in baker_rows:
                username_cell = SHEET.cell(row_idx, COL_USERNAME).value
                if not username_cell:
                    SHEET.update_cell(row_idx, COL_USERNAME, roblox_username)
                    SHEET.update_cell(row_idx, COL_WBPLATE, wb_plate)
                    SHEET.update_cell(row_idx, COL_HIREDATE, today_date)
                    SHEET.update_cell(row_idx, COL_MINUTES, 0)
                    SHEET.update_cell(row_idx, COL_DISCIPLINARY, "None")
                    placed = True
                    break
            if not placed:
                last_baker_row = baker_rows[-1]
                insert_formatted_row(last_baker_row)
                new_row_index = last_baker_row + 1
                copy_borders(last_baker_row, new_row_index)
                SHEET.update_cell(new_row_index, COL_RANK, "Baker")
                SHEET.update_cell(new_row_index, COL_USERNAME, roblox_username)
                SHEET.update_cell(new_row_index, COL_WBPLATE, wb_plate)
                SHEET.update_cell(new_row_index, COL_HIREDATE, today_date)
                SHEET.update_cell(new_row_index, COL_MINUTES, 0)
                SHEET.update_cell(new_row_index, COL_DISCIPLINARY, "None")
            await interaction.followup.send(
                f"✅ Successfully added **{roblox_username}** with plate `{wb_plate}` as a Baker.",
                ephemeral=True
            )
        except APIError as e:
            await interaction.followup.send(f"❌ Google Sheets error: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Unexpected error: {e}", ephemeral=True)

    @addtodb.error
    async def addtodb_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            if interaction.response.is_done():
                await interaction.followup.send(f"🚫 {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"🚫 {error}", ephemeral=True)
        else:
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(AddToDB(bot))
