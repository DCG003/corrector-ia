import { defineConfig, type PluginOption } from 'vite'
import react from '@vitejs/plugin-react'
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { createConnection } from 'node:net'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const RAIZ = fileURLToPath(new URL('..', import.meta.url))
const PUERTO_BACKEND = 8000

/** True si ya hay algo escuchando en ese puerto de localhost. */
function puertoOcupado(puerto: number): Promise<boolean> {
  return new Promise((responder) => {
    const socket = createConnection({ port: puerto, host: '127.0.0.1' })
    const cerrar = (resultado: boolean) => {
      socket.destroy()
      responder(resultado)
    }
    socket.setTimeout(700)
    socket.once('connect', () => cerrar(true))
    socket.once('error', () => cerrar(false))
    socket.once('timeout', () => cerrar(false))
  })
}

/** Ruta al intérprete del entorno virtual, o null si aún no se ha instalado. */
function rutaPython(): string | null {
  const candidatos = [
    resolve(RAIZ, '.venv/Scripts/python.exe'), // Windows
    resolve(RAIZ, '.venv/bin/python'), // Linux / macOS
  ]
  return candidatos.find(existsSync) ?? null
}

/**
 * Arranca el backend de FastAPI junto con el servidor de desarrollo y lo para
 * al cerrarlo, para no tener que abrir dos terminales.
 *
 * - Solo actúa en `npm run dev`; `npm run build` no lo toca.
 * - Si el puerto 8000 ya está ocupado, no arranca nada: así puedes seguir
 *   levantando el backend a mano (por ejemplo, para depurarlo) sin conflictos.
 */
function backendPlugin(): PluginOption {
  let proceso: ChildProcess | null = null

  const pararBackend = () => {
    if (proceso && proceso.exitCode === null) proceso.kill()
    proceso = null
  }

  return {
    name: 'arrancar-backend',
    apply: 'serve',
    async configureServer(server) {
      const logger = server.config.logger

      if (await puertoOcupado(PUERTO_BACKEND)) {
        logger.info(`  ➜  backend:  ya hay algo escuchando en :${PUERTO_BACKEND}, no se arranca otro`)
        return
      }

      const python = rutaPython()
      if (!python) {
        logger.warn('  ➜  backend:  no se encontró .venv — ejecuta install.ps1 en la raíz del proyecto')
        return
      }

      proceso = spawn(
        python,
        ['-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', String(PUERTO_BACKEND)],
        { cwd: RAIZ, stdio: ['ignore', 'pipe', 'pipe'] },
      )

      const volcar = (datos: Buffer) => {
        for (const linea of datos.toString().split('\n')) {
          if (linea.trim()) process.stdout.write(`  [backend] ${linea.trimEnd()}\n`)
        }
      }
      proceso.stdout?.on('data', volcar)
      proceso.stderr?.on('data', volcar)

      proceso.on('exit', (codigo) => {
        if (codigo !== null && codigo !== 0) {
          logger.error(`  ➜  backend:  se cerró con código ${codigo}`)
        }
        proceso = null
      })

      logger.info(`  ➜  backend:  http://localhost:${PUERTO_BACKEND}  (docs en /docs)`)

      // Que el backend muera con el servidor de desarrollo, no quede huérfano.
      server.httpServer?.once('close', pararBackend)
      process.once('exit', pararBackend)
      process.once('SIGINT', () => {
        pararBackend()
        process.exit(0)
      })
      process.once('SIGTERM', () => {
        pararBackend()
        process.exit(0)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), backendPlugin()],
})
