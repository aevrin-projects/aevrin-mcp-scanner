"use server";

import { createClient } from "@/lib/supabase/server";

export async function sendMagicLink(
  _prevState: { status: "idle" | "sent" | "error"; message?: string },
  formData: FormData,
): Promise<{ status: "idle" | "sent" | "error"; message?: string }> {
  const email = formData.get("email") as string;
  if (!email || !email.includes("@")) {
    return { status: "error", message: "Enter a valid email address." };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: `${process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"}/auth/confirm`,
    },
  });

  if (error) {
    return { status: "error", message: error.message };
  }
  return { status: "sent", message: `Check ${email} for a sign-in link.` };
}
