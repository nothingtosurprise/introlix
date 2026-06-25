import { getLlamaCppBuildStatus, downloadLlamaCppBuild, downloadHfModel } from "@/lib/api";
import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

export function useLlamaCppBuildStatus() {
  return useQuery({
    queryKey: ["llama_cpp_build_status"],
    queryFn: () => getLlamaCppBuildStatus(),
    select: (data) => data.status === "downloaded",
  });
}

export function useDownloadLlamaCppBuild() {
  const queryClient = useQueryClient();

  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [downloadInfo, setDownloadInfo] = useState<{
    progress: number | null, downloadedBytes: number | null, totalBytes: number | null, status: string | null
  }>({
    progress: null,
    downloadedBytes: null,
    totalBytes: null,
    status: null,
  });
  const abortControllerRef = useRef<AbortController | null>(null);

  const startDownload = useCallback(async () => {
    if (isDownloading) return;

    setError(null);
    setDownloadInfo({
      progress: null,
      downloadedBytes: null,
      totalBytes: null,
      status: null,
    });
    setIsDownloading(true);
    abortControllerRef.current = new AbortController();

    try {
      const stream = downloadLlamaCppBuild(abortControllerRef.current.signal);
      for await (const line of stream) {
        let parsed;
        try {
          parsed = JSON.parse(line);
        } catch {
          // sometimes we get multiple json with new line \n. And that can't be parsed directly. Or different json error.
          // So, here we just move on.
          continue;
        }
        setDownloadInfo({
          progress: parsed.progress,
          downloadedBytes: parsed.downloadedBytes,
          totalBytes: parsed.totalBytes,
          status: parsed.status,
        });
      }
      setDownloadInfo(prev => ({ ...prev, status: "downloaded" }));
      queryClient.invalidateQueries({ queryKey: ["llama_cpp_build_status"] });
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        setError(err as Error);
        setDownloadInfo(prev => ({ ...prev, status: "Failed" }));
      }
    } finally {
      setIsDownloading(false);
      abortControllerRef.current = null;
    }
  }, [isDownloading, queryClient]);

  const cancelDownload = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  return {
    isDownloading,
    ...downloadInfo,
    error,
    startDownload,
    cancelDownload,
  };
}

export function useDownloadHfModel() {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [downloadInfo, setDownloadInfo] = useState<{
    progress: number | null, downloadedBytes: number | null, totalBytes: number | null, status: string | null
  }>({
    progress: null,
    downloadedBytes: null,
    totalBytes: null,
    status: null,
  });
  const abortControllerRef = useRef<AbortController | null>(null);

  const startDownload = useCallback(
    async (repo_path: string) => {
      if (isDownloading) return;

      const [username, repoIdQuant] = (repo_path || "").split("/");

      if (!username || !repoIdQuant) {
        setError(new Error("Enter full path: username/repo (e.g. unsloth/repo)"));
        return;
      }

      const [repo_id, quant] = repoIdQuant.split(":");

      setError(null);
      setDownloadInfo({
        progress: null,
        downloadedBytes: null,
        totalBytes: null,
        status: null,
      });
      setIsDownloading(true);
      abortControllerRef.current = new AbortController();

      try {
        const stream = downloadHfModel(username, repo_id, quant, abortControllerRef.current.signal);
        for await (const line of stream) {
          let parsed;
          try {
            parsed = JSON.parse(line);
          } catch {
            // sometimes we get multiple json with new line \n. And that can't be parsed directly. Or different json error.
            // So, here we just move on.
            continue;
          }
          setDownloadInfo({
            progress: parsed.progress,
            downloadedBytes: parsed.downloadedBytes,
            totalBytes: parsed.totalBytes,
            status: parsed.status,
          });
        }
        setDownloadInfo(prev => ({ ...prev, status: "downloaded" }));
      } catch (err) {
        setError(err as Error);
        setDownloadInfo(prev => ({ ...prev, status: "Failed" }));
      } finally {
        setIsDownloading(false);
        abortControllerRef.current = null;
      }
    },
    [isDownloading]
  );

  const cancelDownload = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  return {
    isDownloading,
    ...downloadInfo,
    error,
    startDownload,
    cancelDownload,
  };
}