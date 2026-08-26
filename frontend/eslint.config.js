import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },
  {
    // Context+hook co-located with its Provider component is the idiomatic
    // React pattern (see components/ui/Toast.tsx); the fast-refresh
    // single-export-per-file rule doesn't fit it.
    files: ['**/*Provider.tsx', 'src/components/ui/Toast.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    // Pages/components stay props-only: no data layer, no router state or
    // navigation side effects. `<Link>`/`<NavLink>` are the one exception --
    // rendering a link is still a pure prop (`to="..."`), not a data fetch
    // or an imperative navigation, so several of Abhishek's pages already
    // use them for in-page links (e.g. LoginPage -> /register). Restricting
    // by importName rather than banning the whole module lets that stand
    // while still keeping `useNavigate`/`useLocation`/routing primitives out.
    files: ['src/components/**', 'src/pages/**'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: ['@/lib/api/*', '@/store/*', '@tanstack/*', '@/lib/ws/*'],
          paths: [
            {
              name: 'react-router-dom',
              importNames: [
                'useNavigate',
                'useLocation',
                'useParams',
                'useSearchParams',
                'useMatch',
                'useOutletContext',
                'useRoutes',
                'Outlet',
                'BrowserRouter',
                'Routes',
                'Route',
                'Navigate',
              ],
              message:
                'Routing state and navigation side effects belong in a *Container, not a page/component. <Link>/<NavLink> are fine.',
            },
          ],
        },
      ],
    },
  },
)
