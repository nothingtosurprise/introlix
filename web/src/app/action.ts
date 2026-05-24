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

export const clearAuthToken = async (): Promise<void> => {
    const cookieStore = await cookies();
    cookieStore.delete("token");
    cookieStore.delete("userInfo");
}

export const setUserInfo = async (userInfo: { name: string; email: string }): Promise<void> => {
    const cookieStore = await cookies();
    cookieStore.set("userInfo", JSON.stringify(userInfo), {
        maxAge: 60 * 60 * 24 * 7, // 7 days
        path: "/",
    });
}

export const getUserInfo = async (): Promise<{ name: string; email: string } | null> => {
    const cookieStore = await cookies();
    const userInfoCookie = await cookieStore.get("userInfo");
    return userInfoCookie ? JSON.parse(userInfoCookie.value) : null;
}