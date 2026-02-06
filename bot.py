"""
KAIST 메뉴봇 - Discord Bot

주요 기능:
- 메뉴 조회 (/메뉴)
- 메뉴 랜덤 선택 (/메뉴선택)
- 메뉴 투표 (/투표시작, /메뉴제안, /메뉴제안취소)
- 스티커 사용 통계 (/스티커체크)
- TTS 기능 (/tts시작, /tts종료)
- 같이먹자 기능 (/같이먹자)
"""
import os
import logging
import random
import asyncio
from functools import wraps

import discord
import aiohttp
from aiohttp import web
from discord import app_commands
from discord.ext import commands

from menu_collector import get_menus_by_meal_type, format_menu_for_discord
from sticker_stats import parse_channels, StickerAnalyzer, create_sticker_embed
from tts_manager import TTSManager, AVAILABLE_VOICES
from menu_voting import (
    VotingManager,
    VotingSession,
    MenuProposalView,
    create_proposal_embed,
    update_voting_message,
    is_admin
)
from eat_together import (
    EatTogetherManager,
    EatTogetherView,
    create_eat_together_embed
)
from config import (
    PING_INTERVAL_SECONDS,
    HEALTH_CHECK_PORT,
    MAX_MESSAGE_HISTORY,
    DEFAULT_MESSAGE_HISTORY,
    LOG_MESSAGES,
    setup_logging
)

# 로거 설정
logger = logging.getLogger(__name__)


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
    logger.info(f"웹 서버 시작됨 (포트 {HEALTH_CHECK_PORT})")


# ==================== Bot Setup ====================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# TTS 관리자 인스턴스
tts_manager = TTSManager()

# 투표 관리자 인스턴스
voting_manager = VotingManager()

# 같이먹자 관리자 인스턴스
eat_together_manager = EatTogetherManager()


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
            logger.warning(f"⚠️ 인터랙션 타이밍 에러 (NotFound) - 무시함 (함수: {func.__name__}, 사용자: {interaction.user.name if hasattr(interaction, 'user') else 'Unknown'})")

        except Exception as e:
            logger.error(f"❌ {func.__name__} 중 에러 발생: {e}", exc_info=True)

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
                        logger.debug(LOG_MESSAGES['ping_success'].format(status=response.status))
                    else:
                        logger.warning(LOG_MESSAGES['ping_warning'].format(status=response.status))

        except Exception as e:
            logger.error(LOG_MESSAGES['ping_failed'].format(error=e))

        await asyncio.sleep(PING_INTERVAL_SECONDS)


# ==================== Bot Events ====================

