import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { chatApi, getWorkspaces, getWorkspace, createWorkspace, deleteWorkspace, getAllWorkspacesItems, getWorkspaceItems, getModels, deleteWorkspaceItem } from "@/lib/api";
import { Workspace } from "@/lib/types";

// Models to Display
export function useModelsList() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => getModels(),
  });
}

export function useChat(workspaceId: string | null, chatId: string | null) {
  return useQuery({
    queryKey: ["chat", workspaceId, chatId],
    queryFn: () => chatApi.getById(workspaceId!, chatId!),
    enabled: !!workspaceId && !!chatId,
  });
}

export function useWorkspace(workspaceId: string | null) {
  return useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => getWorkspace(workspaceId!),
    enabled: !!workspaceId,
  });
}


export function useWorkspaces(page = 1, limit = 10) {
  return useQuery({
    queryKey: ["workspaces", page, limit],
    queryFn: () => getWorkspaces(page, limit),
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Workspace) => createWorkspace(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace"] });
    }
  });
}

export function useAllWorkspacesItems(page = 1, limit = 10) {
  return useQuery({
    queryKey: ["workspace-items", page, limit],
    queryFn: () => getAllWorkspacesItems(page, limit),
  })
}


export function useWorkspaceItems(workspaceId: string, page = 1, limit = 10) {
  return useQuery({
    queryKey: ["workspace-items", workspaceId],
    queryFn: () => getWorkspaceItems(workspaceId, page, limit),
    enabled: !!workspaceId,
  });
}


export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workspaceId: string) => deleteWorkspace(workspaceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace"] });
    }
  });
}

export function useDeleteWorkspaceItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ workspaceId, itemId, type }: { workspaceId: string; itemId: string; type: string }) =>
      deleteWorkspaceItem(workspaceId, itemId, type),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace-items"] });
    },
  });
}

export function useCreateChat(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: { title?: string }) =>
      chatApi.create(workspaceId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspace", workspaceId] });
    },
  });
}


export function useDeleteChat() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ workspaceId, chatId }: { workspaceId: string; chatId: string }) => chatApi.delete(workspaceId, chatId),
    onSuccess: (_, { workspaceId, chatId }) => {
      queryClient.removeQueries({ queryKey: ["chat", workspaceId, chatId] });
    },
  });
}