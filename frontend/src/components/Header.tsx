import { useEffect, useId, useState } from 'react'
import { NavLink, useLocation } from 'react-router'
import { ROUTES } from '../routes'
import styles from './Header.module.css'
import { Logo } from './Logo'

export function Header() {
  const menuId = useId()
  const { pathname } = useLocation()
  // Página en la que se abrió el menú del móvil: al ir a otra (enlace, atrás…) queda cerrado
  const [openOn, setOpenOn] = useState<string | null>(null)
  const open = openOn === pathname
  const setOpen = (value: boolean) => setOpenOn(value ? pathname : null)

  // Escape cierra el menú
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenOn(null)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <header className={styles.header}>
      <div className={`container ${styles.bar}`}>
        <Logo />
        <button
          type="button"
          className={styles.menuButton}
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => setOpen(!open)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
          Menú
        </button>
        <nav id={menuId} aria-label="Secciones" className={styles.nav} data-open={open}>
          <ul className={styles.links}>
            {ROUTES.map((route) => (
              <li key={route.path}>
                <NavLink to={route.path} end={route.path === '/'} className={styles.link}>
                  {route.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  )
}