@bot.event
async def on_ready() -> None:
    """봇 시작 이벤트"""
    logger.info(f'{bot.user.name}으로 로그인했습니다!')
    logger.info(f'봇 ID: {bot.user.id}')

    try:
        # 명령어 동기화 (글로벌)
        synced = await bot.tree.sync()
        logger.info(f'✅ {len(synced)}개의 슬래시 명령어가 동기화되었습니다.')

        # 동기화된 명령어 목록 출력
        command_names = [cmd.name for cmd in synced]
        logger.info(f'동기화된 명령어: {", ".join(command_names)}')

    except Exception as e:
        logger.error(f'❌ 동기화 실패: {e}', exc_info=True)

    logger.info('------')

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

    # 큐에 추가 및 재생 (사용자 ID 포함)
    session.add_to_queue(message.content, message.author.id)

    # 재생 중이 아니면 재생 시작
    if session.is_connected() and not session.is_playing():
        asyncio.create_task(tts_manager.play_queue(guild_id))


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState
) -> None:
    """음성 상태 변경 이벤트 - TTS 자동 재연결 및 빈 채널 종료"""
    guild_id = member.guild.id
    session = tts_manager.get_session(guild_id)

    if not session:
        return

    # 봇 자신의 상태 변경: 연결 끊김 시 재연결
    if member.id == bot.user.id:
        if before.channel and not after.channel:
            logger.info(f"TTS 연결 끊김 감지 (guild={guild_id}), 재연결 시도...")

            await asyncio.sleep(1)

            try:
                voice_client = await before.channel.connect()
                session.voice_client = voice_client
                logger.info(f"TTS 자동 재연결 성공 (guild={guild_id}, channel={before.channel.name})")

                if session.queue and not session.is_playing():
                    asyncio.create_task(tts_manager.play_queue(guild_id))

            except Exception as e:
                logger.error(f"TTS 자동 재연결 실패 (guild={guild_id}): {e}")
                tts_manager.remove_session(guild_id)
        return

    # 다른 멤버가 음성 채널에서 나간 경우: 빈 채널이면 종료
    if before.channel and session.voice_client and session.voice_client.channel == before.channel:
        # 봇을 제외한 멤버 수 확인
        members_in_channel = [m for m in before.channel.members if not m.bot]

        if len(members_in_channel) == 0:
            logger.info(f"음성 채널에 아무도 없음, TTS 종료 (guild={guild_id})")
            await tts_manager.disconnect_session(guild_id)


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
    await interaction.response.defer()

    meal_type = 종류.value
    logger.info(f"메뉴 요청 받음: {meal_type} (사용자: {interaction.user.name})")

    # 메뉴 데이터 가져오기
    menus = await get_menus_by_meal_type(meal_type)

    logger.info(f"메뉴 결과: {len(menus)}개 식당")
    for rest, menu_list in menus.items():
        logger.debug(f"  - {rest}: {len(menu_list)}개 메뉴")

    if not menus:
        await interaction.followup.send("❌ 메뉴 정보를 가져오는데 실패했습니다. 잠시 후 다시 시도해주세요.")
        return

    # Discord Embed 형식으로 변환 및 전송
    embed = format_menu_for_discord(meal_type, menus)
    await interaction.followup.send(embed=embed)
    logger.info("✅ 메뉴 전송 완료!")


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
    logger.info(f"메뉴 선택: {메뉴들} → {selected}")


def _create_menu_select_embed(menu_list: list[str], selected: str, user_name: str) -> discord.Embed:
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

    logger.info(f"스티커 체크 요청: 최근 {limit}개 메시지 (사용자: {interaction.user.name})")
    logger.info(f"대상 채널: {[ch.name for ch in channels]}")

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

    logger.info(f"✅ 스티커 통계 전송 완료!")
    logger.debug(f"   - 총 메시지: {stats['total_messages']}")
    logger.debug(f"   - 스티커 메시지: {stats['messages_with_stickers']}")
    logger.debug(f"   - 스티커 종류: {len(stats['sticker_counts'])}")


# ==================== TTS Commands ====================

@bot.tree.command(name='tts시작', description='음성 채널에 참가하여 특정 채널의 메시지를 TTS로 읽어줍니다')
@app_commands.describe(
    채널='TTS로 읽을 텍스트 채널',
    보이스설정채널='사용자별 보이스 설정을 저장하는 채널 (선택)'
)
@handle_interaction_errors
async def tts_start(
    interaction: discord.Interaction,
    채널: discord.TextChannel,
    보이스설정채널: discord.TextChannel = None
) -> None:
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
    voice_config_channel_id = 보이스설정채널.id if 보이스설정채널 else None
    tts_manager.create_session(guild_id, voice_client, 채널.id, voice_config_channel_id)

    # 보이스 설정 로드 (설정 채널이 지정된 경우)
    loaded_count = 0
    if 보이스설정채널:
        loaded_count = await tts_manager.load_voice_settings(guild_id, 보이스설정채널)

    # 안내 메시지
    embed = discord.Embed(
        title="🔊 TTS 시작",
        description=f"음성 채널에 참가했습니다!",
        color=discord.Color.green()
    )
    embed.add_field(name="음성 채널", value=voice_channel.mention, inline=True)
    embed.add_field(name="TTS 채널", value=채널.mention, inline=True)

    if 보이스설정채널:
        embed.add_field(name="보이스 설정 채널", value=보이스설정채널.mention, inline=True)
        embed.add_field(name="로드된 보이스 설정", value=f"{loaded_count}개", inline=True)

    usage_text = f"{채널.mention} 채널에 메시지를 입력하면 TTS로 읽어줍니다.\n종료하려면 `/tts종료` 명령어를 사용하세요."
    if 보이스설정채널:
        usage_text += f"\n보이스 변경: `/tts보이스` 명령어를 사용하세요."

    embed.add_field(name="ℹ️ 사용 방법", value=usage_text, inline=False)

    await interaction.followup.send(embed=embed)
    logger.info(f"TTS 시작: 서버={interaction.guild.name}, 음성채널={voice_channel.name}, TTS채널={채널.name}, 보이스설정채널={보이스설정채널.name if 보이스설정채널 else 'None'}")


