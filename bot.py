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
                response = await s.get(os.environ.get('KOYEB_URL', 'http://localhost:8000/health'))
                if response.status == 200:
                    print(f'✓ Ping 성공 ({response.status})')
                else:
                    print(f'⚠️ Ping 응답 이상: {response.status}')
        except Exception as e:
            print(f'❌ Ping 실패: {e}')

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
    try:
        # 약간의 딜레이 후 defer (타이밍 이슈 방지)
        await asyncio.sleep(0.1)
        await interaction.response.defer()

        meal_type = 종류.value
        print(f"\n{'=' * 60}")
        print(f"메뉴 요청 받음: {meal_type} (사용자: {interaction.user.name})")
        print(f"{'=' * 60}")

        # 메뉴 데이터 가져오기 (캐싱 적용됨)
        print(f"메뉴 데이터 수집 시작...")
        menus = await get_menus_by_meal_type(meal_type)

        print(f"메뉴 결과: {len(menus)}개 식단")
        for rest, menu_list in menus.items():
            print(f"  - {rest}: {len(menu_list)}개 메뉴")

        if not menus:
            await interaction.followup.send("❌ 메뉴 정보를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요.")
            return

        # Discord Embed 형식으로 변환
        embed = format_menu_for_discord(meal_type, menus)

        # 메뉴 전송
        await interaction.followup.send(embed=embed)
        print("✅ 메뉴 전송 완료!")

    except discord.errors.NotFound:
        # 인터랙션이 이미 만료된 경우
        print("⚠️ 인터랙션 타이밍 에러 - 무시함")
    except Exception as e:
        print(f"❌ 메뉴 조회 중 에러 발생: {e}")
        import traceback
        traceback.print_exc()

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", ephemeral=True)
            else:
                await interaction.followup.send("❌ 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
        except:
            pass


@bot.tree.command(name='메뉴선택', description='메뉴 중에서 랜덤으로 하나를 골라드립니다')
@app_commands.describe(메뉴들='쉼표(,)로 구분된 메뉴 이름들 (예: 짜장면, 짬뽕, 탕수육)')
async def menu_select(interaction: discord.Interaction, 메뉴들: str):
    await interaction.response.defer()

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

        # 전체 메뉴 목록 표시 (체크 표시를 뒤로)
        menu_list_text = "\n".join([f"{m} {'✅' if m == selected else ''}" for m in menu_list])
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


@bot.tree.command(name='스티커체크', description='채널에서 사용된 스티커 통계를 보여줍니다')
@app_commands.describe(
    메시지수='확인할 최근 메시지 수 (기본값: 500, 최대: 5000)',
    채널들='분석할 채널들 (쉼표로 구분, 기본값: 현재 채널)'
)
async def sticker_check(interaction: discord.Interaction, 메시지수: int = 500, 채널들: str = None):
    await interaction.response.defer()

    try:
        # 메시지 수 제한
        limit = min(max(메시지수, 1), 5000)

        # 채널 파싱
        channels = []
        if 채널들:
            # 쉼표로 분리하고 공백 제거
            channel_mentions = [ch.strip() for ch in 채널들.split(',') if ch.strip()]

            for mention in channel_mentions:
                # <#123456789> 형태의 멘션에서 ID 추출
                if mention.startswith('<#') and mention.endswith('>'):
                    channel_id = mention[2:-1]
                # 숫자만 있는 경우 (ID 직접 입력)
                elif mention.isdigit():
                    channel_id = mention
                else:
                    await interaction.followup.send(f"❌ 올바르지 않은 채널 형식: {mention}\n채널 멘션(#채널명) 또는 ID를 입력해주세요.")
                    return

                # 채널 가져오기
                channel = interaction.guild.get_channel(int(channel_id))
                if channel:
                    channels.append(channel)
                else:
                    await interaction.followup.send(f"❌ 채널을 찾을 수 없습니다: {mention}")
                    return
        else:
            # 채널 지정 안 했으면 현재 채널
            channels = [interaction.channel]

        print(f"\n{'=' * 60}")
        print(f"스티커 체크 요청: 최근 {limit}개 메시지 (사용자: {interaction.user.name})")
        print(f"대상 채널: {[ch.name for ch in channels]}")
        print(f"{'=' * 60}")

        # 서버 스티커 목록 가져오기
        guild_stickers = await interaction.guild.fetch_stickers()
        guild_sticker_ids = {sticker.id for sticker in guild_stickers}
        print(f"서버 스티커 수: {len(guild_sticker_ids)}개")

        # 스티커 카운터
        sticker_counts = {}
        total_messages = 0
        messages_with_stickers = 0

        # 각 채널에서 메시지 읽기
        for channel in channels:
            try:
                async for message in channel.history(limit=limit):
                    total_messages += 1
                    if message.stickers:
                        for sticker in message.stickers:
                            # 서버 스티커만 포함 (Nitro 스티커 제외)
                            if sticker.id in guild_sticker_ids:
                                messages_with_stickers += 1
                                sticker_name = sticker.name
                                sticker_counts[sticker_name] = sticker_counts.get(sticker_name, 0) + 1
            except discord.Forbidden:
                await interaction.followup.send(f"❌ {channel.mention} 채널을 읽을 권한이 없습니다.")
                return
            except Exception as e:
                print(f"채널 {channel.name} 읽기 중 에러: {e}")

        # 결과가 없을 경우
        if not sticker_counts:
            channel_list = ", ".join([ch.mention for ch in channels])
            embed = discord.Embed(
                title="📊 스티커 사용 통계",
                description=f"{channel_list}\n최근 {total_messages}개 메시지에서 서버 스티커가 발견되지 않았습니다.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            print("서버 스티커 사용 없음")
            return

        # 사용 횟수로 정렬
        sorted_stickers = sorted(sticker_counts.items(), key=lambda x: x[1], reverse=True)

        # Embed 생성
        channel_list = ", ".join([ch.mention for ch in channels])
        embed = discord.Embed(
            title="📊 스티커 사용 통계",
            description=f"**분석 채널**: {channel_list}\n**메시지 수**: {total_messages}개 (채널당 최대 {limit}개)",
            color=discord.Color.blue()
        )

        # 통계 정보
        embed.add_field(
            name="📈 요약",
            value=f"스티커가 포함된 메시지: {messages_with_stickers}개\n서로 다른 스티커 종류: {len(sticker_counts)}개",
            inline=False
        )

        # 스티커 목록 (최대 25개까지만 표시)
        sticker_list_text = ""
        for idx, (sticker_name, count) in enumerate(sorted_stickers[:25], 1):
            # 막대 그래프 효과
            bar_length = min(int(count / max(sticker_counts.values()) * 10), 10)
            bar = "█" * bar_length
            sticker_list_text += f"`{idx:2d}.` **{sticker_name}**: {count}회 {bar}\n"

        embed.add_field(
            name="🏆 스티커 순위",
            value=sticker_list_text if sticker_list_text else "스티커 없음",
            inline=False
        )

        # 나머지가 있으면 표시
        if len(sorted_stickers) > 25:
            embed.add_field(
                name="ℹ️ 기타",
                value=f"그 외 {len(sorted_stickers) - 25}개의 스티커가 더 있습니다.",
                inline=False
            )

        embed.set_footer(text=f"요청자: {interaction.user.display_name} | 서버 스티커만 포함")

        await interaction.followup.send(embed=embed)

        print(f"✅ 스티커 통계 전송 완료!")
        print(f"   - 총 메시지: {total_messages}")
        print(f"   - 스티커 메시지: {messages_with_stickers}")
        print(f"   - 스티커 종류: {len(sticker_counts)}")

    except Exception as e:
        print(f"❌ 스티커 체크 중 에러 발생: {e}")
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
