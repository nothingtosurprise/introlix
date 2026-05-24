'use client';

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { loginAction, signupAction } from "@/app/actions/auth";

export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: (items: { email: string; password: string }) => loginAction(items.email, items.password),
    onSuccess: async (data) => {
      // cookies are set in the server action (next/headers)
      queryClient.invalidateQueries({ queryKey: ["currentUser"] });
      router.push("/");
    },
    onError: (error) => {
      console.error("Login failed:", error);
    },
  });
}

export function useSignup() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: (items: { name: string; email: string; password: string }) => signupAction(items.name, items.email, items.password),
    onSuccess: async (data) => {
      // cookies are set in the server action (next/headers)
      queryClient.invalidateQueries({ queryKey: ["currentUser"] });
      router.push("/");
    },
    onError: (error) => {
      console.error("Signup failed:", error);
    },
  });
}
