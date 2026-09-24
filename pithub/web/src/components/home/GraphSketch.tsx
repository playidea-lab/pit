/** 판단(점) → 주제(원) → 동료의 AI — 첫 방문자에게 "그래프"를 한 장으로. 색은 디자인 토큰을 따른다. */
const DECISIONS = [
  { x: 40, y: 40, verdict: "reject" },
  { x: 40, y: 110, verdict: "approve" },
  { x: 40, y: 180, verdict: "modify" },
] as const;
const TOPICS = [
  { x: 190, y: 70, label: "평가 분할" },
  { x: 190, y: 160, label: "배포" },
] as const;
const VERDICT_FILL = { reject: "var(--reject-fg)", approve: "var(--approve-fg)", modify: "var(--modify-fg)" } as const;

export default function GraphSketch() {
  return (
    <svg viewBox="0 0 330 220" className="h-auto w-full max-w-sm" role="img" aria-label="판단이 주제에 매달리고 동료의 AI가 그 주제로 찾아오는 그림">
      <g stroke="var(--border-strong)" strokeWidth="1.5">
        <line x1="48" y1="40" x2="170" y2="70" />
        <line x1="48" y1="110" x2="170" y2="70" />
        <line x1="48" y1="110" x2="170" y2="160" />
        <line x1="48" y1="180" x2="170" y2="160" />
        <line x1="210" y1="70" x2="282" y2="112" strokeDasharray="4 4" />
        <line x1="210" y1="160" x2="282" y2="118" strokeDasharray="4 4" />
      </g>
      {DECISIONS.map((d) => (
        <circle key={`${d.x}-${d.y}`} cx={d.x} cy={d.y} r="8" fill={VERDICT_FILL[d.verdict]} />
      ))}
      {TOPICS.map((t) => (
        <g key={t.label}>
          <circle cx={t.x} cy={t.y} r="20" fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth="1.5" />
          <text x={t.x} y={t.y + 38} textAnchor="middle" fontSize="12" fill="var(--text-muted)">
            {t.label}
          </text>
        </g>
      ))}
      <rect x="276" y="98" width="46" height="34" rx="8" fill="var(--ink)" />
      <text x="299" y="120" textAnchor="middle" fontSize="12" fill="#fff">
        AI
      </text>
      <text x="40" y="212" textAnchor="middle" fontSize="11" fill="var(--text-faint)">
        판단
      </text>
      <text x="299" y="150" textAnchor="middle" fontSize="11" fill="var(--text-faint)">
        동료
      </text>
    </svg>
  );
}
