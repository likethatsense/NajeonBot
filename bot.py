import os
import discord
from discord.ext import commands
from discord import app_commands
import json
import base64
import gspread
from google.oauth2 import service_account

# ✅ 로컬에서만 .env 로드 (Render에선 자동으로 환경변수 주입되므로 불필요)
if os.getenv("RENDER") != "true":
    from dotenv import load_dotenv
    load_dotenv()

# ✅ 환경변수 불러오기
GOOGLE_CREDS_BASE64 = os.getenv("GOOGLE_CREDS_BASE64")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ✅ 디버깅용 출력 (Render에서 환경변수 제대로 들어왔는지 확인)
print("🔍 GOOGLE_CREDS_BASE64 is", "SET" if GOOGLE_CREDS_BASE64 else "NOT SET")
print("🔍 Length:", len(GOOGLE_CREDS_BASE64) if GOOGLE_CREDS_BASE64 else "N/A")

# ✅ 예외 처리
if not GOOGLE_CREDS_BASE64:
    raise ValueError("❌ 환경변수 GOOGLE_CREDS_BASE64가 설정되지 않았습니다.")
if not SPREADSHEET_NAME:
    raise ValueError("❌ 환경변수 SPREADSHEET_NAME이 설정되지 않았습니다.")
if not DISCORD_TOKEN:
    raise ValueError("❌ 환경변수 DISCORD_TOKEN이 설정되지 않았습니다.")

# ✅ base64 → JSON → Credentials 객체
json_str = base64.b64decode(GOOGLE_CREDS_BASE64).decode("utf-8")
creds_dict = json.loads(json_str)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
credentials = service_account.Credentials.from_service_account_info(
    creds_dict, scopes=SCOPES
)

# ✅ Google Spreadsheet 연결
gc = gspread.authorize(credentials)
spreadsheet = gc.open(SPREADSHEET_NAME)

# ✅ Discord 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 봇 로그인 완료: {bot.user.name}")

# ✅ /전적 커맨드
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

# ✅ /전적전체 커맨드
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
        pages = [랭킹[i:i + 10] for i in range(0, len(랭킹), 10)]
        embeds = []

        for i, page in enumerate(pages):
            lines = ["```\n순위  이름       승  패  전  승률"]
            for idx, (name, 승, 패, 전, 승률) in enumerate(page, start=i * 10 + 1):
                lines.append(f"{idx:<4} {name:<10} {승:<3} {패:<3} {전:<3} {승률:>5.1f}%")
            lines.append("```")
            embed = discord.Embed(
                title=f"📊 전체 전적 랭킹 (페이지 {i + 1}/{len(pages)})",
                description="\n".join(lines),
                color=discord.Color.green()
            )
            embeds.append(embed)

        msg = await interaction.followup.send(embed=embeds[0])
        if len(embeds) > 1:
            await msg.edit(view=PageView(embeds, msg))
    except Exception as e:
        print(f"❌ 전적전체 에러: {e}")
        await interaction.followup.send("⚠️ 전적 전체를 불러오는 중 오류가 발생했어요.")

# ✅ 페이지네이션
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

# ✅ 실행
bot.run(DISCORD_TOKEN)
