'use server';

import { cookies } from 'next/headers';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8042';
const API_KEY = process.env.NEXT_PUBLIC_INTROLIX_API_KEY || 'local_api_key123';

export async function loginAction(email: string, password: string) {
  const url = new URL(`${BASE_URL}/auth/login`);
  url.searchParams.set('email', email);
  url.searchParams.set('password', password);

  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'X-API-Key': `${API_KEY}`,
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Login failed: ${res.status} ${text}`);
  }

  const data = await res.json();

  const cookieStore = await cookies();
  cookieStore.set('token', data.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * 7,
    path: '/',
  });

  cookieStore.set('userInfo', JSON.stringify({ name: data.name, email: data.email }), {
    maxAge: 60 * 60 * 24 * 7,
    path: '/',
  });

  return data;
}

export async function signupAction(name: string, email: string, password: string) {
  const url = new URL(`${BASE_URL}/auth/signup`);
  url.searchParams.set('name', name);
  url.searchParams.set('email', email);
  url.searchParams.set('password', password);

  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'X-API-Key': `${API_KEY}`,
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Signup failed: ${res.status} ${text}`);
  }

  const data = await res.json();

  const cookieStore = await cookies();
  cookieStore.set('token', data.access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * 7,
    path: '/',
  });

  cookieStore.set('userInfo', JSON.stringify({ name: data.name, email: data.email }), {
    maxAge: 60 * 60 * 24 * 7,
    path: '/',
  });

  return data;
}
