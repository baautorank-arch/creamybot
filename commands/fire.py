# fire.py
import asyncio
import json
import discord
from discord import app_commands
from discord.ext import commands
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

with open("config.json") as f:
    config = json.load(f)

GOOGLE_SHEET_NAME = config["GOOGLE_SHEET_NAME"]
GOOGLE_CREDENTIALS_FILE = config["GOOGLE_CREDENTIALS_FILE"]
STAFF_WORKSHEET_NAME = config["WORKSHEET_NAME"]
EMPLOYMENT_WORKSHEET_NAME = config.get("EMPLOYMENT_WORKSHEET_NAME", "Employment Records")
MANAGEMENT_ROLE_ID = int(config["MANAGEMENT_ROLE_ID"])
EMP_FIRST_DATA_ROW = int(config.get("EMP_FIRST_DATA_ROW", 4))

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
CREDS = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
CLIENT = gspread.authorize(CREDS)
SPREAD = CLIENT.open(GOOGLE_SHEET_NAME)
STAFF_SHEET = SPREAD.worksheet(STAFF_WORKSHEET_NAME)
EMP_SHEET = SPREAD.worksheet(EMPLOYMENT_WORKSHEET_NAME)


async def _retry_429(fn, *args, **kwargs):
    for delay in (0.0, 1.0, 2.5, 5.0):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            if "429" in str(e):
                await asyncio.sleep(delay if delay else 0.5)
                continue
            raise


def _fmt_api_error(e: APIError) -> str:
    try:
        status = getattr(getattr(e, "response", None), "status_code", "")
        text = getattr(getattr(e, "response", None), "text", "")
        if status or text:
            return f"{e} (status={status}) {text}"
    except Exception:
        pass
    return str(e)


async def _next_emp_row_below_last() -> int:
    col_d = await _retry_429(EMP_SHEET.get, f"D{EMP_FIRST_DATA_ROW}:D")
    last_idx = 0
    for i, row in enumerate(col_d, start=1):
        if (row[0] if row else "").strip():
            last_idx = i
    dest_row = EMP_FIRST_DATA_ROW + last_idx
    if dest_row > EMP_SHEET.row_count:
        await _retry_429(EMP_SHEET.add_rows, dest_row - EMP_SHEET.row_count)
    return dest_row


class Fire(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="fire",
        description="Fire a user: log to Employment Records and remove from Staff Database.",
    )
    @app_commands.describe(
        username="Username (column D in Staff Database)",
        reason="Reason for termination",
        approved_by="Who approved it",
    )
    @app_commands.choices(
        termination_type=[
            app_commands.Choice(name="Honourable", value="Honourable"),
            app_commands.Choice(name="Dishonourable", value="Dishonourable"),
            app_commands.Choice(name="Blacklist", value="Blacklist"),
            app_commands.Choice(name="N/A", value="N/A"),
        ]
    )
    async def fire(
        self,
        interaction: discord.Interaction,
        username: str,
        reason: str,
        termination_type: app_commands.Choice[str],
        approved_by: str,
    ):
        if not isinstance(interaction.user, discord.Member) or not any(
            r.id == MANAGEMENT_ROLE_ID for r in interaction.user.roles
        ):
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            d_col = await _retry_429(STAFF_SHEET.get, "D4:D")
            target = username.strip().lower()
            row_index = None
            for idx, row in enumerate(d_col, start=4):
                cell = (row[0] if row else "").strip()
                if cell and cell.lower() == target:
                    row_index = idx
                    break
            if row_index is None:
                await interaction.followup.send(
                    f"❌ Username **{username}** not found in Staff Database (column D)."
                )
                return

            row_vals = await _retry_429(STAFF_SHEET.get, f"C{row_index}:D{row_index}")
            rank = (row_vals[0][0] if row_vals and row_vals[0] else "") or ""
            uname = (row_vals[0][1] if row_vals and len(row_vals[0]) > 1 else "") or ""

            dest_row = await _next_emp_row_below_last()
            await _retry_429(
                EMP_SHEET.update,
                f"C{dest_row}:G{dest_row}",
                [[rank, uname, reason, termination_type.value, approved_by]],
                value_input_option="USER_ENTERED",
            )

            await _retry_429(STAFF_SHEET.delete_rows, row_index)

            await interaction.followup.send(
                f"✅ Fired **{uname}** ({rank}). Logged to Employment Records row {dest_row} and removed from Staff Database."
            )

        except APIError as e:
            await interaction.followup.send(f"❌ Google Sheets error: {_fmt_api_error(e)}")
        except Exception as e:
            await interaction.followup.send(f"❌ Unexpected error: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fire(bot))