@bot.tree.command(name='tts종료', description='TTS를 종료하고 음성 채널에서 나갑니다')
@handle_interaction_errors
async def tts_stop(interaction: discord.Interaction) -> None:
    """TTS 종료 명령어"""
    if not interaction.response.is_done():
        await interaction.response.defer()

    guild_id = interaction.guild.id

    # 세션 확인 및 종료
    if not tts_manager.get_session(guild_id):
        await interaction.followup.send("❌ 실행 중인 TTS가 없습니다!")
        return

    # 연결 해제
    await tts_manager.disconnect_session(guild_id)

    await interaction.followup.send("✅ TTS를 종료했습니다!")
    logger.info(f"TTS 종료: 서버={interaction.guild.name}")


# TTS 보이스 선택 choices 생성
def _create_voice_choices() -> list[app_commands.Choice[str]]:
    """사용 가능한 보이스 목록을 Choice 리스트로 변환"""
    return [
        app_commands.Choice(name=display_name, value=key)
        for key, (voice_id, display_name) in AVAILABLE_VOICES.items()
    ]


@bot.tree.command(name='tts보이스', description='TTS 보이스를 변경합니다')
@app_commands.describe(보이스='사용할 보이스')
@app_commands.choices(보이스=_create_voice_choices())
@handle_interaction_errors
async def tts_voice(interaction: discord.Interaction, 보이스: app_commands.Choice[str]) -> None:
    """TTS 보이스 변경 명령어"""
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    voice_key = 보이스.value

    # 세션 확인
    session = tts_manager.get_session(guild_id)
    if not session:
        await interaction.response.send_message("❌ 실행 중인 TTS가 없습니다!", ephemeral=True)
        return

    # 보이스 정보 가져오기
    if voice_key not in AVAILABLE_VOICES:
        await interaction.response.send_message("❌ 유효하지 않은 보이스입니다!", ephemeral=True)
        return

    voice_id, display_name = AVAILABLE_VOICES[voice_key]

    # 세션 캐시에 보이스 설정 저장
    session.set_user_voice(user_id, voice_id)

    # 설정 채널이 있으면 채널에도 저장
    if session.voice_config_channel_id:
        config_channel = interaction.guild.get_channel(session.voice_config_channel_id)
        if config_channel:
            await tts_manager.save_voice_setting(config_channel, user_id, voice_key)

    await interaction.response.send_message(
        f"✅ TTS 보이스가 **{display_name}**으로 변경되었습니다!",
        ephemeral=True
    )
    logger.info(f"TTS 보이스 변경: 사용자={interaction.user.name}, 보이스={display_name}")


# ==================== Menu Voting Commands ====================

