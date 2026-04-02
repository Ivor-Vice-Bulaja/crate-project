# frontend/

The React frontend for Crate. Built with Vite for fast development and optimised production builds.

## What belongs here

- `src/` — All React source code
  - `views/` — Full-page components (Library, Crates, SetPlanner)
  - `components/` — Reusable UI components shared across views
  - `App.jsx` — Root component with routing
- `public/` — Static assets served as-is (favicon, fonts)
- `package.json` — Node dependencies and npm scripts
- `.eslintrc.cjs` — ESLint configuration
- `.prettierrc` — Prettier configuration

## Running

```bash
npm run dev       # start dev server (hot reload)
npm run build     # production build to dist/
npm run lint      # check code with ESLint
npm run format    # auto-format with Prettier
npm run preview   # preview the production build locally
```

## Communicates with backend via

REST API at `http://localhost:8000` (configurable). See `backend/api/` for endpoints.
