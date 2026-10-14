import { Link } from 'react-router'
import styles from './Footer.module.css'

export const REE_URL = 'https://www.ree.es/es/apidatos'
export const REPO_URL = 'https://github.com/pdawgabriel-hub/luzPreddict'

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.inner}`}>
        <p>
          Datos: <a href={REE_URL}>Red Eléctrica (REE), apidatos.ree.es</a> · PVPC 2.0TD, término de energía. REE
          publica los precios de mañana hacia las 20:15.
        </p>
        <p>La previsión es orientativa: no es un precio oficial ni garantiza el precio final.</p>
        <p className={styles.meta}>
          <span>luzPreddict · proyecto de portfolio</span>
          <Link to="/desarrolladores">API pública</Link>
          <a href={REPO_URL}>Código en GitHub</a>
          <a href={`${REPO_URL}/blob/main/LICENSE.md`}>Licencia de portfolio</a>
        </p>
      </div>
    </footer>
  )
}
