import "@/app/globals.css";

export const metadata = { title: "TechScreen" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk">
      <body className="bg-surface-base text-content-primary antialiased">
        {children}
      </body>
    </html>
  );
}
