import { type RefObject, useEffect, useRef } from 'react'

// On a phone the tab strip can be wider than the screen; a tab opened from a
// link or a reload must not sit off to the side.
export function useSelectedTabInView(tab: string, ready: boolean): RefObject<HTMLDivElement | null> {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [tab, ready])
  return ref
}
