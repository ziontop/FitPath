import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { Login } from './Login'
import { AuthProvider } from './AuthProvider'
import { ToastProvider } from '../components/ui'
import * as api from '../api'

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<div>Home screen</div>} />
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('Login form', () => {
  beforeEach(() => {
    // Bootstrapping auth check resolves as "guest".
    vi.spyOn(api.auth, 'me').mockRejectedValue(new api.ApiError(401, 'Not authenticated'))
  })

  it('renders the email/username and password fields', async () => {
    renderLogin()
    expect(await screen.findByRole('heading', { name: /welcome back/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/email or username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument()
  })

  it('submits the entered credentials to the auth API', async () => {
    const loginSpy = vi
      .spyOn(api.auth, 'login')
      .mockResolvedValue({ id: 1, email: 'z@fit.dev', username: 'zina', created_at: '2026-01-01T00:00:00' })

    renderLogin()
    await userEvent.type(screen.getByLabelText(/email or username/i), 'zina')
    await userEvent.type(screen.getByLabelText(/password/i), 'supersecret')
    await userEvent.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() =>
      expect(loginSpy).toHaveBeenCalledWith({ identifier: 'zina', password: 'supersecret' }),
    )
  })
})
