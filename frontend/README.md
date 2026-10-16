# DevTrack frontend

Base de interfaz creada con React, TypeScript, Vite y Tailwind CSS. Incluye una
pantalla inicial y el proxy local `/api` hacia FastAPI; todavía no implementa
login ni dashboard.

## Requisitos

- Node.js 18 o posterior.
- npm.

## Desarrollo

Desde esta carpeta:

```powershell
npm install
npm run dev
```

Vite escucha en `http://127.0.0.1:5173`. El proxy apunta por defecto a
`http://127.0.0.1:8000`, el puerto habitual de Uvicorn; el repositorio no fija
un puerto para FastAPI. Arranca el backend desde `backend/` con:

```powershell
uvicorn main:app --reload --port 8000
```

Para usar otro destino del backend, configura `VITE_API_PROXY_TARGET`, por
ejemplo `VITE_API_PROXY_TARGET=http://127.0.0.1:8010`.

El navegador mantiene rutas como `/api/users/me`; Vite retira solo el prefijo
`/api` al reenviar, por lo que FastAPI recibe `/users/me`. Esto conserva el
path `/api` requerido por la cookie de sesión.

## Comprobación manual del proxy

Con FastAPI y Vite ejecutándose, solicita `http://127.0.0.1:5173/api/`.
Debe responder el mensaje de la ruta raíz de FastAPI (`/`). Este recorrido
comprueba el reenvío y la eliminación del prefijo sin requerir autenticación.

## Validación

```powershell
npm run typecheck
npm run build
```
