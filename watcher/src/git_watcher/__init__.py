"""매일 저녁 GitLab 커밋을 계정별로 요약해 메일로 보내는 브리퍼."""

import argparse
import logging
import shutil
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from git_watcher import backfill, evaluate_report, sources, telemetry, work_reports
from git_watcher.calendar_kr import first_workday, is_workday, previous_month
from git_watcher.config import Settings
from git_watcher.gitlab import Account, GitLabClient, split_by_day
from git_watcher.identity import build_index
from git_watcher.mailer import send_mail
from git_watcher.monthly_report import build_monthly, to_html, to_text, write_xlsx
from git_watcher.people import load_github_logins, load_people
from git_watcher.report import Briefing, Day, Row
from git_watcher.summarize import Summarizer, fallback_assessment

logger = logging.getLogger("git_watcher")

LAST_RUN_FILE = "last_run"
# 마지막으로 보낸 월간 리포트의 달 (YYYY-MM)
MONTHLY_SENT_FILE = "monthly_sent"
# 마지막으로 보낸 평가의 달 (YYYY-MM). 월간 리포트와 따로 기록해 한쪽 실패가 다른 쪽을 막지 않게 한다
EVAL_SENT_FILE = "evaluation_sent"
REPORTS_DIR = "reports"


def read_last_run(state_dir: Path) -> datetime | None:
    path = state_dir / LAST_RUN_FILE
    if not path.exists():
        return None
    return datetime.fromisoformat(path.read_text().strip())


def write_last_run(state_dir: Path, until: datetime) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / LAST_RUN_FILE).write_text(until.isoformat())


def resolve_window(
    settings: Settings, now: datetime, last_run: datetime | None, hours: int | None
) -> tuple[datetime, datetime]:
    """지난 성공 실행 시점부터 지금까지. Mac이 잠들어 하루를 건너뛰어도 빈틈이 없도록 한다."""
    if hours is not None:
        return now - timedelta(hours=hours), now
    since = last_run or now - timedelta(hours=settings.default_lookback_hours)
    earliest = now - timedelta(days=settings.max_lookback_days)
    return max(since, earliest), now


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="git-watcher")
    parser.add_argument("--dry-run", action="store_true", help="메일을 보내지 않고 본문만 출력")
    parser.add_argument("--no-llm", action="store_true", help="Claude 요약 없이 커밋 제목만 나열")
    parser.add_argument("--hours", type=int, help="상태 파일 대신 최근 N시간을 본다")
    parser.add_argument("--monthly", metavar="YYYY-MM", help="해당 달의 월간 리포트만 만든다(보낸다)")
    parser.add_argument("--evaluate", metavar="YYYY-MM", help="해당 달의 작업 방식 평가 (EVAL_MAIL_TO로 발송)")
    parser.add_argument("--collector", action="store_true", help="에이전트 텔레메트리 수집기를 띄운다")
    parser.add_argument("--backfill", metavar="JSONL", help="Claude Code 대화 기록을 요약 이벤트로 소급 기록")
    parser.add_argument("--who", help="--backfill 때 기록할 계정 (예: 이메일)")
    parser.add_argument("--work-reports", action="store_true", help="pithub 작업 보고를 커밋과 대조해 출력 (--hours 기간)")
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="그날 정기 보고를 재현한다 (전날~그날 보고 시각)")
    return parser.parse_args(argv)


def make_summarizer(settings: Settings) -> Summarizer:
    claude_bin = shutil.which(settings.claude_bin)
    if claude_bin is None:
        raise SystemExit(f"claude CLI를 찾을 수 없습니다: {settings.claude_bin} (CLAUDE_BIN 설정 또는 --no-llm)")
    return Summarizer(claude_bin, settings.claude_model)


