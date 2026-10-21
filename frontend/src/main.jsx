import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { getBridge } from './session'

// Install the parent-session listener before the first render, so that a
// session pushed by the landing page cannot be missed in the window
// between the frame loading and the application mounting.
getBridge().install();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
