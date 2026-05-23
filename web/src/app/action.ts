'use server';
import { cookies } from 'next/headers';

export const getAuthToken = async (): Promise<string | null> => {
    const cookieStore = await cookies();
    const tokenCookie = await cookieStore.get("token");
    return tokenCookie ? tokenCookie.value : null;
}

export const setAuthToken = async (token: string): Promise<void> => {
    const cookieStore = await cookies();
    cookieStore.set("token", token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        maxAge: 60 * 60 * 24 * 7, // 7 days
        path: "/",
    });
}