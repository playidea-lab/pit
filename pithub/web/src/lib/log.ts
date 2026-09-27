/**
 * 서버 로그 한 줄 (JSON) — Fly 로그에서 찾을 수 있게. 저장된 글이나 토큰은 넣지 않는다: 어디서, 무슨 오류인지만.
 */
export function logServerError(where: string, error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  // 웹에는 따로 로거가 없어 표준 오류 출력이 곧 서버 로그다
  console.error(JSON.stringify({ level: "ERROR", where, message }));
}
