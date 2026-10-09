import { Link } from 'react-router'
import styles from './Header.module.css'

export function Logo() {
  return (
    <Link to="/" className={styles.logo} aria-label="luzPreddict, ir al panel">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--color-brand)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" />
      </svg>
      <span className={styles.logoText}>luzPreddict</span>
    </Link>
  )
}
