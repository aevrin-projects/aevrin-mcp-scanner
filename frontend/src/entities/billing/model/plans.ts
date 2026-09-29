/** Team seat bounds, the same ones the API's CheckoutRequest enforces (and the
 *  admin panel's seat grant). Kept here so the pricing page and the billing
 *  page cannot offer a count the checkout would refuse. */
export const TEAM_MIN_SEATS = 3;
export const TEAM_MAX_SEATS = 500;

export function clampTeamSeats(value: number): number {
  if (!Number.isFinite(value)) return TEAM_MIN_SEATS;
  return Math.min(TEAM_MAX_SEATS, Math.max(TEAM_MIN_SEATS, Math.round(value)));
}

/** The pricing page, opened on Team with a seat count already chosen. */
export function teamPricingHref(seats: number): string {
  return `/pricing?seats=${clampTeamSeats(seats)}#plan-team`;
}
