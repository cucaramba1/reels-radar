

def test_is_limit_matches_real_messages_only():
    from reels_radar.claude import is_limit
    real = ["claude: You've hit your session limit · resets 8:10pm (Asia/Saigon)",
            "claude: You've hit your weekly limit · resets Oct 21 at 1pm (Asia/Saigon)",
            "claude: You've hit your usage limit", "usage limit reached", "you have reached your weekly usage limit",
            "usage credit limit reached", "Fable limit reached", "не смог запустить claude: No such file"]
    noise = ["claude: Context limit reached", "claude exit 1: Usage: claude [options] [command]",
             "claude не ответил за 600 с", "claude вернул не JSON", "claude: rate limited, overloaded"]
    assert all(is_limit(Exception(t)) for t in real)
    assert not any(is_limit(Exception(t)) for t in noise)
