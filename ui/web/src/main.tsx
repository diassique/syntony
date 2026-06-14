import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'  // self-hosted fonts are @import-ed at the top of index.css
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
