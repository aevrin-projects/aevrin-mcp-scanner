/** Account standing, shown wherever an admin sees a user: the list and the
 *  detail page read the same pill so a status never looks different
 *  depending on where you happened to be standing. */
export function StatusPill({ status }: { status: string }) {
  const tone =
    status === "active"
      ? "border-chart-1/40 bg-chart-1/10 text-chart-1"
      : status === "disabled"
        ? "border-severity-medium/40 bg-severity-medium/10 text-severity-medium"
        : "border-severity-critical/40 bg-severity-critical/10 text-severity-critical";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${tone}`}>
      {status}
    </span>
  );
}
