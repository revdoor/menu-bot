import os
from datetime import datetime

import discord
import aiohttp
import asyncio
from aiohttp import web
from discord import app_commands
from discord.ext import commands

from menu import get_menus_by_meal_type
from menu import init_browser, close_browser


def format_menu_for_discord(meal_type, menu_infos):
    """Discord 메시지 형식으로 메뉴 포맷팅"""

    meal_info = {
        "조식": ("🌅 조식", "08:00-09:30"),
        "중식": ("🍽️ 중식", "11:30-13:30"),
        "석식": ("🌙 석식", "17:00-19:00")
    }

    emoji, time_range = meal_info.get(meal_type, ("🍴", ""))

    embed = discord.Embed(
        title=f"{emoji} KAIST 오늘의 식단",
        description=f"**{meal_type}** ({time_range})\n{datetime.now().strftime('%Y년 %m월 %d일')}",
        color=discord.Color.blue()
    )

    if not menu_infos:
        embed.add_field(
            name="❌ 운영 안함",
            value="오늘은 운영하는 식당이 없습니다.",
            inline=False
        )
        return embed

    for restaurant, menus in menu_infos.items():
        menu_text = ""
        for menu in menus:
            menu_lines = menu.split('\n')
            for line in menu_lines:
                line = line.strip()
                if line and line not in ['-', '']:
                    menu_text += f"• {line}\n"

        if menu_text:
            # Discord 필드는 1024자 제한이 있으므로 필요시 자르기
            if len(menu_text) > 1024:
                menu_text = menu_text[:1021] + "..."

            embed.add_field(
                name=f"📍 {restaurant}",
                value=menu_text,
                inline=False
            )

    embed.set_footer(text="KAIST 학생식당 • 메뉴는 사정에 따라 변경될 수 있습니다")

    return embed


async def health_check(request):
    return web.Response(text="OK", status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get('/health', health_check)  # Health Check API 추가
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()


# 봇 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


async def ping():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(os.environ['KOYEB_URL'])
        except Exception as e:
            print(f'Ping 실패: {e}')
            pass

        await asyncio.sleep(180)


# 봇이 준비되었을 때
@bot.event
async def on_ready():
    print(f'{bot.user.name}으로 로그인했습니다!')
    print(f'봇 ID: {bot.user.id}')

    await init_browser()

    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)}개의 슬래시 명령어가 동기화되었습니다.')
    except Exception as e:
        print(f'동기화 실패: {e}')
    print('------')
    bot.loop.create_task(start_web_server())
    bot.loop.create_task(ping())


@bot.tree.command(name='메뉴', description='오늘의 식단을 보여줍니다')
@app_commands.describe(종류='중식, 석식 중 선택')
@app_commands.choices(종류=[
    app_commands.Choice(name='중식', value='중식'),
    app_commands.Choice(name='석식', value='석식')
])
async def menu(interaction: discord.Interaction, 종류: app_commands.Choice[str]):
    await interaction.response.defer()

    try:
        meal_type = 종류.value
        print(f"메뉴 요청: {meal_type}")  # 로그 추가

        menus = await get_menus_by_meal_type(meal_type)

        print(f"메뉴 결과: {menus}")  # 로그 추가
        print(f"메뉴 개수: {len(menus)}")  # 로그 추가

        if not menus:
            await interaction.followup.send("❌ 메뉴 정보를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요.")
            return

        embed = format_menu_for_discord(meal_type, menus)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"메뉴 조회 에러: {e}")  # 상세 에러 로그
        import traceback
        traceback.print_exc()  # 전체 스택 트레이스 출력
        await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}")


@bot.event
async def on_close():
    await close_browser()


bot.run(os.environ['TOKEN'])
