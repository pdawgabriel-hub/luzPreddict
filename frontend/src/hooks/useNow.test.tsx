import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useNow } from './useNow'

describe('useNow', () => {
  it('se actualiza cada minuto y deja de hacerlo al desmontar', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-06T10:00:00Z'))
    const { result, unmount } = renderHook(() => useNow())

    expect(result.current.toISOString()).toBe('2026-10-06T10:00:00.000Z')
    act(() => vi.advanceTimersByTime(60_000))
    expect(result.current.toISOString()).toBe('2026-10-06T10:01:00.000Z')

    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
