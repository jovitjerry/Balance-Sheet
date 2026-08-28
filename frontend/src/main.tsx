import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import DocumentPage from "./routes/DocumentPage";
import NotFoundPage from "./routes/NotFoundPage";
import UploadPage from "./routes/UploadPage";
import "./index.css";

/**
 * The document id lives in the URL.
 *
 * That is not cosmetic. It makes document isolation structural: a view cannot
 * show a document the address bar does not name, the browser's own history
 * separates one document from another, and a refresh reloads from the server
 * rather than from anything this tab happened to be holding.
 */
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
