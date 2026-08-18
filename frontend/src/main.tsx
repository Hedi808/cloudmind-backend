import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import axios from 'axios'
import './index.css'
import App from './App.tsx'

axios.defaults.withCredentials = true
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && !String(error?.config?.url ?? '').includes('/api/auth/')) {
      window.dispatchEvent(new Event('cloudmind:unauthorized'))
    }
    return Promise.reject(error)
  },
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
