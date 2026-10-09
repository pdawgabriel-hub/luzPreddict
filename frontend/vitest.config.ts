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
      // Hora de Madrid en todos los tests, sea cual sea la del equipo o la de CI
      env: { TZ: 'Europe/Madrid' },
    },
  }),
)
