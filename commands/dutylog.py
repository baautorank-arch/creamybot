import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread.exceptions import APIError

with open("config.json") as f:
    config = json.load(f)

GUILD_ID = int(config["GUILD_ID"])
GOOGLE_SHEET_NAME = config["GOOGLE_SHEET_NAME"]
GOOGLE_CREDENTIALS_FILE = config["GOOGLE_CREDENTIALS_FILE"]
SHIFT_CHANNEL_ID = int(config["SHIFT_CHANNEL_ID"])
MANAGEMENT_ROLE_ID = int(config["MANAGEMENT_ROLE_ID"])

def get_gsheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open(GOOGLE_SHEET_NAME).sheet1

def discord_ts(dt: datetime, style: str = "t") -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"

def human_minutes(total_minutes: int) -> str:
    h, m = divmod(max(0, int(total_minutes)), 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"

class DutyLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_shifts: dict[int, dict] = {}
        self.finished_shifts: dict[int, dict] = {}
        self._lock = asyncio.Lock()

    def _make_running_embed(self, member: discord.Member, start_time: datetime) -> discord.Embed:
        embed = discord.Embed(title="📋 Duty Log", color=discord.Color.blurple())
        embed.add_field(name="User", value=member.mention, inline=False)
        embed.add_field(name="Started", value=discord_ts(start_time, "t"), inline=False)
        embed.add_field(name="Status", value="On duty", inline=False)
        return embed

    def _make_summary_embed(self, member: discord.Member | None, start_time: datetime, end_time: datetime, minutes: int, status: str = "Awaiting approval") -> discord.Embed:
        color = discord.Color.green() if status == "Approved" else (discord.Color.red() if status == "Denied" else discord.Color.blurple())
        embed = discord.Embed(title="📋 Shift Summary", color=color)
        embed.add_field(name="User", value=(member.mention if isinstance(member, discord.Member) else "Unknown"), inline=False)
        embed.add_field(name="Started", value=discord_ts(start_time, "t"), inline=False)
        embed.add_field(name="Ended", value=discord_ts(end_time, "t"), inline=False)
        embed.add_field(name="Total Time", value=human_minutes(minutes), inline=False)
        embed.add_field(name="Status", value=status, inline=False)
        return embed

    class RunningShiftView(discord.ui.View):
        def __init__(self, cog: "DutyLog", user_id: int):
            super().__init__(timeout=None)
            self.cog = cog
            self.user_id = user_id

        @discord.ui.button(label="End", style=discord.ButtonStyle.success, custom_id="shift_end")
        async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Only the shift owner can end this shift.")
                return
            await self.cog._end_shift(interaction, canceled=False)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="shift_cancel")
        async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Only the shift owner can cancel this shift.")
                return
            await self.cog._end_shift(interaction, canceled=True)

    class CompletedShiftView(discord.ui.View):
        def __init__(self, cog: "DutyLog", user_id: int):
            super().__init__(timeout=None)
            self.cog = cog
            self.user_id = user_id
            self._locked = False

        async def _check_management(self, interaction: discord.Interaction) -> bool:
            if not isinstance(interaction.user, discord.Member):
                await interaction.response.send_message("Cannot verify your roles here.")
                return False
            if not any(r.id == MANAGEMENT_ROLE_ID for r in interaction.user.roles):
                await interaction.response.send_message("You do not have permission to approve or deny shifts.")
                return False
            return True

        @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="shift_approve")
        async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self._check_management(interaction):
                return
            if self._locked:
                try:
                    await interaction.response.defer()
                except:
                    pass
                return
            self._locked = True
            try:
                await interaction.response.defer()
            except:
                pass
            ok = await self.cog._approve_shift(interaction, self.user_id, approved=True)
            if not ok:
                self._locked = False

        @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="shift_deny")
        async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not await self._check_management(interaction):
                return
            if self._locked:
                try:
                    await interaction.response.defer()
                except:
                    pass
                return
            self._locked = True
            try:
                await interaction.response.defer()
            except:
                pass
            ok = await self.cog._approve_shift(interaction, self.user_id, approved=False)
            if not ok:
                self._locked = False

    @app_commands.command(name="shift", description="Start a new shift (no proof required).")
    async def shift(self, interaction: discord.Interaction):
        if interaction.channel.id != SHIFT_CHANNEL_ID:
            await interaction.response.send_message(f"This command can only be used in <#{SHIFT_CHANNEL_ID}>.")
            return
        member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
        if member is None:
            await interaction.response.send_message("Couldn't resolve your member record. Try again.")
            return
        if interaction.user.id in self.active_shifts:
            await interaction.response.send_message("You already have an active shift. Use the End button on your shift message.")
            return
        start_time = datetime.now(timezone.utc)
        embed = self._make_running_embed(member, start_time)
        view = DutyLog.RunningShiftView(self, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        self.active_shifts[interaction.user.id] = {"message_id": msg.id, "channel_id": msg.channel.id, "start_time": start_time}

    async def _end_shift(self, interaction: discord.Interaction, canceled: bool):
        data = self.active_shifts.get(interaction.user.id)
        if not data:
            await interaction.response.send_message("You don't have an active shift.")
            return
        try:
            await interaction.response.defer()
        except:
            pass
        async with self._lock:
            start_time: datetime = data["start_time"]
            end_time = datetime.now(timezone.utc)
            minutes = int((end_time - start_time).total_seconds() // 60)
            channel = interaction.client.get_channel(data["channel_id"]) or await interaction.client.fetch_channel(data["channel_id"])
            try:
                msg: discord.Message = await channel.fetch_message(data["message_id"])
            except:
                msg = None
            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            display_name = member.display_name if isinstance(member, discord.Member) else str(interaction.user.id)
            if canceled:
                if msg:
                    try:
                        await msg.delete()
                    except:
                        pass
                self.active_shifts.pop(interaction.user.id, None)
                return
            summary_embed = self._make_summary_embed(member, start_time, end_time, minutes, status="Awaiting approval")
            view = DutyLog.CompletedShiftView(self, interaction.user.id)
            try:
                if msg:
                    await msg.edit(embed=summary_embed, view=view)
                else:
                    await interaction.channel.send(embed=summary_embed, view=view)
            except:
                pass
            self.finished_shifts[interaction.user.id] = {
                "start_time": start_time,
                "end_time": end_time,
                "duration": minutes,
                "message_id": data["message_id"],
                "channel_id": data["channel_id"],
                "display_name": display_name
            }
            self.active_shifts.pop(interaction.user.id, None)

    async def _approve_shift(self, interaction: discord.Interaction, user_id: int, approved: bool):
        data = self.finished_shifts.get(user_id)
        if not data:
            return False
        channel = interaction.client.get_channel(data["channel_id"]) or await interaction.client.fetch_channel(data["channel_id"])
        try:
            msg: discord.Message = await channel.fetch_message(data["message_id"])
        except:
            msg = None
        guild = interaction.guild
        member = guild.get_member(user_id) if guild else None
        start_time: datetime = data["start_time"]
        end_time: datetime = data["end_time"]
        minutes: int = data["duration"]
        if not approved:
            if msg:
                try:
                    await msg.delete()
                except:
                    pass
            self.finished_shifts.pop(user_id, None)
            return True
        display_name = data.get("display_name") or (member.display_name if isinstance(member, discord.Member) else str(user_id))
        try:
            sheet = get_gsheet()
            usernames = sheet.col_values(4)
            row_index = None
            dn_l = display_name.strip().lower()
            for i, name in enumerate(usernames, start=1):
                if name and name.strip().lower() == dn_l:
                    row_index = i
                    break
            if row_index is None:
                raise RuntimeError(f"No row found in column D for display name '{display_name}'.")
            current_value = sheet.cell(row_index, 7).value
            try:
                current_minutes = int(str(current_value).strip()) if current_value is not None and str(current_value).strip().isdigit() else 0
            except:
                current_minutes = 0
            sheet.update_cell(row_index, 7, current_minutes + minutes)
        except (APIError, Exception) as e:
            if msg:
                try:
                    await interaction.channel.send(f"Failed to log shift: {e}")
                except:
                    pass
            return False
        if msg:
            try:
                await msg.delete()
            except:
                pass
        self.finished_shifts.pop(user_id, None)
        return True

async def setup(bot):
    await bot.add_cog(DutyLog(bot))
