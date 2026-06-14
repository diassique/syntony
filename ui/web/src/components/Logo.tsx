/** Brand wordmark — the designed Syntony logo (symbol + "Syntony"), served from /public.
 *  Rendered as an <img> so it stays pixel-faithful to the source SVG. Sized by height;
 *  width follows the artwork's aspect ratio. The asset is ink-coloured to match the system. */
export function Wordmark({ height = 22, className = '' }: { height?: number; className?: string }) {
  return (
    <img
      src="/syntony-logo.svg"
      alt="Syntony"
      style={{ height, width: 'auto' }}
      className={className}
      draggable={false}
    />
  )
}
