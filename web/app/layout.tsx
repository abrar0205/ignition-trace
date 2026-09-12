import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IgnitionTrace — Vehicle Software Lab",
  description: "Record, replay and investigate Android Automotive events and vehicle signals.",
  icons: {
    icon: `${process.env.NEXT_PUBLIC_BASE_PATH || ""}/favicon.svg`,
    shortcut: `${process.env.NEXT_PUBLIC_BASE_PATH || ""}/favicon.svg`,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
