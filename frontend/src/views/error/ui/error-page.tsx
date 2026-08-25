import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { buttonVariants } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";
import Link from "next/link";

// Reached from auth/callback and auth/confirm whenever sign-in doesn't
// complete, previously always showed one hardcoded "link expired" message
// left over from the old magic-link flow, even for a denied Google consent
// screen or a network blip mid-exchange. `reason` lets the actual cause
// show through instead of a generic dead end.
const MESSAGES: Record<string, { title: string; description: string }> = {
  google_denied: {
    title: "Google sign-in was cancelled",
    description: "You didn't approve access on Google's consent screen, so we couldn't sign you in.",
  },
  google_error: {
    title: "Google sign-in failed",
    description: "Google reported an error completing the request. This is usually temporary.",
  },
  github_denied: {
    title: "GitHub sign-in was cancelled",
    description: "You didn't approve access on GitHub's consent screen, so we couldn't sign you in.",
  },
  github_error: {
    title: "GitHub sign-in failed",
    description: "GitHub reported an error completing the request. This is usually temporary.",
  },
  // Distinct from *_error because it is not temporary and retrying will not
  // help: the exchange succeeded and the provider simply returned no address
  // to identify the account by. Worded without blaming the reader, since the
  // usual cause is a permission missing on our side, not their settings.
  github_email: {
    title: "GitHub didn't share an email address",
    description:
      "Sign-in completed, but GitHub returned no email address, and an account needs one. Try Google instead, or let us know at support@aevrin.net.",
  },
  google_email: {
    title: "Google didn't share an email address",
    description:
      "Sign-in completed, but Google returned no email address, and an account needs one. Try GitHub instead, or let us know at support@aevrin.net.",
  },
  exchange_failed: {
    title: "That sign-in link has expired",
    description: "Sign-in links and codes are single-use and expire quickly, request a new one.",
  },
  missing_code: {
    title: "Sign-in link is incomplete",
    description: "This link is missing information it needs to complete sign-in, it may have been copied incorrectly.",
  },
};

const DEFAULT_MESSAGE = {
  title: "Sign-in didn't complete",
  description: "Something went wrong finishing sign-in. Try again; it usually works on the next attempt.",
};

export async function ErrorPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  const { reason } = await searchParams;
  const { title, description } = (reason && MESSAGES[reason]) || DEFAULT_MESSAGE;
  return (
    <div className="flex min-h-[calc(100svh-3.5rem)] items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/login" className={cn(buttonVariants(), "w-full")}>
            Back to sign in
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
