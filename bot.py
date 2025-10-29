"""
KAIST 메뉴봇 - Discord Bot

주요 기능:
- 메뉴 조회 (/메뉴)
- 메뉴 랜덤 선택 (/메뉴선택)
- 스티커 사용 통계 (/스티커체크)
- TTS 기능 (/tts시작, /tts종료)
"""
import os
import random
import asyncio
from typing import List
from functools import wraps

import discord
import aiohttp
from aiohttp import web
from discord import app_commands
from discord.ext import commands

from menu_collector import get_menus_by_meal_type, format_menu_for_discord
from sticker_stats import parse_channels, StickerAnalyzer, create_sticker_embed
from tts_manager import TTSManager
from config import (
    PING_INTERVAL_SECONDS,
    HEALTH_CHECK_PORT,
    MAX_MESSAGE_HISTORY,
    DEFAULT_MESSAGE_HISTORY,
    LOG_MESSAGES
)


# ==================== Web Server ====================

async def health_check(request: web.Request) -> web.Response:
    """헬스체크 엔드포인트"""
    return web.Response(text="OK", status=200)


async def start_web_server() -> None:
    """백그라운드 웹 서버 시작 (헬스체크용)"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', HEALTH_CHECK_PORT)
    await site.start()
    print(f"웹 서버 시작됨 (포트 {HEALTH_CHECK_PORT})")


# ==================== Bot Setup ====================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# TTS 관리자 인스턴스
tts_manager = TTSManager()


# ==================== Error Handling ====================

def handle_interaction_errors(func):
    """
    Discord Interaction 에러 처리 데코레이터

    - NotFound 에러 처리 (타이밍 이슈)
    - 일반 예외 처리 및 로깅
    - 사용자에게 에러 메시지 전송
    """
    @wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            return await func(interaction, *args, **kwargs)

        except discord.errors.NotFound:
            print("⚠️ 인터랙션 타이밍 에러 - 무시함")

        except Exception as e:
            print(f"❌ {func.__name__} 중 에러 발생: {e}")
            import traceback
            traceback.print_exc()

            try:
                error_msg = "❌ 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg)
            except:
                pass

    return wrapper


# ==================== Background Tasks ====================

async def ping_self() -> None:
    """주기적으로 자신에게 ping하여 활성 상태 유지 (무료 호스팅용)"""
    await bot.wait_until_ready()
    koyeb_url = os.environ.get('KOYEB_URL', f'http://localhost:{HEALTH_CHECK_PORT}/health')

    while not bot.is_closed():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(koyeb_url) as response:
                    if response.status == 200:
                        print(LOG_MESSAGES['ping_success'].format(status=response.status))
                    else:
                        print(LOG_MESSAGES['ping_warning'].format(status=response.status))

        except Exception as e:
            print(LOG_MESSAGES['ping_failed'].format(error=e))

        await asyncio.sleep(PING_INTERVAL_SECONDS)


# ==================== Bot Events ====================

@bot.event
async def on_ready() -> None:
    """봇 시작 이벤트"""
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
    bot.loop.create_task(ping_self())


@bot.event
async def on_message(message: discord.Message) -> None:
    """메시지 이벤트 (TTS 처리)"""
    # 봇 자신의 메시지는 무시
    if message.author.bot:
        return

    # TTS 세션 확인
    guild_id = message.guild.id if message.guild else None
    if not guild_id:
        return

    session = tts_manager.get_session(guild_id)
    if not session:
        return

    # TTS 채널인지 확인
    if message.channel.id != session.channel_id:
        return

    # 메시지 유효성 검증
    if not message.content.strip() or message.content.startswith('/'):
        return

    # 큐에 추가 및 재생
    session.add_to_queue(message.content)

    # 재생 중이 아니면 재생 시작
    if session.is_connected() and not session.is_playing():
        asyncio.create_task(tts_manager.play_queue(guild_id))


# ==================== Menu Commands ====================

@bot.tree.command(name='메뉴', description='오늘의 식단을 보여줍니다')
@app_commands.describe(종류='중식, 석식 중 선택')
@app_commands.choices(종류=[
    app_commands.Choice(name='중식', value='중식'),
    app_commands.Choice(name='석식', value='석식')
])
@handle_interaction_errors
async def menu(interaction: discord.Interaction, 종류: app_commands.Choice[str]) -> None:
    """메뉴 조회 명령어"""
    await asyncio.sleep(0.1)  # 타이밍 이슈 방지
    await interaction.response.defer()

    meal_type = 종류.value
    print(f"\n{'=' * 60}")
    print(f"메뉴 요청 받음: {meal_type} (사용자: {interaction.user.name})")
    print(f"{'=' * 60}")

    # 메뉴 데이터 가져오기
    menus = await get_menus_by_meal_type(meal_type)

    print(f"메뉴 결과: {len(menus)}개 식단")
    for rest, menu_list in menus.items():
        print(f"  - {rest}: {len(menu_list)}개 메뉴")

    if not menus:
        await interaction.followup.send("❌ 메뉴 정보를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요.")
        return

    # Discord Embed 형식으로 변환 및 전송
    embed = format_menu_for_discord(meal_type, menus)
    await interaction.followup.send(embed=embed)
    print("✅ 메뉴 전송 완료!")


@bot.tree.command(name='메뉴선택', description='메뉴 중에서 랜덤으로 하나를 골라드립니다')
@app_commands.describe(메뉴들='쉼표(,)로 구분된 메뉴 이름들 (예: 짜장면, 짬뽕, 탕수육)')
@handle_interaction_errors
async def menu_select(interaction: discord.Interaction, 메뉴들: str) -> None:
    """메뉴 랜덤 선택 명령어"""
    await interaction.response.defer()

    # 메뉴 파싱
    menu_list = [menu.strip() for menu in 메뉴들.split(',') if menu.strip()]

    if not menu_list:
        await interaction.followup.send("❌ 메뉴를 입력해주세요!\n예시: `/메뉴선택 짜장면, 짬뽕, 탕수육`")
        return

    if len(menu_list) == 1:
        await interaction.followup.send(f"메뉴가 하나밖에 없네요! 🤔\n선택: **{menu_list[0]}** 🍽️")
        return

    # 랜덤 선택 및 Embed 생성
    selected = random.choice(menu_list)
    embed = _create_menu_select_embed(menu_list, selected, interaction.user.display_name)

    await interaction.followup.send(embed=embed)
    print(f"메뉴 선택: {메뉴들} → {selected}")


def _create_menu_select_embed(menu_list: List[str], selected: str, user_name: str) -> discord.Embed:
    """메뉴 선택 결과 Embed 생성 (내부 헬퍼 함수)"""
    embed = discord.Embed(
        title="🎲 메뉴 선택 결과",
        description=f"고민 중인 메뉴: {len(menu_list)}개",
        color=discord.Color.green()
    )

    # 전체 메뉴 목록 표시
    menu_list_text = "\n".join([f"{m} {'✅' if m == selected else ''}" for m in menu_list])
    embed.add_field(name="메뉴 목록", value=menu_list_text, inline=False)

    # 선택된 메뉴 강조
    embed.add_field(name="🎯 오늘의 선택", value=f"# {selected}", inline=False)
    embed.set_footer(text=f"요청자: {user_name}")

    return embed


# ==================== Sticker Statistics ====================

@bot.tree.command(name='스티커체크', description='채널에서 사용된 스티커 통계를 보여줍니다')
@app_commands.describe(
    메시지수=f'확인할 최근 메시지 수 (기본값: {DEFAULT_MESSAGE_HISTORY}, 최대: {MAX_MESSAGE_HISTORY})',
    채널들='분석할 채널들 (쉼표로 구분, 기본값: 현재 채널)'
)
@handle_interaction_errors
async def sticker_check(
    interaction: discord.Interaction,
    메시지수: int = DEFAULT_MESSAGE_HISTORY,
    채널들: str = None
) -> None:
    """스티커 사용 통계 조회 명령어"""
    await interaction.response.defer()

    # 메시지 수 제한
    limit = min(max(메시지수, 1), MAX_MESSAGE_HISTORY)

    # 채널 파싱
    try:
        channels = parse_channels(채널들, interaction.guild, interaction.channel)
    except ValueError as e:
        await interaction.followup.send(f"❌ {str(e)}\n채널 멘션(#채널명) 또는 ID를 입력해주세요.")
        return

    print(f"\n{'=' * 60}")
    print(f"스티커 체크 요청: 최근 {limit}개 메시지 (사용자: {interaction.user.name})")
    print(f"대상 채널: {[ch.name for ch in channels]}")
    print(f"{'=' * 60}")

    # 스티커 통계 수집
    analyzer = StickerAnalyzer(interaction.guild)
    await analyzer.initialize()

    try:
        stats = await analyzer.collect_stats(channels, limit)
    except PermissionError as e:
        await interaction.followup.send(f"❌ {str(e)}")
        return

    # Embed 생성 및 전송
    embed = create_sticker_embed(channels, stats, limit, interaction.user.display_name)
    await interaction.followup.send(embed=embed)

    print(f"✅ 스티커 통계 전송 완료!")
    print(f"   - 총 메시지: {stats['total_messages']}")
    print(f"   - 스티커 메시지: {stats['messages_with_stickers']}")
    print(f"   - 스티커 종류: {len(stats['sticker_counts'])}")


# ==================== TTS Commands ====================

@bot.tree.command(name='tts시작', description='음성 채널에 참가하여 특정 채널의 메시지를 TTS로 읽어줍니다')
@app_commands.describe(채널='TTS로 읽을 텍스트 채널')
@handle_interaction_errors
async def tts_start(interaction: discord.Interaction, 채널: discord.TextChannel) -> None:
    """TTS 시작 명령어"""
    await interaction.response.defer()

    # 사용자가 음성 채널에 있는지 확인
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ 먼저 음성 채널에 참가해주세요!")
        return

    voice_channel = interaction.user.voice.channel
    guild_id = interaction.guild.id

    # 이미 TTS 세션이 있는 경우
    existing_session = tts_manager.get_session(guild_id)
    if existing_session and existing_session.is_connected():
        await interaction.followup.send(
            f"❌ 이미 TTS가 실행 중입니다!\n"
            f"음성 채널: {existing_session.voice_client.channel.mention}\n"
            f"TTS 채널: <#{existing_session.channel_id}>"
        )
        return

    # 음성 채널에 연결
    try:
        voice_client = await voice_channel.connect()
    except Exception as e:
        await interaction.followup.send(f"❌ 음성 채널 연결 실패: {str(e)}")
        return

    # TTS 세션 생성
    tts_manager.create_session(guild_id, voice_client, 채널.id)

    # 안내 메시지
    embed = discord.Embed(
        title="🔊 TTS 시작",
        description=f"음성 채널에 참가했습니다!",
        color=discord.Color.green()
    )
    embed.add_field(name="음성 채널", value=voice_channel.mention, inline=True)
    embed.add_field(name="TTS 채널", value=채널.mention, inline=True)
    embed.add_field(
        name="ℹ️ 사용 방법",
        value=f"{채널.mention} 채널에 메시지를 입력하면 TTS로 읽어줍니다.\n종료하려면 `/tts종료` 명령어를 사용하세요.",
        inline=False
    )

    await interaction.followup.send(embed=embed)
    print(f"TTS 시작: 서버={interaction.guild.name}, 음성채널={voice_channel.name}, TTS채널={채널.name}")


@bot.tree.command(name='tts종료', description='TTS를 종료하고 음성 채널에서 나갑니다')
@handle_interaction_errors
async def tts_stop(interaction: discord.Interaction) -> None:
    """TTS 종료 명령어"""
    await interaction.response.defer()

    guild_id = interaction.guild.id

    # 세션 확인 및 종료
    if not tts_manager.get_session(guild_id):
        await interaction.followup.send("❌ 실행 중인 TTS가 없습니다!")
        return

    # 연결 해제
    await tts_manager.disconnect_session(guild_id)

    await interaction.followup.send("✅ TTS를 종료했습니다!")
    print(f"TTS 종료: 서버={interaction.guild.name}")


# ==================== Bot Start ====================

if __name__ == "__main__":
    token = os.environ.get('TOKEN')
    if not token:
        print("❌ TOKEN 환경변수가 설정되지 않았습니다!")
    else:
        print("봇 시작 중...")
        bot.run(token)
