/** Tiny className joiner — drops falsy values and joins with spaces.
 *  Dependency-free stand-in for clsx (the frontend ships no runtime deps). */
export type ClassValue = string | false | null | undefined

export function cx(...parts: ClassValue[]): string {
  return parts.filter(Boolean).join(' ')
}
