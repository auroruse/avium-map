import { defineConfig, type Plugin } from 'vite'
import { writeFileSync } from 'fs'
import { join, resolve } from 'path'
// @ts-expect-error plain Node script, no types
import { writeCoords } from './scripts/coords.mjs'

// The placer's Save button writes straight into src/data instead of pushing three
// downloads through the browser. A page cannot write to disk on its own, so the
// dev server does it: Save POSTs the JSON here and this hands it to fs.
//
// Dev only — configureServer never runs for a build, so nothing like this exists
// in the deployed site. The filename is checked against a fixed list rather than
// joined straight onto a path, because the body of a POST is not something to
// hand to the filesystem on trust.
const SAVEABLE = new Set(['cities.json', 'labels.json', 'stations.json'])

function placerSave(): Plugin {
  const dir = resolve(import.meta.dirname, 'src/data')
  return {
    name: 'avium-placer-save',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__save', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          return res.end('POST only')
        }
        let body = ''
        req.on('data', chunk => (body += chunk))
        req.on('end', () => {
          try {
            const { file, data } = JSON.parse(body) as { file: string; data: unknown }
            if (!SAVEABLE.has(file)) throw new Error(`refusing to write ${file}`)
            writeFileSync(join(dir, file), JSON.stringify(data, null, 2) + '\n')
            // coordinates.tsv is derived from these, so it is rewritten here
            // rather than left for someone to remember
            writeCoords(dir)
            res.setHeader('content-type', 'application/json')
            res.end(JSON.stringify({ ok: true, file }))
          } catch (err) {
            res.statusCode = 400
            res.end(String(err))
          }
        })
      })
    },
  }
}

export default defineConfig({
  base: './',
  build: { outDir: 'dist' },
  plugins: [placerSave()],
})
