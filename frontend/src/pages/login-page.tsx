import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const loginSchema = z.object({ password: z.string().min(1, "请输入密码") });
type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const { register, handleSubmit, formState } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
  });
  const login = useMutation({ mutationFn: api.login, onSuccess });

  return (
    <main className="grid min-h-screen place-items-center bg-stone-50 p-4">
      <form
        className="w-full max-w-sm rounded-xl border border-neutral-200 bg-white p-7 shadow-sm"
        onSubmit={handleSubmit(({ password }) => login.mutate(password))}
      >
        <h1 className="text-2xl font-semibold">拾记</h1>
        <p className="mb-6 mt-1 text-sm text-neutral-500">登录后访问你的记录</p>
        <label className="mb-2 block text-sm font-medium" htmlFor="password">密码</label>
        <Input id="password" type="password" autoFocus {...register("password")} />
        <p className="mt-2 min-h-5 text-sm text-red-600">
          {formState.errors.password?.message ?? (login.error instanceof Error ? login.error.message : "")}
        </p>
        <Button className="mt-3 w-full" disabled={login.isPending} type="submit">
          {login.isPending ? "登录中…" : "登录"}
        </Button>
      </form>
    </main>
  );
}
