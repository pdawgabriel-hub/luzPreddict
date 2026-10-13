import { act, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useWidth } from './useWidth'

function Probe() {
  const [ref, width] = useWidth<HTMLDivElement>(320)
  return <div ref={ref}>{width}</div>
}

describe('useWidth', () => {
  it('sin ResizeObserver se queda en el valor por defecto', () => {
    render(<Probe />)
    expect(screen.getByText('320')).toBeInTheDocument()
  })

  it('sigue el ancho real del elemento y deja de observarlo al desmontar', () => {
    let notify: ResizeObserverCallback = () => {}
    const disconnect = vi.fn()
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: ResizeObserverCallback) {
          notify = callback
        }
        observe() {}
        disconnect = disconnect
      },
    )
    const { unmount } = render(<Probe />)

    act(() => notify([{ contentRect: { width: 517.6 } } as ResizeObserverEntry], {} as ResizeObserver))
    expect(screen.getByText('518')).toBeInTheDocument()

    unmount()
    expect(disconnect).toHaveBeenCalled()
  })
})
