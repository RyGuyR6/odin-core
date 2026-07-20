"use client";

import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { authClient } from "@/lib/auth/client";

export default function LoginPage() {
  const router = useRouter();
  const { login, bootstrap } = useAuth();
  const [bootstrapRequired, setBootstrapRequired] = useState<boolean | null>(
    null,
  );
  const [identity, setIdentity] = useState("");
  const [username, setUsername] = useState("admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void authClient
        .bootstrapStatus()
        .then((result) => setBootstrapRequired(result.required))
        .catch(() => setBootstrapRequired(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      if (bootstrapRequired) {
        await bootstrap(username, email, password);
      } else {
        await login(identity, password, rememberMe);
      }
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign in");
    } finally {
      setPending(false);
    }
  }

  const initializing = bootstrapRequired === null;

  return (
    <main className="grid min-h-screen place-items-center bg-zinc-950 px-6 py-12 text-zinc-100">
      <section className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10">
            <ShieldCheck className="h-6 w-6 text-cyan-300" />
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.24em] text-cyan-300">
              Odin Core
            </p>
            <h1 className="text-2xl font-semibold">
              {bootstrapRequired ? "Create administrator" : "Secure access"}
            </h1>
          </div>
        </div>

        <form
          onSubmit={(event) => void submit(event)}
          className="space-y-5 rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-black/30"
        >
          {initializing ? (
            <p className="text-sm text-zinc-400">
              Checking Odin identity status…
            </p>
          ) : (
            <>
              {bootstrapRequired ? (
                <>
                  <Field
                    label="Administrator username"
                    value={username}
                    onChange={setUsername}
                    autoComplete="username"
                  />
                  <Field
                    label="Email"
                    type="email"
                    value={email}
                    onChange={setEmail}
                    autoComplete="email"
                  />
                </>
              ) : (
                <Field
                  label="Username or email"
                  value={identity}
                  onChange={setIdentity}
                  autoComplete="username"
                />
              )}

              <Field
                label="Password"
                type="password"
                value={password}
                onChange={setPassword}
                autoComplete={
                  bootstrapRequired ? "new-password" : "current-password"
                }
                hint={
                  bootstrapRequired
                    ? "Use at least 12 characters."
                    : undefined
                }
              />

              {!bootstrapRequired && (
                <label className="flex items-center gap-3 text-sm text-zinc-300">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(event) => setRememberMe(event.target.checked)}
                    className="h-4 w-4 rounded border-white/20 bg-zinc-900"
                  />
                  Keep me signed in
                </label>
              )}

              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={pending}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-300 px-4 py-3 font-medium text-zinc-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <LockKeyhole className="h-4 w-4" />
                {pending
                  ? "Please wait…"
                  : bootstrapRequired
                    ? "Create administrator"
                    : "Enter Odin"}
                {!pending && <ArrowRight className="h-4 w-4" />}
              </button>
            </>
          )}
        </form>

        <p className="mt-5 text-center text-xs text-zinc-500">
          HttpOnly sessions · Argon2 password hashing · protected workspace
        </p>
      </section>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-medium text-zinc-200">
        {label}
      </span>
      <input
        required
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        minLength={type === "password" ? 12 : undefined}
        className="w-full rounded-xl border border-white/10 bg-zinc-950/70 px-4 py-3 outline-none transition placeholder:text-zinc-600 focus:border-cyan-300/50 focus:ring-2 focus:ring-cyan-300/10"
      />
      {hint && <span className="mt-1 block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}
