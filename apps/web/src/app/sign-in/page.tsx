"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";

export default function SignInPage() {
  const router = useRouter();
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string>();
  const [isPending, setIsPending] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(undefined);
    setIsPending(true);

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    const name = String(form.get("name") ?? email);
    try {
      const result = isSignUp
        ? await authClient.signUp.email({ email: email.trim(), password, name: name.trim() })
        : await authClient.signIn.email({ email: email.trim(), password });
      if (result.error) {
        setError(result.error.status === 429 ? "操作过于频繁，请稍后再试。" : isSignUp ? "注册失败，请检查填写内容；已有账户请直接登录。" : "登录失败，请核对邮箱和密码后重试。");
        return;
      }
      const returnTo = new URLSearchParams(window.location.search).get("returnTo") ?? "/";
      const destination = returnTo.startsWith("/") && !returnTo.startsWith("//") && !/[\\\s\u0000-\u001f]/.test(returnTo) ? returnTo : "/";
      router.replace(destination);
      router.refresh();
    } catch { setError("无法连接服务，请检查网络后重试。"); }
    finally { setIsPending(false); }
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
            {isSignUp ? "创建账户，开始你的职业计划" : "登录，继续你的职业计划"}
          </p>
        </div>
        <fieldset disabled={isPending} className="space-y-4">
        {isSignUp && <div className="space-y-2"><label htmlFor="sign-in-name" className="text-sm">显示名称</label>
          <input
            id="sign-in-name"
            name="name"
            autoComplete="name"
            placeholder="你的名字"
            required
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
          />
        </div>}
        <div className="space-y-2"><label htmlFor="sign-in-email" className="text-sm">邮箱</label>
        <input
          id="sign-in-email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="name@example.com"
          required
          className="h-10 w-full rounded-md border bg-background px-3 text-sm"
        />
        </div>
        <div className="space-y-2"><label htmlFor="sign-in-password" className="text-sm">密码</label><div className="relative">
        <input
          id="sign-in-password"
          name="password"
          type={showPassword ? "text" : "password"}
          autoComplete={isSignUp ? "new-password" : "current-password"}
          placeholder={isSignUp ? "至少 8 个字符" : "输入密码"}
          minLength={isSignUp ? 8 : undefined}
          required
          className="h-10 w-full rounded-md border bg-background pl-3 pr-11 text-sm"
        />
        <button type="button" aria-label={showPassword ? "隐藏密码" : "显示密码"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)} className="absolute right-0 top-0 flex size-10 items-center justify-center text-muted-foreground">{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div></div>
        </fieldset>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={isPending}>
          {isPending ? "正在处理…" : isSignUp ? "创建账户" : "登录"}
        </Button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => { setIsSignUp(value => !value); setError(undefined); setShowPassword(false); }}
          className="w-full text-sm text-muted-foreground hover:text-foreground"
        >
          {isSignUp ? "已有账户？登录" : "还没有账户？创建账户"}
        </button>
      </form>
    </main>
  );
}
