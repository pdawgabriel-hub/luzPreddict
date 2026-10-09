import { Outlet } from 'react-router'
import { Footer } from './Footer'
import { Header } from './Header'
import styles from './Layout.module.css'
import { StaleDataBanner } from './StaleDataBanner'

export const MAIN_ID = 'contenido'

export function Layout() {
  return (
    <div className={styles.layout}>
      <a href={`#${MAIN_ID}`} className={styles.skipLink}>
        Saltar al contenido
      </a>
      <Header />
      <main id={MAIN_ID} tabIndex={-1} className={`container ${styles.main}`}>
        <StaleDataBanner />
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
