import { useEffect, useState } from 'react'

// The value, but only once it has stopped changing for `delay` ms. Keeps a
// search box from firing a request per keystroke.
export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
