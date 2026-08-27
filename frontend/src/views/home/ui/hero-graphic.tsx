/**
 * The product, drawn.
 *
 * The reference design puts a rendering of its own console beside the
 * headline. The equivalent here is the thing Aevrin actually hands you: a
 * scan that found something and admits what it could not check. Every value
 * below is a shape the real report produces, including the incomplete
 * coverage line, because a marketing graphic showing a flawless 100 would be
 * advertising the one result this product refuses to fake.
 *
 * Authored as inline SVG rather than an exported image so it stays sharp at
 * any size, weighs almost nothing, and needs no network.
 */

const SEVERITY = {
  critical: "#C7262B",
  high: "#D9622B",
  medium: "#C99A18",
  low: "#2F72C4",
} as const;

function FindingRow({
  y,
  colour,
  width,
  metaWidth,
}: {
  y: number;
  colour: string;
  width: number;
  metaWidth: number;
}) {
  return (
    <g>
      <rect x={28} y={y} width={3} height={26} rx={1.5} fill={colour} />
      <rect x={42} y={y + 3} width={width} height={7} rx={2} fill="#1B3139" opacity={0.82} />
      <rect x={42} y={y + 16} width={metaWidth} height={5} rx={2} fill="#1B3139" opacity={0.24} />
    </g>
  );
}

export function HeroGraphic() {
  return (
    <svg
      viewBox="0 0 520 430"
      className="h-auto w-full"
      role="img"
      aria-label="An Aevrin scan report showing a score of 62 out of 100, a severity breakdown, and a notice that two checks did not run"
    >
      <defs>
        <linearGradient id="mk-sheet" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#FAFAF8" />
        </linearGradient>
        <filter id="mk-lift" x="-14%" y="-14%" width="128%" height="132%">
          <feDropShadow dx="0" dy="14" stdDeviation="18" floodColor="#1B3139" floodOpacity="0.13" />
        </filter>
      </defs>

      {/* The report sheet */}
      <g filter="url(#mk-lift)">
        <rect x={16} y={14} width={440} height={362} rx={4} fill="url(#mk-sheet)" />

        {/* Masthead */}
        <text x={40} y={44} fontSize={9} letterSpacing="2.2" fill="#1B3139" opacity={0.5}>
          SECURITY REPORT
        </text>
        <rect x={40} y={54} width={214} height={9} rx={2} fill="#1B3139" opacity={0.78} />
        <line x1={40} y1={78} x2={432} y2={78} stroke="#1B3139" strokeOpacity={0.1} />

        {/* Verdict and score */}
        <text x={40} y={106} fontSize={17} fontWeight={500} fill="#1B3139">
          Critical issues need
        </text>
        <text x={40} y={127} fontSize={17} fontWeight={500} fill="#1B3139">
          attention before use
        </text>
        <text x={432} y={120} fontSize={40} fontWeight={500} textAnchor="end" fill={SEVERITY.high}>
          62
        </text>
        <text x={432} y={135} fontSize={8} letterSpacing="1.6" textAnchor="end" fill="#1B3139" opacity={0.45}>
          SCORE
        </text>

        {/* Severity distribution. Widths are the proportions of 1/1/2/1. */}
        <g>
          <rect x={40} y={152} width={78} height={5} rx={2.5} fill={SEVERITY.critical} />
          <rect x={120} y={152} width={78} height={5} rx={2.5} fill={SEVERITY.high} />
          <rect x={200} y={152} width={154} height={5} rx={2.5} fill={SEVERITY.medium} />
          <rect x={356} y={152} width={76} height={5} rx={2.5} fill={SEVERITY.low} />
        </g>
        <g fontSize={8} fill="#1B3139" opacity={0.62}>
          <circle cx={43} cy={172} r={3} fill={SEVERITY.critical} opacity={1} />
          <text x={51} y={175}>Critical 1</text>
          <circle cx={112} cy={172} r={3} fill={SEVERITY.high} opacity={1} />
          <text x={120} y={175}>High 1</text>
          <circle cx={172} cy={172} r={3} fill={SEVERITY.medium} opacity={1} />
          <text x={180} y={175}>Medium 2</text>
          <circle cx={247} cy={172} r={3} fill={SEVERITY.low} opacity={1} />
          <text x={255} y={175}>Low 1</text>
        </g>

        {/* The coverage admission, which is the point of the picture. */}
        <g>
          <rect x={40} y={192} width={2.5} height={38} fill={SEVERITY.high} />
          <text x={54} y={205} fontSize={9} fontWeight={500} fill={SEVERITY.high}>
            Secrets, Dependencies did not run
          </text>
          <rect x={54} y={213} width={330} height={5} rx={2} fill="#1B3139" opacity={0.22} />
          <rect x={54} y={222} width={248} height={5} rx={2} fill="#1B3139" opacity={0.22} />
        </g>

        {/* Findings */}
        <line x1={40} y1={250} x2={432} y2={250} stroke="#1B3139" strokeOpacity={0.1} />
        <text x={40} y={270} fontSize={11} fontWeight={500} fill="#1B3139">
          Findings
        </text>
        <g transform="translate(12, 0)">
          <FindingRow y={284} colour={SEVERITY.critical} width={196} metaWidth={252} />
          <FindingRow y={318} colour={SEVERITY.high} width={164} metaWidth={228} />
        </g>
      </g>

      {/* Trust grade, lifted off the sheet the way the reference floats its
          product tiles over the panel edge. */}
      <g filter="url(#mk-lift)">
        <rect x={372} y={318} width={132} height={92} rx={4} fill="#0B2026" />
        <text x={392} y={344} fontSize={8} letterSpacing="1.8" fill="#EDF2F8" opacity={0.55}>
          MCP TRUST
        </text>
        <text x={392} y={382} fontSize={34} fontWeight={500} fill="#FFFFFF">
          C
        </text>
        <text x={428} y={382} fontSize={11} fill="#EDF2F8" opacity={0.72}>
          Caution
        </text>
        <rect x={392} y={392} width={92} height={4} rx={2} fill="#EDF2F8" opacity={0.16} />
        <rect x={392} y={392} width={52} height={4} rx={2} fill="#5AA9F0" />
      </g>
    </svg>
  );
}
