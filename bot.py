import os
import discord
from discord import app_commands
from discord.ext import commands
import gspread
from google.oauth2.service_account import Credentials
import base64
import json

# 환경변수에서 Discord 토큰과 Google 인증 정보 불러오기
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_CREDS_BASE64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_BASE64")

# 구글 인증: base64 → json
json_str = base64.b64decode(GOOGLE_CREDS_BASE64).decode("utf-8")
creds_dict = json.loads(json_str)
creds = Credentials.from_service_account_info(creds_dict)
gc = gspread.authorize(creds)

# 스프레드시트 열기 (스프레드시트 제목 입력!)
SPREADSHEET_NAME = "전적"
spreadsheet = gc.open(SPREADSHEET_NAME)

# 디스코드 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 봇 로그인 완료: {bot.user.name}")

# 📌 /전적 [아이디]
@bot.tree.command(name="전적", description="특정 유저의 누적 전적을 조회합니다.")
@app_commands.describe(아이디="조회할 유저 아이디")
async def 전적(interaction: discord.Interaction, 아이디: str):
    await interaction.response.defer()

    try:
        stats = {"승": 0, "패": 0, "마지막날짜": ""}
        for ws in spreadsheet.worksheets():
            rows = ws.get_all_values()[1:]  # 헤더 제외
            for row in rows:
                if len(row) < 2:
                    continue
                name, result = row[0].strip(), row[1].strip()
                if name.lower() == 아이디.lower():
                    if result == "승":
                        stats["승"] += 1
                    elif result == "패":
                        stats["패"] += 1
                    stats["마지막날짜"] = ws.title

        총전 = stats["승"] + stats["패"]
        if 총전 == 0:
            await interaction.followup.send(f"📭 `{아이디}`님의 전적 기록이 없습니다.")
            return

        승률 = (stats["승"] / 총전) * 100
        table = (
            "```\n"
            "승   패   전   승률   마지막기록\n"
            f"{stats['승']:<4} {stats['패']:<4} {총전:<4} {승률:>5.1f}%   {stats['마지막날짜']}\n"
            "```"
        )

        embed = discord.Embed(title=f"📄 {아이디}님의 전적 요약", description=table, color=discord.Color.blue())
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"❌ 전적 에러: {e}")
        await interaction.followup.send("⚠️ 전적을 불러오는 중 오류가 발생했어요.")

# 📌 /전적전체
@bot.tree.command(name="전적전체", description="모든 유저의 전적 랭킹을 표시합니다.")
async def 전적전체(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        user_data = {}

        for ws in spreadsheet.worksheets():
            rows = ws.get_all_values()[1:]
            for row in rows:
                if len(row) < 2:
                    continue
                name, result = row[0].strip(), row[1].strip()

                if name not in user_data:
                    user_data[name] = {"승": 0, "패": 0}

                if result == "승":
                    user_data[name]["승"] += 1
                elif result == "패":
                    user_data[name]["패"] += 1

        랭킹 = []
        for name, record in user_data.items():
            전 = record["승"] + record["패"]
            if 전 == 0:
                continue
            승률 = (record["승"] / 전) * 100
            랭킹.append((name, record["승"], record["패"], 전, 승률))

        랭킹.sort(key=lambda x: (-x[4], -x[3]))

        if not 랭킹:
            await interaction.followup.send("📭 전적 데이터가 없습니다.")
            return

        # 10명씩 페이지
        pages = [랭킹[i:i+10] for i in range(0, len(랭킹), 10)]
        embeds = []

        for i, page in enumerate(pages):
            lines = ["```\n순위  이름       승  패  전  승률"]
            for idx, (name, 승, 패, 전, 승률) in enumerate(page, start=i*10+1):
                lines.append(f"{idx:<4} {name:<10} {승:<3} {패:<3} {전:<3} {승률:>5.1f}%")
            lines.append("```")
            embed = discord.Embed(
                title=f"📊 전체 전적 랭킹 (페이지 {i+1}/{len(pages)})",
                description="\n".join(lines),
                color=discord.Color.green()
            )
            embeds.append(embed)

        # 첫 페이지 전송
        msg = await interaction.followup.send(embed=embeds[0])
        if len(embeds) > 1:
            await msg.edit(view=PageView(embeds, msg))

    except Exception as e:
        print(f"❌ 전적전체 에러: {e}")
        await interaction.followup.send("⚠️ 전적 전체를 불러오는 중 오류가 발생했어요.")

# 페이지네이션 뷰
class PageView(discord.ui.View):
    def __init__(self, embeds, message):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.message = message
        self.current = 0

    @discord.ui.button(label="⬅️ 이전", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current])

    @discord.ui.button(label="➡️ 다음", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current < len(self.embeds) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.embeds[self.current])

# 실행            
import os
TOKEN = os.getenv("DISCORD_TOKEN")
