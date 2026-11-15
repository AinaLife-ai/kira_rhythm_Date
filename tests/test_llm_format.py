from datetime import datetime
from zoneinfo import ZoneInfo

from krd.llm_format import humanize_timestamps


def test_humanize_nested_timestamps():
    ts = datetime(2026, 11, 15, 10, 36, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
    payload = {
        'scheduled_at': ts,
        'nested': [{'created_at': ts, 'title': '随意走走'}],
        'timezone': 'Asia/Shanghai',
    }
    cleaned = humanize_timestamps(payload, 'Asia/Shanghai')
    assert cleaned['scheduled_at'] == '2026-11-15 10:36'
    assert cleaned['nested'][0]['created_at'] == '2026-11-15 10:36'
    assert cleaned['nested'][0]['title'] == '随意走走'
    assert isinstance(payload['scheduled_at'], float)
