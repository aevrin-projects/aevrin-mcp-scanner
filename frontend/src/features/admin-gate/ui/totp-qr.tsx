"use client";

import { useMemo } from "react";
import qrcode from "qrcode-generator";

/**
 * The otpauth:// URI as a scannable QR code.
 *
 * Enrolment previously offered only the base32 setup key and the URI as a
 * link. The link is inert on desktop, where nothing registers an otpauth://
 * handler, so the only working path was hand-typing a 32-character secret
 * into a phone. Every authenticator app scans instead.
 *
 * Rendered as inline SVG rather than a canvas or an <img> data URI: it stays
 * crisp at any size, needs no ref or effect, and works with JavaScript doing
 * nothing after hydration.
 */
export function TotpQr({ uri, size = 176 }: { uri: string; size?: number }) {
  const { path, cells } = useMemo(() => {
    // Type 0 = pick the smallest version that fits. "M" is the level every
    // authenticator expects, and leaves room for the label and issuer.
    const qr = qrcode(0, "M");
    qr.addData(uri);
    qr.make();

    const count = qr.getModuleCount();
    // One <path> of rects beats thousands of elements: an otpauth URI is
    // long enough that a per-module <rect> tree is noticeably slow to paint.
    let d = "";
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) {
        if (qr.isDark(row, col)) d += `M${col} ${row}h1v1h-1z`;
      }
    }
    return { path: d, cells: count };
  }, [uri]);

  return (
    <svg
      // The quiet zone is part of the spec; scanners get unreliable without
      // it, and the white plate has to extend through it.
      viewBox={`-2 -2 ${cells + 4} ${cells + 4}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
      role="img"
      aria-label="QR code for two-factor enrolment"
      className="rounded-lg"
    >
      {/* Fixed black-on-white regardless of theme. A QR inverted for dark
          mode fails on a good share of scanners, which assume dark modules
          on a light field. */}
      <rect x={-2} y={-2} width={cells + 4} height={cells + 4} fill="#ffffff" />
      <path d={path} fill="#000000" />
    </svg>
  );
}
