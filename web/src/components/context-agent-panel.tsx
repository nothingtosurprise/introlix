"use client";

import { useMemo, useState, useCallback, KeyboardEvent, useRef, useEffect } from "react";
import {
  ArrowUp,
  Book,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  LayoutTemplate,
  Loader2,
  MessageSquare,
  RefreshCcw,
  Settings2,
  Sparkles,
  Target
} from "lucide-react";
import { motion } from "framer-motion";

// UI Components
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";

// Logic
import { useSetupContextAgent } from "@/hooks/use-desk";
import { ResearchDesk } from "@/lib/types";
import { cn } from "@/lib/utils";

const MODELS = [
  { label: "Auto Selection", value: "auto", icon: Sparkles },
  { label: "GPT-5", value: "gpt-5", icon: Bot },
  { label: "Claude Sonnet 4", value: "claude-sonnet-4", icon: Bot },
  { label: "Deepseek V3.2", value: "deepseek/deepseek-v3.2-exp", icon: BrainCircuit },
  { label: "Gemini 2.5 Pro", value: "google/gemini-2.5-pro", icon: Bot },
] as const;

const SCOPES = [
  { label: "Narrow Focus", value: "narrow" },
  { label: "Medium Range", value: "medium" },
  { label: "Comprehensive", value: "comprehensive" },
] as const;

type ContextAgentPanelProps = {
  workspaceId: string;
  deskId: string;
  desk: ResearchDesk;
  initialPrompt: string;
  initialModel: string;
  researchScope: string;
};

