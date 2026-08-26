import { createElement } from "react";
import type { RouteObject } from "react-router-dom";
import { PreviewPage } from "./PreviewPage";

export const previewRoutes: RouteObject[] = [
  { path: "/__preview", element: createElement(PreviewPage) },
];
