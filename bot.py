import os
import random

import discord
import aiohttp
import asyncio
from aiohttp import web
from discord import app_commands
from discord.ext import commands

from menu_collector import get_menus_by_meal_type, format_menu_for_discord


async def health_check(request):
    return web.Response(text="OK", status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("웹 서버 시작됨 (포트 8000)")


# 봇 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


async def ping():
    """주기적으로 서버에 ping"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(os.environ.get('KOYEB_URL', 'http://localhost:8000/health'))
        except Exception as e:
            print(f'Ping 실패: {e}')
            pass

        await asyncio.sleep(180)


# 봇이 준비되었을 때
@bot.event
async def on_ready():
    print(f'{bot.user.name}으로 로그인했습니다!')
    print(f'봇 ID: {bot.user.id}')

    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)}개의 슬래시 명령어가 동기화되었습니다.')
    except Exception as e:
        print(f'동기화 실패: {e}')

    print('------')

    # 백그라운드 태스크 시작
    bot.loop.create_task(start_web_server())
    bot.loop.create_task(ping())


@bot.tree.command(name='메뉴', description='오늘의 식단을 보여줍니다')
@app_commands.describe(종류='중식, 석식 중 선택')
@app_commands.choices(종류=[
    app_commands.Choice(name='중식', value='중식'),
    app_commands.Choice(name='석식', value='석식')
])
async def menu(interaction: discord.Interaction, 종류: app_commands.Choice[str]):
    # 즉시 응답하여 3초 제한 회피
    await interaction.response.defer(thinking=True)

    try:
        meal_type = 종류.value
        print(f"\n{'=' * 60}")
        print(f"메뉴 요청 받음: {meal_type} (사용자: {interaction.user.name})")
        print(f"{'=' * 60}")

        # 메뉴 데이터 가져오기
        print(f"메뉴 데이터 수집 시작...")
        menus = await get_menus_by_meal_type(meal_type)

        print(f"메뉴 결과: {len(menus)}개 식당")
        for rest, menu_list in menus.items():
            print(f"  - {rest}: {len(menu_list)}개 메뉴")

        if not menus:
            await interaction.followup.send("❌ 메뉴 정보를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요.")
            return

        # Discord Embed 형식으로 변환
        embed = format_menu_for_discord(meal_type, menus)

        # 메뉴 전송
        await interaction.followup.send(embed=embed)
        print("메뉴 전송 완료!")

    except Exception as e:
        print(f"메뉴 조회 중 에러 발생: {e}")
        import traceback
        traceback.print_exc()

        try:
            await interaction.followup.send(f"❌ 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        except:
            pass


@bot.tree.command(name='메뉴선택', description='메뉴 중에서 랜덤으로 하나를 골라드립니다')
@app_commands.describe(메뉴들='쉼표(,)로 구분된 메뉴 이름들 (예: 짜장면, 짬뽕, 탕수육)')
async def menu_select(interaction: discord.Interaction, 메뉴들: str):
    await interaction.response.defer(thinking=True)

    try:
        # 쉼표로 분리하고 공백 제거
        menu_list = [menu.strip() for menu in 메뉴들.split(',') if menu.strip()]

        if not menu_list:
            await interaction.followup.send("❌ 메뉴를 입력해주세요!\n예시: `/메뉴선택 짜장면, 짬뽕, 탕수육`")
            return

        if len(menu_list) == 1:
            await interaction.followup.send(f"메뉴가 하나밖에 없네요! 🤔\n선택: **{menu_list[0]}** 🍽️")
            return

        # 랜덤 선택
        selected = random.choice(menu_list)

        # Embed로 예쁘게 표시
        embed = discord.Embed(
            title="🎲 메뉴 선택 결과",
            description=f"고민 중인 메뉴: {len(menu_list)}개",
            color=discord.Color.green()
        )

        # 전체 메뉴 목록 표시
        menu_list_text = "\n".join([f"{'✅ ' if m == selected else '　 '}{m}" for m in menu_list])
        embed.add_field(
            name="메뉴 목록",
            value=menu_list_text,
            inline=False
        )

        # 선택된 메뉴 강조
        embed.add_field(
            name="🎯 오늘의 선택",
            value=f"# {selected}",
            inline=False
        )

        embed.set_footer(text=f"요청자: {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)
        print(f"메뉴 선택: {메뉴들} → {selected}")

    except Exception as e:
        print(f"메뉴 선택 중 에러: {e}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ 오류가 발생했습니다: {str(e)}")


# 봇 실행
if __name__ == "__main__":
    token = os.environ.get('TOKEN')
    if not token:
        print("❌ TOKEN 환경변수가 설정되지 않았습니다!")
    else:
        print("봇 시작 중...")
        bot.run(token)
