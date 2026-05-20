"use client"
import { FolderOpen, Moon, Sun } from "lucide-react";
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "./ui/sidebar";
import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { useAllWorkspacesItems } from "@/hooks/use-chat";

const navigation = [
    { name: "Workspaces", href: "/workspaces", icon: FolderOpen }
];

export function AppSidebar() {
    const { data: recentOpens } = useAllWorkspacesItems(1, 10);

    const [theme, setTheme] = useState<"light" | "dark">("light");

    const toggleTheme = () => {
        const newTheme = theme === "light" ? "dark" : "light";
        setTheme(newTheme);
        document.documentElement.classList.toggle("dark");
    };

    return (
        <Sidebar collapsible="icon">
            <SidebarHeader>
                <SidebarMenu>
                    <Link href={'/'}>
                        <SidebarMenuButton className="cursor-pointer" tooltip="">
                            <Image src={'./vercel.svg'} alt="" width={20} height={20} />
                            <span className="text-lg font-bold">Introlix</span>
                        </SidebarMenuButton>
                    </Link>
                </SidebarMenu>
            </SidebarHeader>
            <SidebarContent>
                <SidebarGroup>
                    <SidebarGroupContent>
                        <SidebarMenu>
                            {navigation.map((item) => (
                                <SidebarMenuItem key={item.name}>
                                    <Link key={item.name} href={item.href}>
                                        <SidebarMenuButton className="cursor-pointer" tooltip={item.name}>
                                            {item.icon && <item.icon />}
                                            <span>{item.name}</span>
                                        </SidebarMenuButton>
                                    </Link>
                                </SidebarMenuItem>
                            ))}
                        </SidebarMenu>
                    </SidebarGroupContent>
                </SidebarGroup>
                <SidebarGroup className="flex-1 overflow-y-auto">
                    <SidebarGroupLabel>Recents</SidebarGroupLabel>
                    <SidebarGroupContent>
                        <SidebarMenu>
                            {recentOpens?.items.length === 0 && (
                                <div className="text-sm text-muted-foreground px-3">No recent Items</div>
                            )}
                            {recentOpens?.items.map((item) => (
                                <SidebarMenuItem key={item.id}>
                                    <Link href={`/workspaces/${item.workspace_id}/${item.type}/${item.id}`}>
                                        <SidebarMenuButton asChild tooltip={item.title || "Untitled"} className="cursor-pointer">
                                            <span className="group-data-[collapsible=icon]:hidden">{item.title.length > 25 ? item.title.slice(0, 25) + "..." : item.title || "Untitled"}</span>
                                        </SidebarMenuButton>
                                    </Link>
                                </SidebarMenuItem>
                            ))}
                        </SidebarMenu>
                    </SidebarGroupContent>
                </SidebarGroup>
            </SidebarContent>
            <SidebarFooter>
                <SidebarMenu>
                    <SidebarMenuItem>
                        <SidebarMenuButton onClick={toggleTheme} className="cursor-pointer w-full my-5 px-5 py-5">
                            {theme === "light" ? <Moon /> : <Sun />}
                            {theme === "light" ? "Dark mode" : "Light mode"}
                        </SidebarMenuButton>
                    </SidebarMenuItem>
                </SidebarMenu>
            </SidebarFooter>
        </Sidebar>
    )
}