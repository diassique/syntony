import { useEffect, useState } from 'react'
import Landing from './components/Landing'
import Dashboard from './components/Dashboard'

/** Tiny dependency-free hash router: '#/live' → dashboard, anything else → landing. */
function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash
}

export default function App() {
  const route = useHashRoute()
  return route.startsWith('#/live') ? <Dashboard /> : <Landing />
}
