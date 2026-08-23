/** Date and duration formatting shared by every surface. Kept in `shared`
 *  rather than an entity because none of it knows what it is formatting. */

const DATE: Intl.DateTimeFormatOptions = { month: "short", day: "numeric", year: "numeric" };

export function formatDate(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-US", DATE).format(new Date(value));
}

export function formatDateTime(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-US", {
    ...DATE,
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDuration(start: string, end: string | null) {
  const totalSeconds = Math.max(
    0,
    Math.round((new Date(end ?? Date.now()).getTime() - new Date(start).getTime()) / 1000),
  );
  if (totalSeconds < 60) return `${totalSeconds}s`;

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;

  const remainingMinutes = minutes % 60;
  const hours = Math.floor(minutes / 60);
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}