@bot.tree.command(name='투표시작', description='메뉴 투표를 시작합니다')
@app_commands.describe(
    제목='투표 제목 (예: 오늘 점심 메뉴)',
    투표제한='투표 제한 여부 (True: 허용된 사람만 투표 가능)'
)
async def vote_start(interaction: discord.Interaction, 제목: str, 투표제한: bool = False) -> None:
    """투표 시작 명령어"""
    try:
        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        creator_id = interaction.user.id

        # 이미 진행 중인 투표 확인
        existing_session = voting_manager.get_session(guild_id)
        if existing_session:
            await interaction.response.send_message(
                f"❌ 이미 진행 중인 투표가 있습니다!\n"
                f"제목: **{existing_session.title}**\n"
                f"먼저 진행 중인 투표를 종료해주세요.",
                ephemeral=True
            )
            return

        # 새 투표 세션 생성
        session = voting_manager.create_session(guild_id, channel_id, creator_id, 제목, is_restricted=투표제한)
        if not session:
            await interaction.response.send_message("❌ 투표 세션 생성에 실패했습니다.", ephemeral=True)
            return

        logger.info(f"✅ 투표 세션 생성됨 - guild_id: {guild_id}, 제목: {제목}")
        logger.debug(f"현재 활성 세션: {list(voting_manager.sessions.keys())}")

        # 메뉴 제안 단계 Embed 및 View 생성
        embed = create_proposal_embed(session)
        view = MenuProposalView(session, voting_manager)

        await interaction.response.send_message(embed=embed, view=view)

        # 메시지 ID 저장 (갱신용)
        # response.send_message는 Message 객체를 반환하지 않으므로 original_response()로 가져옴
        # 타이밍 이슈 방지를 위해 재시도
        message = None
        for attempt in range(3):
            try:
                await asyncio.sleep(0.1 * attempt)  # 재시도 시 약간의 지연
                message = await interaction.original_response()
                session.message_id = message.id
                logger.info(f"투표 메시지 ID 저장: {message.id}")
                break
            except discord.errors.NotFound as e:
                if attempt < 2:
                    logger.warning(f"original_response() 재시도 {attempt + 1}/3: {e}")
                else:
                    logger.error(f"original_response() 최종 실패: {e}")
                    # 세션은 생성되었지만 message_id가 없는 상태
                    # 나중에 메뉴 제안 시 업데이트 불가
                    raise

        logger.info(f"투표 세션 생성 완료: {제목} (생성자: {interaction.user.name})")

    except discord.errors.NotFound as e:
        logger.error(f"⚠️ 투표시작 인터랙션 NotFound 에러: {e} (사용자: {interaction.user.name})")
        # message_id를 가져오지 못한 경우 세션 정리
        if 'session' in locals() and session and not session.message_id:
            voting_manager.close_session(guild_id)
            logger.warning(f"message_id 없는 세션 정리: {session.title}")
    except Exception as e:
        logger.error(f"❌ 투표시작 중 에러 발생: {e}", exc_info=True)
        # 세션이 생성되었지만 message_id가 없으면 정리
        if 'session' in locals() and session and not session.message_id:
            voting_manager.close_session(guild_id)
            logger.warning(f"에러 발생으로 message_id 없는 세션 정리: {session.title}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 오류가 발생했습니다.", ephemeral=True)
        except:
            pass


@bot.tree.command(name='메뉴제안', description='투표에 메뉴를 제안합니다')
@app_commands.describe(메뉴명='제안할 메뉴 이름')
async def propose_menu(interaction: discord.Interaction, 메뉴명: str) -> None:
    """메뉴 제안 명령어"""
    try:
        logger.debug(f"[{interaction.user.name}] 메뉴 제안 시작: {메뉴명}")

        # defer 제거하고 즉시 응답 체계로 변경
        guild_id = interaction.guild.id
        logger.debug(f"현재 활성 세션: {list(voting_manager.sessions.keys())}")

        session = voting_manager.get_session(guild_id)

        if not session:
            logger.warning(f"세션을 찾을 수 없음 - guild_id: {guild_id}")
            await interaction.response.send_message("❌ 진행 중인 투표가 없습니다!", ephemeral=True)
            return

        if session.voting_started:
            await interaction.response.send_message("❌ 이미 투표가 시작되어 메뉴를 제안할 수 없습니다!", ephemeral=True)
            return

        # 메뉴 추가
        success = session.add_menu(메뉴명, interaction.user.id)
        if not success:
            await interaction.response.send_message(f"❌ '{메뉴명}' 메뉴는 이미 제안되었습니다!", ephemeral=True)
            return

        # 즉시 사용자에게 응답
        await interaction.response.send_message(f"✅ '{메뉴명}' 메뉴가 제안되었습니다!", ephemeral=True)
        logger.info(f"메뉴 제안: {메뉴명} (제안자: {interaction.user.name})")
        logger.debug(f"현재 세션 정보 - 메뉴 수: {len(session.menus)}, message_id: {session.message_id}")

        # 메인 메시지 업데이트 (interaction 사용)
        await update_voting_message(interaction, session)

    except discord.errors.NotFound as e:
        logger.warning(f"⚠️ 메뉴제안 인터랙션 NotFound 에러: {e} (사용자: {interaction.user.name})")
    except Exception as e:
        logger.error(f"❌ 메뉴제안 중 에러 발생: {e}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 오류가 발생했습니다.", ephemeral=True)
        except:
            pass


