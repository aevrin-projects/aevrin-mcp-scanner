"use client";

import { useActionState } from "react";
import { sendMagicLink } from "./actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  const [state, formAction, pending] = useActionState(sendMagicLink, { status: "idle" as const });

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Sign in to Aevrin</CardTitle>
          <CardDescription>We&apos;ll email you a magic link — no password needed.</CardDescription>
        </CardHeader>
        <CardContent>
          {state.status === "sent" ? (
            <p className="text-sm text-muted-foreground" data-testid="magic-link-sent">
              {state.message}
            </p>
          ) : (
            <form action={formAction} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@company.com"
                  required
                  autoFocus
                />
              </div>
              {state.status === "error" && (
                <p className="text-sm text-destructive" role="alert">
                  {state.message}
                </p>
              )}
              <Button type="submit" disabled={pending} className="w-full">
                {pending ? "Sending…" : "Send magic link"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
