import { useEffect } from 'react'
import { documentTitle } from '../routes'

/** Título de la pestaña del navegador para la página actual. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = documentTitle(title)
  }, [title])
}
