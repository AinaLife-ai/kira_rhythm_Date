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


def test_prepare_payload_compacts_noise():
    from krd.llm_format import prepare_llm_payload

    payload = {
        'persona_id': 'aina',
        'timezone': 'Asia/Shanghai',
        'holiday': None,
        'solar_term': None,
        'source': 'internal',
        'next': None,
        'title': '随意走走',
    }
    cleaned = prepare_llm_payload(payload, 'Asia/Shanghai', 'Asia/Shanghai', drop=('source',))
    assert cleaned == {'title': '随意走走'}

    cleaned = prepare_llm_payload(
        {'timezone': 'Asia/Tokyo', 'title': 'x'}, 'Asia/Tokyo', 'Asia/Shanghai'
    )
    assert cleaned == {'timezone': 'Asia/Tokyo', 'title': 'x'}


def test_humanize_schedule_seconds_when_nonzero():
    ts = datetime(2026, 11, 15, 10, 36, 17, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
    cleaned = humanize_timestamps({'scheduled_at': ts}, 'Asia/Shanghai')
    assert cleaned['scheduled_at'] == '2026-11-15 10:36:17'
