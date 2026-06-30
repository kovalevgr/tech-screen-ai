import "@/app/globals.css";
import { Shell } from "@/components/shell/shell";
import { Providers } from "@/app/providers";

export const metadata = { title: "TechScreen" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk">
      <body className="bg-surface-base text-content-primary antialiased">
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
