import Link from "next/link";

import GraphSketch from "@/components/home/GraphSketch";

/** 첫 방문자용 소개 — 스크린샷 대신 글과 그림으로 두어 실제 화면과 어긋날 일이 없다 */

const STEPS = [
  ["평소처럼 일하다 판단한다", "AI의 제안을 거부하거나 고치거나 고르는 순간, AI가 그 판단을 한 줄로 기록합니다. 대화 원문은 나가지 않습니다."],
  ["팀의 판단 그래프가 된다", "판단은 주제·파일에 매달리고 서로 이어집니다. 3일 동안은 내 것이고, 그 뒤 팀에 보입니다."],
  ["동료의 AI가 먼저 찾아본다", "제안하기 전에 팀의 판단을 봅니다. “○○이라면?”에는 트윈이 근거와 함께 답하고, 모르면 본인에게 묻습니다."],
] as const;

const SCENES = [
  { when: "오늘, 내 세션", lines: [["AI", "평가를 무작위 분할로 하겠습니다."], ["나", "아니, 시간 분할로 해. 미래가 새."], ["", "· pithub 기록됨 — 거부 · 평가 분할"]] },
  { when: "다음 주, 동료의 세션", lines: [["AI", "평가 분할을 정하기 전에 팀 기록을 봤습니다."], ["AI", "지난주 무작위 분할이 기각됐습니다 — 시간 분할로 갑니다."], ["동료", "ㅇㅇ"]] },
] as const;

const TOOLS = [
  ["Claude Code", "명령 한 줄로 연결, 기록 훅까지 한 줄"],
  ["Codex", "같은 주소, 같은 훅"],
  ["claude.ai", "커스텀 커넥터 + 개인 선호 사항 한 문장"],
  ["그 밖의 MCP 도구", "같은 주소 + 전역 지침 한 문장"],
] as const;

const POINTS = [
  ["원문은 나가지 않습니다", "대화 자체는 저장하지 않습니다. 결정 한 건의 요약과 당신의 말 한 줄만 받습니다."],
  ["회사 밖으로 나가지 않습니다", "공개 기능이 없습니다. 판단은 회사 팀 안에서만 보입니다."],
  ["3일 동안은 당신 것입니다", "기록된 판단은 3일 뒤 팀에 보입니다. 그 전에 정리함에서 빼거나 고칠 수 있습니다."],
  ["팀에 보인 뒤에는 회사의 기록입니다", "퇴사해도 남아 후임에게 답합니다. 지울 수 있는 것은 팀 소유자뿐입니다."],
] as const;

const FAQ = [
  ["AI가 대화를 전부 올리나요?", "아니요. AI가 판단이라고 본 순간에 요약과 당신의 말 한 줄만 보냅니다. 비밀번호·키 같은 값은 서버가 받자마자 가립니다."],
  ["잘못 기록되면요?", "정리함에서 고치거나 버리면 됩니다. 팀에 보이기 전 3일 동안은 흔적 없이 지울 수 있습니다."],
  ["트윈이 나 대신 결정하나요?", "아니요. 트윈은 예측과 근거만 말하고, 확신이 없으면 답하지 않고 당신에게 질문을 넘깁니다."],
  ["토큰이 많이 드나요?", "기록과 검색은 짧은 요약만 오갑니다. 설정 화면에서 도구별 호출 수와 실제로 읽힌 비율을 볼 수 있습니다."],
] as const;

function Section({ title, children, id }: { title: string; children: React.ReactNode; id?: string }) {
  return (
    <div id={id} className="scroll-mt-20">
      <h2 className="mb-5 text-[15px] font-semibold text-ink">{title}</h2>
      {children}
    </div>
  );
}

export default function Landing({ signedIn }: { signedIn: boolean }) {
  return (
    <div className="space-y-20">
      <div className="grid items-center gap-10 pt-6 sm:grid-cols-[1.3fr_1fr]">
        <div>
          <p className="label mb-4">팀 판단 그래프</p>
          <h1 className="mb-5 text-[34px] font-semibold leading-[1.15] tracking-tight text-ink sm:text-[42px]">
            팀이 AI와 내린 판단을
            <br />
            <span className="text-accent">회사의 기억으로</span>
          </h1>
          <p className="muted mb-7 max-w-xl text-[16px] leading-relaxed sm:text-[17px]">
            구성원이 AI의 제안을 거부하고 고치고 방향을 정한 순간이 팀의 판단 그래프로 쌓입니다. 동료의 AI는 그 판단을 먼저
            찾아보고, 기획자는 개발자를 부르지 않고 &ldquo;왜&rdquo;를 압니다. 사람이 떠나도 판단은 남습니다.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href={signedIn ? "/connect" : "/login"} className="btn btn-primary h-10 px-5">
              {signedIn ? "도구 연결하기" : "시작하기"}
            </Link>
            <a href="#how" className="btn btn-secondary h-10 px-5">
              어떻게 동작하나
            </a>
          </div>
        </div>
        <div className="card flex justify-center">
          <GraphSketch />
        </div>
      </div>

      <Section title="어떻게 동작하나" id="how">
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="card">
              <span className="mb-3 flex h-7 w-7 items-center justify-center rounded-full bg-[var(--accent-soft)] text-sm font-semibold text-accent">
                {i + 1}
              </span>
              <p className="mb-1.5 font-medium text-ink">{title}</p>
              <p className="muted text-sm leading-relaxed">{body}</p>
            </li>
          ))}
        </ol>
      </Section>

      <div className="grid gap-4 sm:grid-cols-2">
        {SCENES.map((scene) => (
          <div key={scene.when} className="code">
            <p className="mb-3 text-xs opacity-60">{scene.when}</p>
            {scene.lines.map(([who, text], i) => (
              <p key={i} className={who ? "mb-1.5" : "mt-3 text-xs opacity-60"}>
                {who && <span className="mr-2 opacity-60">{who}</span>}
                {text}
              </p>
            ))}
          </div>
        ))}
      </div>

      <Section title="쓰는 AI 그대로">
        <div className="grid gap-3 sm:grid-cols-4">
          {TOOLS.map(([name, how]) => (
            <div key={name} className="card">
              <p className="mb-1 font-medium text-ink">{name}</p>
              <p className="muted text-xs leading-relaxed">{how}</p>
            </div>
          ))}
        </div>
        <p className="muted mt-3 text-sm">
          주소 하나를 붙이면 끝입니다. 도구별 방법은{" "}
          <Link href="/connect" className="link">
            연결하기
          </Link>
          에 있습니다.
        </p>
      </Section>

      <Section title="경계">
        <ul className="grid gap-8 sm:grid-cols-2">
          {POINTS.map(([title, body]) => (
            <li key={title}>
              <p className="mb-1.5 font-medium text-ink">{title}</p>
              <p className="muted text-sm leading-relaxed">{body}</p>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="자주 묻는 것">
        <div className="card divide-y divide-border py-1">
          {FAQ.map(([q, a]) => (
            <details key={q} className="py-3">
              <summary className="cursor-pointer text-sm text-ink">{q}</summary>
              <p className="muted mt-2 text-sm leading-relaxed">{a}</p>
            </details>
          ))}
        </div>
      </Section>

      <p className="faint text-xs">
        오픈소스(AGPL-3.0) —{" "}
        <a href="https://github.com/playidea-lab/pit" className="link">
          github.com/playidea-lab/pit
        </a>
        . 회사 서버에 직접 설치할 수도 있습니다.
      </p>
    </div>
  );
}
