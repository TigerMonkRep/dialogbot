import { InstallCapture } from "@/components/install-app";

/** The entry page. InstallCapture only listens for the browser's install prompt (never shows anything here), so a
 *  later «Download app» – after the demo call, in the app – can be one tap. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return <>{children}<InstallCapture /></>;
}
