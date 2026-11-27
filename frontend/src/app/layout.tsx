import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bureaucracy Copilot",
  description:
    "Answers international students' questions about German bureaucracy, with a link to the " +
    "official source for every claim.",
};

// Makes the page fit phone screens instead of showing a zoomed-out desktop layout.
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
