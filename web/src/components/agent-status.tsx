"use client";
import { Loader2, Sparkles, Brain, Globe, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { useEffect, useRef, useState } from "react";
import { Progress } from "./ui/progress";

/**
 * Agent status display component
 * Shows animated status indicators for different agent operations
 */
interface AgentStatusProps {
    message: string;
    subMessage?: string;
    /** Type of agent operation: loading, planning, searching, thinking, or setup */
    type?: "loading" | "planning" | "searching" | "thinking" | "setup";
}

function SinWaveAnimation() {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        let t = 0;
        let rafId: number;

        const draw = () => {
            const W = canvas.width;
            const H = canvas.height;

            ctx.clearRect(0, 0, W, H);

            ctx.beginPath();
            ctx.strokeStyle = "#3b82f6";
            ctx.lineWidth = 3;
            ctx.lineJoin = "round";

            for (let x = 0; x <= W; x++) {
                const y = H / 2 + Math.sin((x / W) * Math.PI * 4 + t) * (H / 3);
                x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
            }

            ctx.stroke();
            t += 0.05;
            rafId = requestAnimationFrame(draw);
        };

        draw();
        return () => cancelAnimationFrame(rafId);
    }, []);
    return (
        <canvas
            ref={canvasRef}
            width={800}
            height={200}
            className="w-full max-w-6xl"
        />
    )
}

export default function AgentStatus({ message, subMessage, type = "loading" }: AgentStatusProps) {
    const getIcon = () => {
        switch (type) {
            case "planning":
                return <Brain className="h-10 w-10 text-purple-500" />;
            case "searching":
                return <Globe className="h-10 w-10 text-blue-500" />;
            case "thinking":
                return <Sparkles className="h-10 w-10 text-amber-500" />;
            case "setup":
                return <Zap className="h-10 w-10 text-emerald-500" />;
            default:
                return <Loader2 className="h-10 w-10 text-primary animate-spin" />;
        }
    };

    const [progress, setProgress] = useState(0);

    useEffect(() => {
        const timer = setInterval(() => {
            setProgress((prev) => (prev >= 100 ? 0 : prev + 1));

        }, 30);

        return () => clearInterval(timer);
    }, []);

    const getGradient = () => {
        switch (type) {
            case "planning":
                return "from-purple-500/20 to-blue-500/20";
            case "searching":
                return "from-blue-500/20 to-cyan-500/20";
            case "thinking":
                return "from-amber-500/20 to-orange-500/20";
            case "setup":
                return "from-emerald-500/20 to-teal-500/20";
            default:
                return "from-primary/20 to-primary/10";
        }
    };

    return (
        <Card className="flex flex-col items-center w-full max-w-4xl mx-auto border-none bg-transparent shadow-none">
            <CardHeader className="w-full items-center text-center space-y-6 pb-8">
                <div className="space-y-2">
                    <CardTitle className="text-3xl font-bold tracking-tight bg-linear-to-br from-foreground to-foreground/70 bg-clip-text text-transparent">
                        {message}
                    </CardTitle>
                    {subMessage && (
                        <div className="flex items-center justify-center gap-2.5 mt-2">
                            <span className="relative flex h-2.5 w-2.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary"></span>
                            </span>
                            <p className="text-muted-foreground font-medium">
                                {subMessage}
                            </p>
                        </div>
                    )}
                </div>
            </CardHeader>
            <CardContent className="w-full px-8 sm:px-12">
                <div className="relative w-full h-8 flex items-center">
                    <Progress value={progress} className="h-2 w-full z-0" />
                    {[0, 25, 50, 75, 100].map((step) => {
                        const isActive = progress >= step;
                        return (
                            <div
                                key={step}
                                className={cn(
                                    "absolute top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-full border-4 border-background transition-all duration-500 z-10",
                                    isActive 
                                        ? "h-6 w-6 bg-primary shadow-[0_0_15px_hsl(var(--primary)/0.5)] scale-110" 
                                        : "h-4 w-4 bg-muted-foreground/20"
                                )}
                                style={{ left: `${step}%` }}
                            />
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}
