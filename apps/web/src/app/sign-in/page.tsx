"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";

export default function SignInPage() {
  const router = useRouter();
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string>();
  const [isPending, setIsPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setIsPending(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    const name = String(form.get("name") ?? email);
    const result = isSignUp
      ? await authClient.signUp.email({ email, password, name })
      : await authClient.signIn.email({ email, password });

    setIsPending(false);
    if (result.error) {
      setError(result.error.message ?? "Authentication failed");
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-muted/30 p-6">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-xl border bg-background p-6 shadow-sm"
      >
        <div>
          <h1 className="text-2xl font-semibold">CareerAct</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isSignUp ? "Create your account" : "Sign in to your career workspace"}
          </p>
        </div>
        {isSignUp && (
          <input
            name="name"
            autoComplete="name"
            placeholder="Name"
            required
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
          />
        )}
        <input
          name="email"
          type="email"
          autoComplete="email"
          placeholder="Email"
          required
          className="h-10 w-full rounded-md border bg-background px-3 text-sm"
        />
        <input
          name="password"
          type="password"
          autoComplete={isSignUp ? "new-password" : "current-password"}
          placeholder="Password"
          minLength={8}
          required
          className="h-10 w-full rounded-md border bg-background px-3 text-sm"
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={isPending}>
          {isPending ? "Please wait…" : isSignUp ? "Create account" : "Sign in"}
        </Button>
        <button
          type="button"
          onClick={() => setIsSignUp((value) => !value)}
          className="w-full text-sm text-muted-foreground hover:text-foreground"
        >
          {isSignUp ? "Already have an account? Sign in" : "New to CareerAct? Sign up"}
        </button>
      </form>
    </main>
  );
}
