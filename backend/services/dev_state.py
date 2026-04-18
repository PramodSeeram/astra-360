ACTIVE_USER_ID = "demo_user_1"


def get_active_user_id() -> str:
    return ACTIVE_USER_ID


def set_active_user_id(user_id: str) -> str:
    global ACTIVE_USER_ID
    ACTIVE_USER_ID = user_id
    return ACTIVE_USER_ID