def build_rows(
    users: list[dict], accounts: dict[str, Account], summarizer: Summarizer | None, full_roster: bool
) -> list[Row]:
    """작업한 사람은 작업량 순으로. full_roster면 커밋 없는 사람도 이름 순으로 붙인다."""
    names, exclude = load_people()
    active = []
    for key, account in accounts.items():
        if key in exclude:
            continue
        assessment = summarizer.assess(account) if summarizer else fallback_assessment(account)
        active.append(Row(names.get(key, account.display), account, assessment))
    # 추정 시간이 긴 순, 추정이 없으면 맨 뒤
    active.sort(key=lambda r: (-(r.ratio or -1), -len(r.account.commits)))
    if not full_roster:
        return active
    idle = [Row(names.get(u["username"], u["name"])) for u in users
            if u["username"] not in accounts and u["username"] not in exclude]
    return active + sorted(idle, key=lambda r: r.name)


def build_briefing(settings: Settings, since: datetime, until: datetime, use_llm: bool) -> Briefing:
    """보고일(until 날짜)은 전원을, 그 이전 날짜(주말·전날 저녁)는 커밋한 사람만 싣는다."""
    with GitLabClient(settings.gitlab_url, settings.gitlab_token.get_secret_value()) as gl:
        users = gl.human_users()
        index = build_index(gl, users, since, settings.state_dir)
        accounts = sources.collect_all(settings, gl, since, until, index)
    summarizer = make_summarizer(settings) if use_llm else None
    by_day = split_by_day(accounts, until.tzinfo)
    by_day.setdefault(until.date(), {})
    days = []
    for day in sorted(by_day):
        rows = build_rows(users, by_day[day], summarizer, full_roster=(day == until.date()))
        if rows:
            days.append(Day(day, rows))
    return Briefing(since=since, until=until, days=days)


def run_work_reports(settings: Settings, now: datetime, hours: int, use_llm: bool) -> None:
    if not (settings.pithub_url and settings.pithub_service_key):
        raise SystemExit("PITHUB_URL 과 PITHUB_SERVICE_KEY 가 필요합니다.")
    since = now - timedelta(hours=hours)
    with GitLabClient(settings.gitlab_url, settings.gitlab_token.get_secret_value()) as gl:
        index = build_index(gl, gl.human_users(), since, settings.state_dir)
        accounts = sources.collect_all(settings, gl, since, now, index)
    with work_reports.PithubClient(settings.pithub_url, settings.pithub_service_key.get_secret_value()) as ph:
        reports = ph.reports(since, now)
        logins = ph.logins(sorted({r["owner_github_id"] for r in reports}))
        github_map = load_github_logins()
        who_of = {gid: github_map.get(login.lower(), f"github:{login}") for gid, login in logins.items()}
        people = work_reports.verify(accounts, reports, who_of, make_summarizer(settings) if use_llm else None)
        ids = sorted({i for r in reports for i in (r.get("implements") or [])})
        groups = work_reports.by_decision(people, ph.decision_titles(ids))
    names, _ = load_people()
    sys.stdout.write(work_reports.render_text(people, groups, names) + "\n")


def run_evaluate(settings: Settings, year: int, month: int, dry_run: bool) -> None:
    label = f"{year}-{month:02d}"
    people = evaluate_report.build_evaluation(settings, year, month)
    xlsx = evaluate_report.write_xlsx(people, label, settings.state_dir / REPORTS_DIR)
    logger.info("평가 엑셀 저장: %s", xlsx)
    if dry_run:
        sys.stdout.write(evaluate_report.to_text(people, label) + "\n")
        return
    if not settings.eval_mail_to:
        raise SystemExit("EVAL_MAIL_TO가 비어 있어 평가 메일을 보내지 않습니다.")
    recipients = settings.model_copy(update={"mail_to": settings.eval_mail_to})
    subject = f"[작업 방식 평가 v1] {label} — 대외비"
    send_mail(recipients, subject, evaluate_report.to_text(people, label),
              evaluate_report.to_html(people, label), (xlsx,))
    (settings.state_dir / EVAL_SENT_FILE).write_text(label)
    logger.info("평가 발송 완료: %s", ", ".join(settings.eval_mail_to))


