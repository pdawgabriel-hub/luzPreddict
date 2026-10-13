import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { KpiCard } from './KpiCard'
import { NumberInput } from './NumberInput'
import { SegmentedControl } from './SegmentedControl'
import { Stepper } from './Stepper'

function HourStepper() {
  const [value, setValue] = useState(1)
  return <Stepper label="Hora" value={value} min={0} max={2} onChange={setValue} format={(v) => `${v}:00`} decrementLabel="Antes" incrementLabel="Después" />
}

describe('Stepper', () => {
  it('sube y baja de uno en uno, sin salirse de los límites', async () => {
    const user = userEvent.setup()
    render(<HourStepper />)
    const down = screen.getByRole('button', { name: 'Hora: antes' })
    const up = screen.getByRole('button', { name: 'Hora: después' })

    expect(screen.getByRole('group', { name: 'Hora' })).toHaveTextContent('1:00')
    await user.click(down)
    expect(screen.getByText('0:00')).toBeInTheDocument()
    expect(down).toBeDisabled()

    await user.click(up)
    await user.click(up)
    expect(screen.getByText('2:00')).toBeInTheDocument()
    expect(up).toBeDisabled()
  })
})

describe('SegmentedControl', () => {
  it('marca la opción elegida y no deja elegir las desactivadas', async () => {
    const onChange = vi.fn()
    render(
      <SegmentedControl
        label="Día"
        value="hoy"
        onChange={onChange}
        segments={[
          { value: 'hoy', label: 'Hoy' },
          { value: 'manana', label: 'Mañana', disabled: true },
          { value: 'comparar', label: 'Comparar' },
        ]}
      />,
    )

    expect(screen.getByRole('group', { name: 'Día' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hoy' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Mañana' }))
    expect(onChange).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Comparar' }))
    expect(onChange).toHaveBeenCalledWith('comparar')
  })
})

describe('NumberInput', () => {
  it('admite coma decimal y solo avisa de valores válidos', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberInput label="Precio" value={0.15} min={0.01} max={1} decimals={3} unit="€/kWh" hint="Sin impuestos." onChange={onChange} />)
    const input = screen.getByRole('textbox', { name: 'Precio' })

    expect(input).toHaveValue('0,150')
    expect(input).toHaveAccessibleDescription('Sin impuestos.')

    await user.clear(input)
    await user.type(input, '2')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Entre 0,010 y 1 €/kWh')
    expect(onChange).not.toHaveBeenCalledWith(2)

    await user.clear(input)
    await user.type(input, '0,12')
    expect(input).toHaveAttribute('aria-invalid', 'false')
    expect(onChange).toHaveBeenLastCalledWith(0.12)
  })
})

describe('KpiCard', () => {
  it('muestra etiqueta, valor con unidad y detalle; la oscura se marca', () => {
    const { container } = render(<KpiCard dark label="Ahora" value="0,252" unit="€/kWh" detail="Hora cara" />)

    expect(container).toHaveTextContent('Ahora0,252 €/kWhHora cara')
    expect(container.firstChild).toHaveAttribute('data-dark', 'true')
  })
})
