import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { DemoUserProvider } from "@/components/DemoUserProvider";
import { Header } from "@/components/Header";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "L.I.V.E",
  description: "Discover experiences worth doing.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900">
        <DemoUserProvider>
          <Header />
          {children}
        </DemoUserProvider>
      </body>
    </html>
  );
}