async def menu_proposal_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """메뉴 제안 취소를 위한 자동완성 - 본인이 제안한 메뉴만 표시 (관리자와 생성자는 모든 메뉴)"""
    guild_id = interaction.guild.id
    session = voting_manager.get_session(guild_id)

    if not session:
        return []

    # 관리자 또는 생성자면 모든 메뉴, 아니면 본인이 제안한 메뉴만
    is_creator = interaction.user.id == session.creator_id
    if is_admin(interaction.user.name) or is_creator:
        user_menus = list(session.menus.keys())
    else:
        user_menus = [
            menu_name for menu_name, proposer_id in session.menus.items()
            if proposer_id == interaction.user.id
        ]

    # 현재 입력값과 매칭되는 메뉴 필터링
    if current:
        user_menus = [m for m in user_menus if current.lower() in m.lower()]

    # 최대 25개까지만 반환 (Discord 제한)
    return [
        app_commands.Choice(name=menu, value=menu)
        for menu in user_menus[:25]
    ]


@bot.tree.command(name='메뉴제안취소', description='자신이 제안한 메뉴를 취소합니다 (생성자/관리자는 모든 메뉴 취소 가능)')
@app_commands.describe(메뉴명='취소할 메뉴 이름')
@app_commands.autocomplete(메뉴명=menu_proposal_autocomplete)
async def cancel_menu_proposal(interaction: discord.Interaction, 메뉴명: str) -> None:
    """메뉴 제안 취소 명령어"""
    try:
        guild_id = interaction.guild.id
        session = voting_manager.get_session(guild_id)

        if not session:
            await interaction.response.send_message("❌ 진행 중인 투표가 없습니다!", ephemeral=True)
            return

        # 관리자 여부 확인
        user_is_admin = is_admin(interaction.user.name)
        is_creator = interaction.user.id == session.creator_id

        # 메뉴 삭제 (관리자면 is_admin=True 전달)
        success = session.remove_menu(메뉴명, interaction.user.id, is_admin=user_is_admin)
        if not success:
            await interaction.response.send_message(
                f"❌ '{메뉴명}' 메뉴를 취소할 수 없습니다.\n"
                f"(메뉴가 존재하지 않거나, 본인이 제안한 메뉴가 아니거나, 이미 투표가 시작되었습니다)",
                ephemeral=True
            )
            return

        # 즉시 사용자에게 응답
        suffix = ""
        if user_is_admin:
            suffix = " [관리자 권한]"
        elif is_creator:
            suffix = " [생성자 권한]"

        await interaction.response.send_message(f"✅ '{메뉴명}' 메뉴 제안이 취소되었습니다!{suffix}", ephemeral=True)
        logger.info(f"메뉴 제안 취소: {메뉴명} (사용자: {interaction.user.name}, 관리자: {user_is_admin}, 생성자: {is_creator})")

        # 메인 메시지 업데이트 (interaction 사용)
        await update_voting_message(interaction, session)

    except discord.errors.NotFound as e:
        logger.warning(f"⚠️ 메뉴제안취소 인터랙션 NotFound 에러: {e}")
    except Exception as e:
        logger.error(f"❌ 메뉴제안취소 중 에러 발생: {e}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 오류가 발생했습니다.", ephemeral=True)
        except:
            pass


