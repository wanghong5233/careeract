"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { LogOut, Settings, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { authClient } from "@/lib/auth-client";
import { clearSpaceDrafts } from "@/lib/agent-space-state";

type Appearance = "system" | "light" | "dark";
const appearanceKey = "careeract-appearance";

export function AccountButton({ compact = false, onClick }: { compact?: boolean; onClick: () => void }) {
  const { data: session, isPending } = authClient.useSession();
  const name = session?.user.name || "我的账户";
  if (compact) return <Button variant="ghost" size="icon" onClick={onClick} title="账户与设置" aria-label="账户与设置"><Settings className="size-4 text-muted-foreground" /></Button>;
  return <button type="button" onClick={onClick} aria-label="账户与设置" className="flex w-full items-center gap-3 rounded-lg px-2 py-3 text-left hover:bg-muted">
    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium" aria-hidden="true">{session ? name.slice(0, 1).toUpperCase() : <UserRound className="size-4" />}</span>
    <span className="min-w-0 flex-1 truncate text-xs">{isPending ? "正在加载账户…" : name}</span><Settings className="size-3.5 text-muted-foreground" />
  </button>;
}

export function WorkspaceAccount({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const { data: session, isPending, error: sessionError, refetch } = authClient.useSession();
  const [tab, setTab] = useState<"account" | "appearance">("account");
  const [appearance, setAppearance] = useState<Appearance>("system");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<"close" | "appearance" | "sign-out" | null>(null);
  const dirty = nameDraft !== null && nameDraft !== session?.user.name;

  function requestClose() {
    if (busy) return;
    if (dirty) { setConfirmation("close"); return; }
    onOpenChange(false); setError(""); setStatus(""); setNameDraft(null); setConfirmation(null);
  }

  function changeTab(value: "account" | "appearance") {
    if (value === "appearance" && dirty) { setConfirmation("appearance"); return; }
    setTab(value); setError(""); setStatus(""); setConfirmation(null);
  }

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    function applyAppearance() {
      let stored: string | null = null;
      try { stored = localStorage.getItem(appearanceKey); }
      catch { stored = null; }
      const preference: Appearance = stored === "dark" || stored === "light" ? stored : "system";
      setAppearance(preference);
      const dark = preference === "dark" || (preference === "system" && query.matches);
      document.documentElement.classList.toggle("dark", dark);
      document.documentElement.style.colorScheme = dark ? "dark" : "light";
    }
    applyAppearance();
    query.addEventListener("change", applyAppearance);
    window.addEventListener("storage", applyAppearance);
    return () => { query.removeEventListener("change", applyAppearance); window.removeEventListener("storage", applyAppearance); };
  }, []);

  function changeAppearance(value: Appearance) {
    setAppearance(value);
    const dark = value === "dark" || (value === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
    try { localStorage.setItem(appearanceKey, value); setStatus("外观设置已保存到此浏览器。"); }
    catch { setStatus("外观已更新；此浏览器无法保存设置。"); }
  }

  async function saveName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    if (!name) { setError("请输入显示名称。"); return; }
    setBusy(true); setError(""); setStatus("");
    try {
      const result = await authClient.updateUser({ name });
      if (result.error) { setError("名称保存失败，请重试。"); return; }
      await refetch();
      setNameDraft(null);
      setStatus("显示名称已保存。");
    } catch { setError("无法连接服务，请稍后重试。"); }
    finally { setBusy(false); }
  }

  async function signOut() {
    if (busy) return;
    setBusy(true); setError(""); setStatus("");
    try {
      const result = await authClient.signOut();
      if (result.error) { setError("退出失败，请重试。"); return; }
      try { clearSpaceDrafts(); } catch { setStatus("已退出；关闭此标签页以清理浏览器草稿。"); }
      router.replace("/sign-in"); router.refresh();
    } catch { setError("无法连接服务，请重试。"); }
    finally { setBusy(false); }
  }

  async function confirm() {
    if (confirmation === "sign-out") { await signOut(); return; }
    setNameDraft(null); setError(""); setStatus("");
    if (confirmation === "close") onOpenChange(false);
    else setTab("appearance");
    setConfirmation(null);
  }

  return <Dialog open={open} onOpenChange={value => { if (value) onOpenChange(true); else requestClose(); }}>
    <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
      <DialogHeader><DialogTitle>账户与设置</DialogTitle><DialogDescription>管理个人账户和此设备的使用偏好。</DialogDescription></DialogHeader>
      <div className="flex gap-2 border-b pb-3" aria-label="设置分类"><Button disabled={busy} variant={tab === "account" ? "secondary" : "ghost"} aria-pressed={tab === "account"} onClick={() => changeTab("account")}><UserRound />账户</Button><Button disabled={busy} variant={tab === "appearance" ? "secondary" : "ghost"} aria-pressed={tab === "appearance"} onClick={() => changeTab("appearance")}><Settings />外观</Button></div>
      {confirmation ? <div className="space-y-4 py-3"><p className="text-sm font-medium">{confirmation === "sign-out" ? "退出当前账户？" : "显示名称尚未保存"}</p><p className="text-sm leading-6 text-muted-foreground">{confirmation === "sign-out" ? "退出会清除此标签页的对话草稿。已保存的项目与职业资料不受影响。" : "可以返回保存，或放弃这次名称修改。"}</p><div className="flex justify-end gap-2"><Button variant="outline" disabled={busy} onClick={() => setConfirmation(null)}>返回</Button><Button disabled={busy} onClick={confirm}>{busy ? "正在退出…" : confirmation === "sign-out" ? "退出登录" : "放弃修改"}</Button></div></div> : tab === "account" ? isPending ? <p role="status" className="py-8 text-sm text-muted-foreground">正在加载账户…</p> : sessionError ? <div className="space-y-3 py-4"><p role="alert">账户信息加载失败。</p><Button variant="outline" onClick={() => refetch()}>重试</Button></div> : session ? <><form onSubmit={saveName} className="space-y-4 py-2"><div className="space-y-2"><label htmlFor="account-name" className="text-sm">显示名称</label><input id="account-name" name="name" value={nameDraft ?? session.user.name} onChange={event => { setNameDraft(event.target.value); setError(""); setStatus(""); }} maxLength={80} required disabled={busy} autoComplete="name" className="h-10 w-full rounded-md border bg-background px-3 text-sm" /></div><div className="space-y-2"><label htmlFor="account-email" className="text-sm">登录邮箱</label><input id="account-email" value={session.user.email} readOnly className="h-10 w-full rounded-md border bg-muted/40 px-3 text-sm" /><p className="text-xs text-muted-foreground">邮箱用于登录，当前暂不支持修改。</p></div><Button type="submit" disabled={busy || !dirty || !nameDraft?.trim()}>{busy ? "正在处理…" : "保存名称"}</Button></form><div className="mt-2 flex items-center justify-between gap-3 border-t pt-4"><span className="text-xs text-muted-foreground">此设备已登录</span><Button variant="outline" onClick={() => setConfirmation("sign-out")} disabled={busy}><LogOut />退出登录</Button></div><p className="text-xs leading-6 text-muted-foreground">对话草稿仅保留在本标签页，刷新可恢复；退出登录会清除。它们尚未保存为服务端对话历史。</p></> : <div className="space-y-3 py-4"><p>登录状态已失效，请重新登录。</p><Button onClick={() => router.replace(`/sign-in?returnTo=${encodeURIComponent(window.location.pathname + window.location.search)}`)}>前往登录</Button></div> : <div className="space-y-4 py-3"><label htmlFor="account-appearance" className="block text-sm">颜色主题</label><select id="account-appearance" value={appearance} onChange={event => changeAppearance(event.target.value as Appearance)} className="h-10 w-full rounded-md border bg-background px-3 text-sm"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select><p className="text-xs leading-6 text-muted-foreground">设置仅作用于此浏览器，跟随系统时会自动适应系统主题。</p></div>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}{status && <p role="status" className="text-sm text-muted-foreground">{status}</p>}
    </DialogContent>
  </Dialog>;
}
