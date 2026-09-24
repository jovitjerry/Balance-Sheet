import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import DocumentPage from "./routes/DocumentPage";
import NotFoundPage from "./routes/NotFoundPage";
import UploadPage from "./routes/UploadPage";
import "./index.css";
const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    errorElement: <App />,
    children: [
      { index: true, element: <UploadPage /> },
      { path: "documents/:documentId", element: <DocumentPage /> },
      { path: "documents/:documentId/:tab", element: <DocumentPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
const container = document.getElementById("root");
if (!container) throw new Error("#root not found in index.html");
createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
