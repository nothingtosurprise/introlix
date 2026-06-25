"use client";

import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { InfoIcon, AlertCircleIcon, CheckCircle2Icon, DownloadIcon } from "lucide-react";
import { useDownloadHfModel, useDownloadLlamaCppBuild, useLlamaCppBuildStatus } from "@/hooks/use-services";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export default function Page() {
  const [url, setUrl] = useState("");

  const { data: isLlamaCppDownloaded, isLoading: isLlamaCppStatusLoading, isError: isLlamaCppStatusError } = useLlamaCppBuildStatus();

  const {
    isDownloading: isLlamaCppDownloading,
    progress: llamaCppDownloadProgress,
    downloadedBytes: llamaCppDownloadBytes,
    totalBytes: llamaCppTotalBytes,
    status: llamaCppStatus,
    error: llamaCppError,
    startDownload: startLlamaCppDownload,
    cancelDownload: cancelLlamaCppDownload
  } = useDownloadLlamaCppBuild();

  const {
    isDownloading,
    progress,
    downloadedBytes,
    totalBytes,
    status,
    error,
    startDownload,
    cancelDownload
  } = useDownloadHfModel();

  if (isLlamaCppStatusLoading) return <span>Checking status...</span>;

  if (isLlamaCppStatusError) return <span>Error While Checking For LLamaCpp Build</span>
  
  const isLlamaCppComplete = !isLlamaCppDownloading && llamaCppStatus === "downloaded";

  if (!isLlamaCppDownloaded) {
    console.log(isLlamaCppDownloaded)
    return (
      <Card className="w-full max-w-md border-dashed">
        <CardHeader>
          <CardTitle className="text-xl font-semibold">Llama.cpp Missing</CardTitle>
          <CardDescription>
            The Llama.cpp binaries are required to run local models. Please download the build to continue.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          {llamaCppError && (
            <Alert variant="destructive">
              <AlertCircleIcon />
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{llamaCppError.message}</AlertDescription>
            </Alert>
          )}
          {(isLlamaCppDownloading) ? (
            <div className="flex space-x-2 items-center justify-between w-full">
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span className="flex items-center gap-1.5 capitalize">
                    {isLlamaCppComplete && <CheckCircle2Icon size={14} className="text-green-500" />}
                    {llamaCppStatus ?? (isLlamaCppDownloading ? "Connecting…" : "")}
                  </span>
                  {llamaCppDownloadBytes !== null && llamaCppTotalBytes !== null && llamaCppTotalBytes > 0 && (
                    <span className="font-mono text-xs">
                      {formatBytes(llamaCppDownloadBytes)} / {formatBytes(llamaCppTotalBytes)}
                    </span>
                  )}
                </div>
                {llamaCppDownloadProgress !== null && (
                  <Progress value={Math.min(llamaCppDownloadProgress, 100)} className="h-2" />
                )}
              </div>
              <Button variant="destructive" className="cursor-pointer" onClick={cancelLlamaCppDownload}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button className="w-full cursor-pointer" onClick={startLlamaCppDownload} >
              <DownloadIcon className="mr-2 h-4 w-4" />
              Download Llama.cpp
            </Button>
          )}
        </CardFooter>
      </Card>
    )
  }

  const isComplete = !isDownloading && status === "downloaded";

  return (
    <div className="flex min-h-svh w-full items-center justify-center p-6 md:p-10">
      <div className="w-full max-w-3xl space-y-4">
        <Alert className="fixed top-5 w-5xl">
          <InfoIcon />
          <AlertTitle>Notice</AlertTitle>
          <AlertDescription>
            This is a temporary UI for downloading models from Hugging Face. Better UI with models list will be shown in the future.
          </AlertDescription>
        </Alert>

        <Label className="mb-5 text-lg font-semibold">Download Models</Label>

        <Field orientation="horizontal">
          <Input
            type="text"
            placeholder="unsloth/gemma-4-E4B-it-GGUF or unsloth/gemma-4-E4B-it-GGUF:Q4_K_M"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !isDownloading && startDownload(url.trim())}
            disabled={isDownloading}
          />
          {isDownloading ? (
            <Button variant="destructive" className="cursor-pointer" onClick={cancelDownload}>
              Cancel
            </Button>
          ) : (
            <Button className="cursor-pointer" onClick={() => startDownload(url.trim())} disabled={!url.trim()}>
              Download
            </Button>
          )}
        </Field>

        {/* Error */}
        {error && (
          <Alert variant="destructive">
            <AlertCircleIcon />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}

        {/* Progress */}
        {(isDownloading || isComplete) && (
          <div className="space-y-2 pt-1">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5 capitalize">
                {isComplete && <CheckCircle2Icon size={14} className="text-green-500" />}
                {status ?? (isDownloading ? "Connecting…" : "")}
              </span>
              {downloadedBytes !== null && totalBytes !== null && totalBytes > 0 && (
                <span className="font-mono text-xs">
                  {formatBytes(downloadedBytes)} / {formatBytes(totalBytes)}
                </span>
              )}
            </div>
            {progress !== null && (
              <Progress value={Math.min(progress, 100)} className="h-2" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
