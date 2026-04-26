import "@/app/globals.css";
import { Shell } from "@/components/shell/shell";

export const metadata = { title: "TechScreen" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk">
      <body className="bg-surface-base text-content-primary antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
