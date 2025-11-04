"""
메뉴 투표 시스템 권한 관리

주요 기능:
- 관리자 권한 확인
"""


def is_admin(username: str) -> bool:
    """
    관리자 여부 확인

    Args:
        username: Discord 사용자 이름

    Returns:
        관리자면 True
    """
    # TODO: 향후 설정 파일이나 DB로 관리 고려
    ADMIN_USERS = {"revdoor"}
    return username in ADMIN_USERS
