import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
    const token = request.cookies.get("token");
    const { pathname } = request.nextUrl;

    if (!token && pathname !== "/login" && pathname !== "/signup") {
        const loginUrl = new URL("/login", request.url);
        return NextResponse.redirect(loginUrl);
    }

    if (token && (pathname === "/login" || pathname === "/signup")) {
        const homeUrl = new URL("/", request.url);
        return NextResponse.redirect(homeUrl);
    }

    return NextResponse.next();
}