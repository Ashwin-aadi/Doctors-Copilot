import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { previewRoutes } from "./pages/preview";

// TEMP: minimal routing so /__preview is reachable before the real router/providers
// shell lands. Replace with the full app router.
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/__preview" replace />} />
        {previewRoutes.map((route) => (
          <Route key={route.path} path={route.path} element={route.element} />
        ))}
      </Routes>
    </BrowserRouter>
  );
}

export default App;
