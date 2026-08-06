/**
 * FitPath "Ridgeline" brand mark: a rising ridge line (ascending trend)
 * rendered in white inside the indigo brand tile. No orange.
 */
export function Logo({ size = 32 }: { size?: number }) {
  const glyph = Math.round(size * 0.62)
  return (
    <span className="brand">
      <span className="brand__mark" style={{ width: size, height: size }} aria-hidden="true">
        <svg
          width={glyph}
          height={glyph}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 17.5 L8.5 8 L12.5 13.5 L16 6.5 L21 12.5" />
          <path d="M3 20.5 L21 20.5" opacity="0.5" />
        </svg>
      </span>
      <span>
        Fit<span className="brand__accent">Path</span>
      </span>
    </span>
  )
}
