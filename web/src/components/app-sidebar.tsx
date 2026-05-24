"use client"
import { ChevronsUpDown, FolderOpen, HelpCircle, LogOut, Moon, Settings, Sparkles, Sun } from "lucide-react";
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "./ui/sidebar";
import Link from "next/link";
import Image from "next/image";
import { useState, useEffect } from "react";
import { useAllWorkspacesItems } from "@/hooks/use-chat";
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Avatar } from "./ui/avatar";
import { clearAuthToken, getAuthToken, getUserInfo } from "@/app/action";
import { useRouter } from "next/navigation";

const navigation = [
    { name: "Workspaces", href: "/workspaces", icon: FolderOpen }
];

export function AppSidebar() {
    const { isMobile } = useSidebar();
    const { data: recentOpens } = useAllWorkspacesItems(1, 10);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [theme, setTheme] = useState<"light" | "dark">("light");

    const router = useRouter();

    // User Info
    const [userInfo, setUserInfo] = useState<{ name: string; email: string } | null>(null);


    useEffect(() => {
        const checkAuth = async () => {
            try {
                const token = await getAuthToken();
                setIsAuthenticated(!!token);

                // save user info
                if (token) {
                    const user_info = await getUserInfo();
                    setUserInfo(user_info);
                }
            } catch (error) {
                setIsAuthenticated(false);
            } finally {
                setIsLoading(false);
            }
        };
        checkAuth();
    }, []);

    if (isLoading || !isAuthenticated) {
        return null;
    }

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
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <SidebarMenuButton
                                    size="lg"
                                    className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                                >
                                    <Avatar className="h-8 w-8 rounded-full">
                                        <span className="bg-blue-400 w-full items-center justify-center flex">{userInfo?.name?.split(' ')[0].charAt(0)}{userInfo?.name?.split(' ')[1].charAt(0)}</span>
                                    </Avatar>
                                    <div className="grid flex-1 text-left text-sm leading-tight">
                                        <span className="truncate font-medium">{userInfo?.name}</span>
                                        <span className="truncate text-xs">{userInfo?.email}</span>
                                    </div>
                                    <ChevronsUpDown className="ml-auto size-4" />
                                </SidebarMenuButton>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent
                                className="w-(--radix-dropdown-menu-trigger-width) bg-sidebar border border-accent min-w-56 rounded-lg"
                                side={isMobile ? "bottom" : "right"}
                                align="end"
                                sideOffset={4}
                            >
                                <DropdownMenuLabel className="p-0 font-normal">
                                    <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                                        <Avatar className="h-8 w-8 rounded-lg">
                                            <span className="bg-blue-400 w-full items-center justify-center flex">{userInfo?.name?.split(' ')[0].charAt(0)}{userInfo?.name?.split(' ')[1].charAt(0)}</span>
                                        </Avatar>
                                        <div className="grid flex-1 text-left text-sm leading-tight">
                                            <span className="truncate font-medium">{userInfo?.name}</span>
                                            <span className="truncate text-xs">{userInfo?.email}</span>
                                        </div>
                                    </div>
                                </DropdownMenuLabel>
                                <DropdownMenuSeparator />
                                <DropdownMenuGroup>
                                    <Link href={'/settings'}>
                                        <DropdownMenuItem className="cursor-pointer">
                                            <Settings />
                                            Settings
                                        </DropdownMenuItem>
                                    </Link>
                                    <Link href={'/help'}>
                                        <DropdownMenuItem className="cursor-pointer">
                                            <HelpCircle />
                                            Help
                                        </DropdownMenuItem>
                                    </Link>
                                    <DropdownMenuItem onClick={toggleTheme} className="cursor-pointer">
                                        {theme === "light" ? <Moon /> : <Sun />}
                                        {theme === "light" ? "Dark mode" : "Light mode"}
                                    </DropdownMenuItem>
                                </DropdownMenuGroup>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => {
                                    clearAuthToken();
                                    router.push("/login");
                                }} className="cursor-pointer">
                                    <LogOut />
                                    Log out
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </SidebarMenuItem>
                </SidebarMenu>
            </SidebarFooter>
        </Sidebar>
    )
}