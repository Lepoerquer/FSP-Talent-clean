// Обновляет docs/openapi/openapi.json по запущенному бэкенду, чтобы документация API и типы фронтенда
// совпадали с реальным кодом сервера. Использование: `npm run sync:api` (бэкенд должен быть запущен).
//
// Адрес сервера: переменная API_ORIGIN (по умолчанию http://127.0.0.1:8000).
import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const origin = process.env.API_ORIGIN ?? 'http://127.0.0.1:8000';
const url = `${origin}/api/v1/openapi.json`;
const target = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/openapi/openapi.json');

let spec;
try {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  spec = await res.json();
} catch (e) {
  console.error(`Не удалось получить спецификацию с ${url}: ${e.message}\nЗапустите бэкенд: uvicorn backend.app.main:app --port 8000`);
  process.exit(1);
}

await writeFile(target, JSON.stringify(spec, null, 2) + '\n', 'utf-8');
console.log(`OpenAPI ${spec.info.version}: ${Object.keys(spec.paths).length} путей записано в ${target}`);