export default function ContextAgentPanel({
  workspaceId,
  deskId,
  desk,
  initialPrompt,
  initialModel,
  researchScope
}: ContextAgentPanelProps) {
  const contextAgent = desk.context_agent;
  const [answers, setAnswers] = useState("");
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Setup State
  const [scope, setScope] = useState<string>(
    ["narrow", "medium", "comprehensive"].includes(researchScope) ? researchScope : "medium"
  );
  const [model, setModel] = useState(initialModel || "auto");

  const setupContextAgent = useSetupContextAgent();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [answers]);

  const questions = useMemo(() => {
    if (!contextAgent?.questions) return [];
    return contextAgent.questions.map((question) =>
      typeof question === "string" ? question : JSON.stringify(question)
    );
  }, [contextAgent?.questions]);

  const deskTitle = typeof desk.title === "string" ? desk.title : "Untitled Research Desk";

  const finalPrompt =
    typeof contextAgent?.final_prompt === "string"
      ? contextAgent.final_prompt
      : contextAgent?.final_prompt
        ? JSON.stringify(contextAgent.final_prompt, null, 2)
        : "";

  const researchParameters = contextAgent?.research_parameters as
    | Record<string, string | number>
    | undefined;

  const handleSubmit = () => {
    if (!initialPrompt.trim() && !answers.trim()) return;

    setupContextAgent.mutate(
      {
        workspaceId,
        deskId,
        data: {
          prompt: initialPrompt.trim(),
          model,
          answers: answers.trim() || undefined,
          research_scope: scope as "narrow" | "medium" | "comprehensive",
        },
      },
      {
        onSuccess: () => setAnswers(""),
      }
    );
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === "Enter" && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleRetry = () => {
    setupContextAgent.mutate({
      workspaceId,
      deskId,
      data: {
        prompt: initialPrompt?.trim() || "",
        model: initialModel?.trim() || "auto",
        research_scope: scope as "narrow" | "medium" | "comprehensive",
      },
    });
  }

  const isPending = setupContextAgent.isPending;

  return (
    <div className="flex h-screen w-full flex-col bg-background text-foreground">
      {/* --- Header --- */}
      <header className="sticky top-4 z-10 flex items-center justify-between border bg-accent/20 backdrop-blur-lg px-6 py-3 mx-4 mt-4 rounded-full">
        <motion.div 
          className="flex items-center gap-3 relative"
          animate={{ y: [0, -1.5, 0] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        >
          <motion.div
            initial={{ x: 0, scaleX: 1, scaleY: 1, rotate: 0 }}
            animate={{ 
              x: [0, 8, -10, 4, 0],
              scaleX: [1, 1.25, 0.85, 1.05, 1],
              scaleY: [1, 0.75, 1.15, 0.95, 1],
              rotate: [0, 6, -6, 2, 0]
            }}
            transition={{ 
              duration: 1.4, 
              times: [0, 0.5, 0.7, 0.85, 1], 
              ease: ["easeIn", "easeOut", "easeInOut", "easeInOut"] 
            }}
            style={{ transformOrigin: "right center", zIndex: 10 }}
          >
            <Bot size={30} className="" />
          </motion.div>
          <motion.div 
            className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider"
            initial={{ x: -40, opacity: 0, scaleX: 0.5, scaleY: 0.8 }}
            animate={{ 
              x: [-40, -18, 30, -8, 0], 
              opacity: [0, 1, 1, 1, 1],
              scaleX: [0.8, 1.4, 0.85, 1.05, 1],
              scaleY: [0.8, 0.65, 1.15, 0.95, 1]
            }}
            transition={{ 
              duration: 1.4, 
              times: [0, 0.5, 0.7, 0.85, 1], 
              ease: ["easeIn", "easeOut", "easeInOut", "easeInOut"] 
            }}
            style={{ transformOrigin: "left center", zIndex: 5 }}
          >
            Context Agent
          </motion.div>
        </motion.div>
        <div className="">
          <h1 className="text-lg font-bold tracking-tight">{deskTitle}</h1>
        </div>
        <div className="flex items-center gap-3 pr-2">
          {contextAgent?.confidence_level !== undefined && (
            <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent/30 border border-border/40 backdrop-blur-sm shadow-sm transition-all hover:bg-accent/50">
              <Target className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">Confidence</span>
              <span className={cn("text-xs font-bold",
                contextAgent.confidence_level > 0.8 ? "text-emerald-500" : "text-amber-500"
              )}>
                {(contextAgent.confidence_level * 100).toFixed(0)}%
              </span>
            </div>
          )}

          <div className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full border backdrop-blur-sm shadow-sm transition-all",
            contextAgent?.move_next 
              ? "bg-emerald-500/10 border-emerald-500/20" 
              : ""
          )}>
            {contextAgent?.move_next ? (
              <>
                <CheckCircle2 className="h-4 w-4" /> 
                <span className="text-[11px] font-bold uppercase tracking-wider">Ready</span>
              </>
            ) : (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> 
                <span className="text-[11px] font-bold uppercase tracking-wider">Gathering</span>
              </>
            )}
          </div>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  onClick={handleRetry} 
                  className="rounded-full h-8 w-8 hover:bg-accent hover:text-foreground text-muted-foreground transition-all cursor-pointer"
                >
                  <RefreshCcw className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                <p>Retry setup</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </header>

      {/* --- Scrollable Content --- */}
      <ScrollArea className="flex-1">
        <main className="mx-auto max-w-4xl space-y-8 px-6 py-8">

          {/* Clarification Section */}
          <section className="space-y-4">
            <Card className={cn("border-none shadow-sm", questions.length > 0)}>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">
                  {questions.length > 0 ? "The agent needs your input" : "All clear for now"}
                </CardTitle>
                <CardDescription>
                  {questions.length > 0
                    ? "Please address the following questions in the chat below to refine the research."
                    : "The agent has sufficient context to proceed, but you can add more details below."}
                </CardDescription>
              </CardHeader>
              {questions.length > 0 && (
                <CardContent>
                  <ul className="space-y-3">
                    {questions.map((q, i) => (
                      <li key={i} className="flex items-center gap-3 rounded-lg bg-muted/50 p-3 text-sm leading-relaxed">
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium text-muted-foreground shadow-sm ring-1 ring-inset ring-border">
                          {i + 1}
                        </span>
                        {q}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              )}
            </Card>
          </section>

          <Separator />

          {/* Technical Details (Accordion) */}
          <Accordion type="multiple" className="w-full space-y-4">

            {/* Generated Prompt View */}
            {finalPrompt && (
              <AccordionItem value="prompt" className="rounded-lg bg-card px-4">
                <AccordionTrigger className="hover:no-underline py-4">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Book className="h-4 w-4 text-muted-foreground" />
                    Current Final Prompt
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="relative rounded-md bg-muted/50 p-4 font-mono text-xs text-muted-foreground">
                    <div className="absolute right-2 top-2 text-[10px] uppercase text-muted-foreground/50">Read Only</div>
                    <p className="whitespace-pre-wrap">{finalPrompt}</p>
                  </div>
                </AccordionContent>
              </AccordionItem>
            )}
          </Accordion>

          <div className="h-24" />
        </main>
      </ScrollArea>

      {/* --- Input Area --- */}
      <div className="sticky bottom-0 z-20 w-full bg-background p-4 pt-2">
        <div className="mx-auto max-w-4xl">
          <div className={cn(
            "relative flex flex-col rounded-xl border bg-background shadow-lg transition-all duration-200",
            isComposing && "ring-1 ring-ring border-primary"
          )}>

            {/* Text Input */}
            <textarea
              ref={textareaRef}
              value={answers}
              onChange={(e) => setAnswers(e.target.value)}
              onKeyDown={handleKeyDown}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              placeholder={questions.length > 0 ? "Answer the questions above or provide more context..." : "How can I help refine the research?"}
              disabled={isPending}
              className="min-h-15 max-h-50 w-full resize-none border-0 bg-transparent px-4 py-4 text-sm outline-none placeholder:text-muted-foreground focus:outline-none focus:ring-0 disabled:opacity-50"
              rows={1}
            />

            {/* Toolbar Row */}
            <div className="flex items-center justify-between border-t outline-none bg-muted/20 px-2 py-2">
              <div className="flex items-center gap-2">
                {/* Model Selector */}
                <Select value={model} onValueChange={setModel} disabled={isPending}>
                  <SelectTrigger className="h-8 gap-2 border-0 bg-transparent px-2 text-xs font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="start">
                    {MODELS.map((m) => (
                      <SelectItem key={m.value} value={m.value} className="text-xs">
                        <div className="flex items-center gap-2">
                          <m.icon className="h-3 w-3" />
                          {m.label}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Separator orientation="vertical" className="h-4" />

                {/* Scope Selector */}
                <Select value={scope} onValueChange={setScope} disabled={isPending}>
                  <SelectTrigger className="h-8 gap-2 border-0 bg-transparent px-2 text-xs font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground focus:ring-0">
                    <div className="flex items-center gap-2">
                      <LayoutTemplate className="h-3 w-3" />
                      <SelectValue />
                    </div>
                  </SelectTrigger>
                  <SelectContent align="start">
                    {SCOPES.map((s) => (
                      <SelectItem key={s.value} value={s.value} className="text-xs">
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Send Button */}
              <div className="flex items-center gap-2">
                <span className="hidden text-[10px] text-muted-foreground sm:inline-block">
                  {answers.trim() ? "Press Enter to send" : ""}
                </span>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        onClick={handleSubmit}
                        disabled={!answers.trim() && !initialPrompt.trim() || isPending}
                        size="icon"
                        className={cn(
                          "h-8 w-8 transition-all duration-200 rounded-lg cursor-pointer",
                          answers.trim() ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                        )}
                      >
                        {isPending ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <ArrowUp className="h-4 w-4" />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Run Context Agent</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}