@bot.tree.command(name='투표허용', description='제한된 투표에서 사용자를 허용합니다')
@app_commands.describe(사용자='허용할 사용자 (멘션)')
async def allow_voter(interaction: discord.Interaction, 사용자: discord.User) -> None:
    """투표 허용 명령어"""
    try:
        guild_id = interaction.guild.id
        session = voting_manager.get_session(guild_id)

        if not session:
            await interaction.response.send_message("❌ 진행 중인 투표가 없습니다!", ephemeral=True)
            return

        # 투표 생성자만 허용 가능
        if interaction.user.id != session.creator_id:
            await interaction.response.send_message(
                "❌ 투표를 시작한 사람만 다른 사용자를 허용할 수 있습니다!",
                ephemeral=True
            )
            return

        # 제한 모드가 아니면 허용 불필요
        if not session.is_restricted:
            await interaction.response.send_message(
                "❌ 이 투표는 제한 모드가 아닙니다. 모든 사용자가 투표할 수 있습니다.",
                ephemeral=True
            )
            return

        # 이미 허용된 사용자인지 확인
        if session.is_voter_allowed(사용자.id):
            await interaction.response.send_message(
                f"ℹ️ {사용자.mention}님은 이미 투표 가능합니다.",
                ephemeral=True
            )
            return

        # 허용 목록에 추가
        session.add_allowed_voter(사용자.id)

        await interaction.response.send_message(
            f"✅ {사용자.mention}님이 투표 허용 목록에 추가되었습니다!",
            ephemeral=True
        )
        logger.info(f"투표 허용: {사용자.name} (session: {session.title}, by: {interaction.user.name})")

    except Exception as e:
        logger.error(f"❌ 투표허용 중 에러 발생: {e}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 오류가 발생했습니다.", ephemeral=True)
        except:
            pass


@bot.tree.command(name='세션초기화', description='[관리자 전용] 투표 세션을 강제로 초기화합니다')
async def reset_session(interaction: discord.Interaction) -> None:
    """세션 강제 초기화 명령어 (관리자 전용)"""
    try:
        # 관리자 권한 확인
        if not is_admin(interaction.user.name):
            await interaction.response.send_message("❌ 이 명령어는 관리자만 사용할 수 있습니다!", ephemeral=True)
            return

        guild_id = interaction.guild.id
        session = voting_manager.get_session(guild_id)

        if not session:
            await interaction.response.send_message("❌ 초기화할 세션이 없습니다!", ephemeral=True)
            return

        # 세션 강제 종료
        voting_manager.close_session(guild_id)

        await interaction.response.send_message(
            f"✅ 투표 세션이 강제로 초기화되었습니다!\n"
            f"제목: **{session.title}**",
            ephemeral=True
        )
        logger.warning(f"⚠️ 세션 강제 초기화: {session.title} (사용자: {interaction.user.name})")

    except Exception as e:
        logger.error(f"❌ 세션초기화 중 에러 발생: {e}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ 오류가 발생했습니다.", ephemeral=True)
        except:
            pass


# ==================== Eat Together Commands ====================

@bot.tree.command(name='같이먹자', description='같이 먹을 사람을 모집합니다')
@app_commands.describe(메뉴='먹을 메뉴 (예: 짜장면, 치킨, 피자)')
@handle_interaction_errors
async def eat_together(interaction: discord.Interaction, 메뉴: str) -> None:
    """같이먹자 명령어"""
    await interaction.response.defer()

    guild_id = interaction.guild.id
    channel_id = interaction.channel.id
    creator_id = interaction.user.id

    # 새 세션 생성
    session_id, session = eat_together_manager.create_session(
        guild_id,
        channel_id,
        creator_id,
        메뉴
    )

    logger.info(f"같이먹자 세션 생성: {메뉴} (생성자: {interaction.user.name}, session_id: {session_id})")

    # Embed 및 View 생성
    embed = create_eat_together_embed(session, interaction.guild)
    view = EatTogetherView(session_id, session, eat_together_manager)

    # 메시지 전송
    message = await interaction.followup.send(embed=embed, view=view, wait=True)
    session.message_id = message.id

    logger.info(f"같이먹자 메시지 전송 완료: {메뉴} (message_id: {message.id})")


# ==================== Bot Start ====================

if __name__ == "__main__":
    # 로깅 시스템 초기화
    setup_logging()

    token = os.environ.get('TOKEN')
    if not token:
        logger.error("❌ TOKEN 환경변수가 설정되지 않았습니다!")
    else:
        logger.info("봇 시작 중...")
        bot.run(token)