def run_monthly(settings: Settings, year: int, month: int, dry_run: bool, use_llm: bool) -> None:
    report = build_monthly(settings, year, month, make_summarizer(settings) if use_llm else None)
    xlsx = write_xlsx(report, settings.state_dir / REPORTS_DIR)
    logger.info("월간 엑셀 저장: %s", xlsx)
    if dry_run:
        sys.stdout.write(f"{report.subject}\n\n{to_text(report)}\n")
        return
    send_mail(settings, report.subject, to_text(report), to_html(report), (xlsx,))
    (settings.state_dir / MONTHLY_SENT_FILE).write_text(f"{year}-{month:02d}")
    logger.info("월간 리포트 발송 완료: %s", ", ".join(settings.mail_to))


def monthly_due(settings: Settings, today: date, sent_name: str = MONTHLY_SENT_FILE) -> tuple[int, int] | None:
    """이번 달 첫 근무일 이후의 근무일이고 지난달 것을 아직 안 보냈으면 그 달을 돌려준다."""
    if not is_workday(today) or today < first_workday(today.year, today.month):
        return None
    year, month = previous_month(today)
    sent_file = settings.state_dir / sent_name
    sent = sent_file.read_text().strip() if sent_file.exists() else ""
    return None if sent == f"{year}-{month:02d}" else (year, month)


def daily_window(settings: Settings, args: argparse.Namespace, now: datetime) -> tuple[datetime, datetime]:
    if args.date:
        # 그날 보고 시각까지 24시간 — 정기 발송이 그날 냈을 메일과 같은 기간
        until = datetime.combine(date.fromisoformat(args.date), time(settings.report_hour), now.tzinfo)
        return until - timedelta(days=1), until
    last_run = None if args.hours else read_last_run(settings.state_dir)
    return resolve_window(settings, now, last_run, args.hours)


def run_daily(settings: Settings, args: argparse.Namespace, now: datetime) -> None:
    since, until = daily_window(settings, args, now)
    logger.info("브리핑 기간: %s ~ %s", since.isoformat(), until.isoformat())
    briefing = build_briefing(settings, since.astimezone(now.tzinfo), until, use_llm=not args.no_llm)
    if args.dry_run:
        sys.stdout.write(f"{briefing.subject}\n\n{briefing.to_text()}\n")
        return
    send_mail(settings, briefing.subject, briefing.to_text(), briefing.to_html())
    # 메일 발송까지 성공했을 때만 다음 기간의 시작점을 옮긴다
    if args.hours is None and args.date is None:
        write_last_run(settings.state_dir, until)
    logger.info("발송 완료: %s", ", ".join(settings.mail_to))


def run(argv: list[str]) -> None:
    args = parse_args(argv)
    settings = Settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    if args.work_reports:
        run_work_reports(settings, now, args.hours or settings.default_lookback_hours, use_llm=not args.no_llm)
        return
    if args.backfill:
        who = args.who or settings.backfill_who
        if not who:
            raise SystemExit("--backfill 에는 --who 또는 .env 의 BACKFILL_WHO 가 필요합니다.")
        out = backfill.backfill(Path(args.backfill).expanduser(), who, settings.state_dir / "telemetry" / "backfill")
        logger.info("소급 기록: %s", out)
        return
    if args.collector:
        telemetry.serve(settings.telemetry_host, settings.telemetry_port, settings.state_dir / "telemetry")
        return
    if args.evaluate:
        year, month = (int(x) for x in args.evaluate.split("-"))
        run_evaluate(settings, year, month, args.dry_run)
        return
    if args.monthly:
        year, month = (int(x) for x in args.monthly.split("-"))
        run_monthly(settings, year, month, args.dry_run, use_llm=not args.no_llm)
        return
    run_daily(settings, args, now)
    # 정기 실행일 때만 월초 리포트를 확인한다 (수동 --hours·--dry-run 실행은 제외)
    if args.hours or args.date or args.dry_run:
        return
    due = monthly_due(settings, now.date())
    if due:
        run_monthly(settings, *due, dry_run=False, use_llm=not args.no_llm)
    eval_due = monthly_due(settings, now.date(), EVAL_SENT_FILE)
    if eval_due:
        run_evaluate(settings, *eval_due, dry_run=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # 요청마다 찍히는 httpx 로그는 launchd 로그를 덮어버린다
    logging.getLogger("httpx").setLevel(logging.WARNING)
    run(sys.argv[1:])
