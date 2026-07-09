import type { Metadata } from "next";
import { oswald, barlow, spaceMono } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "TopoPuzzle Studio",
  description: "Generate printable topographic puzzle terrain models from any place on Earth.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${oswald.variable} ${barlow.variable} ${spaceMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
