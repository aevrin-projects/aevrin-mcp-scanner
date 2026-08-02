export function verdict(score: number): string {
  if (score >= 90) return "Clean — no significant issues found";
  if (score >= 70) return "Minor issues — review recommended";
  if (score >= 40) return "Significant risk — do not deploy as-is";
  return "Critical risk — do not use this server";
}

export function verdictTone(score: number): "good" | "warn" | "bad" {
  if (score >= 90) return "good";
  if (score >= 40) return "warn";
  return "bad";
}
