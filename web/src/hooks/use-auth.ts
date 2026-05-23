'use client';

import { login, signup } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { setAuthToken } from "@/app/action";

export function useLogin() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (items: { email: string; password: string }) => login(items.email, items.password),
        onSuccess: async (data) => {
            await setAuthToken(data.access_token);
            queryClient.invalidateQueries({ queryKey: ["currentUser"] });
        },
        onError: (error) => {
            console.error("Login failed:", error);
        }
    });
}

export function useSignup() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (items: { name: string; email: string; password: string }) => signup(items.name, items.email, items.password),
        onSuccess: async (data) => {
            await setAuthToken(data.access_token);
            queryClient.invalidateQueries({ queryKey: ["currentUser"] });
        },
        onError: (error) => {
            console.error("Signup failed:", error);
        }
    });
}