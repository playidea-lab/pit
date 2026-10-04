from datetime import date, datetime
from zoneinfo import ZoneInfo

from git_watcher import monthly_due
from git_watcher.calendar_kr import first_workday, is_workday
from git_watcher.config import Settings
from git_watcher.monthly import DayActivity, PersonMonth, mean_clock, summary_cells

KST = ZoneInfo("Asia/Seoul")


def make_settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("GITLAB_URL", "http://localhost")
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    return Settings(_env_file=None, state_dir=tmp_path)


def test_is_workday_excludes_chuseok_and_weekend() -> None:
    assert not is_workday(date(2026, 9, 25))  # 추석
    assert not is_workday(date(2026, 9, 27))  # 일요일
    assert is_workday(date(2026, 9, 30))


def test_first_workday_skips_substitute_holiday() -> None:
    # 2027-01-01 금(신정) → 첫 근무일은 1/4 월
    assert first_workday(2027, 1) == date(2027, 1, 4)


def test_monthly_due_on_first_workday_until_sent(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path, monkeypatch)
    assert monthly_due(settings, date(2026, 10, 2)) == (2026, 9)
    (tmp_path / "monthly_sent").write_text("2026-09")
    assert monthly_due(settings, date(2026, 10, 2)) is None


def test_monthly_due_skips_non_workday(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path, monkeypatch)
    assert monthly_due(settings, date(2026, 10, 3)) is None  # 개천절(토)


def test_summary_averages_only_active_workdays() -> None:
    person = PersonMonth("alice", "앨리스")
    for day, first, last in [(29, 9, 18), (30, 11, 19)]:
        act = person.days[date(2026, 9, day)]
        act.touch(datetime(2026, 9, day, first, 0, tzinfo=KST))
        act.touch(datetime(2026, 9, day, last, 0, tzinfo=KST))
    # 일요일 활동은 평균에서 빠지고 휴일 활동일로만 센다
    person.days[date(2026, 9, 27)].touch(datetime(2026, 9, 27, 3, 0, tzinfo=KST))
    row = summary_cells(person, workday_total=20)
    assert row["활동한 근무일"] == "2 / 20"
    assert row["휴일 활동일"] == 1
    assert row["평균 첫 활동"] == "10:00"
    assert row["평균 활동 폭(시간)"] == 8.5


def test_day_activity_without_events_has_no_span() -> None:
    assert DayActivity().span_hours is None
    assert mean_clock([]) == "-"


def test_estimate_cell_sums_days_against_workday_capacity() -> None:
    from git_watcher.monthly import estimate_cell
    person = PersonMonth("alice", "앨리스")
    for day, low, high in [(29, 4, 6), (27, 2, 3)]:  # 일요일 작업도 합계에 들어간다
        act = person.days[date(2026, 9, day)]
        act.hours_low, act.hours_high = low, high
    assert estimate_cell(person, workday_total=2) == "6~9시간 (38%~56%)"
    assert estimate_cell(PersonMonth("bob", "밥"), workday_total=2) == "-"


def test_evaluation_due_tracked_separately_from_monthly(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path, monkeypatch)
    (tmp_path / "monthly_sent").write_text("2026-09")
    # 월간 리포트를 보냈어도 평가는 아직이면 보낼 차례다
    assert monthly_due(settings, date(2026, 10, 2), "evaluation_sent") == (2026, 9)
