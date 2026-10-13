import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      // tokens.test.ts lee tokens.css para comprobar el contraste de los colores
      css: { include: [/tokens\.css/] },
      // npm run test:coverage: falla si la cobertura baja de estos mínimos
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/api/schema.d.ts', 'src/main.tsx', 'src/vite-env.d.ts'],
        reporter: ['text-summary', 'html'],
        thresholds: { statements: 95, branches: 85, functions: 95, lines: 95 },
      },
      // Hora de Madrid en todos los tests, sea cual sea la del equipo o la de CI
      env: { TZ: 'Europe/Madrid' },
    },
  }),
)
