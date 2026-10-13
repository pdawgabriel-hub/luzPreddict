// Configuración pública de la web (variables VITE_*, que acaban en el código del navegador).

/** Tema público de ntfy al que la tarea diaria envía el resumen de mañana. */
export const NTFY_TOPIC = import.meta.env.VITE_NTFY_TOPIC || 'luzpreddict'
export const NTFY_SERVER = 'https://ntfy.sh'
export const NTFY_TOPIC_URL = `${NTFY_SERVER}/${NTFY_TOPIC}`
