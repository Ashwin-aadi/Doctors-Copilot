export const env = {
  apiBase: import.meta.env.VITE_API_BASE ?? "http://localhost:8000",
} as const;
