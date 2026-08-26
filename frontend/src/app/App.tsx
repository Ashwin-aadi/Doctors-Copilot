import { BrowserRouter } from "react-router-dom";
import { QueryProvider } from "../providers/QueryProvider";
import { ThemeProvider } from "../providers/ThemeProvider";
import { ToastProvider } from "../providers/ToastProvider";
import { AuthProvider } from "../providers/AuthProvider";
import { AppRouter } from "../router";

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <QueryProvider>
          <ThemeProvider>
            <AuthProvider>
              <AppRouter />
            </AuthProvider>
          </ThemeProvider>
        </QueryProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
