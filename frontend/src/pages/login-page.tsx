import "@/styles/login-page.css";
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
    <main className="login-layout">
      <form
        className="login-panel"
        onSubmit={handleSubmit(({ password }) => login.mutate(password))}
      >
        <h1 className="login-title">拾记</h1>
        <p className="login-description">登录后访问你的记录</p>
        <label className="login-label" htmlFor="password">
          密码
        </label>
        <Input id="password" type="password" autoFocus {...register("password")} />
        <p className="login-error">
          {formState.errors.password?.message ??
            (login.error instanceof Error ? login.error.message : "")}
        </p>
        <Button className="login-submit" disabled={login.isPending} type="submit">
          {login.isPending ? "登录中…" : "登录"}
        </Button>
      </form>
    </main>
  );
}
