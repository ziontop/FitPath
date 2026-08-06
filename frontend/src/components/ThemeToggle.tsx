import { Sun, Moon } from 'lucide-react'
import { useTheme } from '../theme/useTheme'
import { IconButton } from './ui'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'
  return (
    <IconButton
      label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={toggle}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </IconButton>
  )
}
