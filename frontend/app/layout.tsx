// app/layout.tsx
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
