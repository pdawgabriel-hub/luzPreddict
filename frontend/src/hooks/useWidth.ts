import { useCallback, useState } from 'react'

/**
 * Ancho real de un elemento, que se actualiza al cambiar el tamaño de la ventana.
 * Los gráficos lo usan para dibujar a su tamaño (sin escalar el texto).
 * Sin ResizeObserver (tests con jsdom) se queda en `fallback`.
 */
export function useWidth<T extends HTMLElement>(fallback = 640): [(node: T | null) => void, number] {
  const [width, setWidth] = useState(fallback)

  const ref = useCallback(
    (node: T | null) => {
      if (!node || typeof ResizeObserver === 'undefined') return
      const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width) || fallback))
      observer.observe(node)
      return () => observer.disconnect()
    },
    [fallback],
  )
  return [ref, width]
}
