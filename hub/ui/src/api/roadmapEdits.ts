import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postJson } from "./client";
import { useConfigStore } from "@/store/configStore";

/** The operator's edits to an approved roadmap's slices (`hub/hub/roadmap_edits.py`): a move and a
 *  removal apply at once and are recorded in the roadmap's history; "Add a slice" opens a
 *  conversation with an agent, who adds it through its tool. There is no call that adds a slice
 *  from a form. */
function useRoadmapEdit<TArgs>(
  call: (projectId: string, args: TArgs) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  const { selectedProjectId: projectId } = useConfigStore();
  return useMutation({
    mutationFn: (args: TArgs) => call(projectId ?? "", args),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
}

/** Move a Not drafted or Drafting slice to a 1-based position. */
export function useMoveSlice() {
  return useRoadmapEdit<{ roadmap: string; slice: string; position: number }>(
    (projectId, { roadmap, slice, position }) =>
      postJson(`/api/v1/projects/${projectId}/project/documents/slices/move`, {
        path: roadmap,
        slice,
        position,
      }),
  );
}

/** Remove a Not drafted slice no document names. */
export function useRemoveSlice() {
  return useRoadmapEdit<{ roadmap: string; slice: string }>(
    (projectId, { roadmap, slice }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/slices/remove`,
        { path: roadmap, slice },
      ),
  );
}

/** Add a slice: open a conversation with the chosen agent (default the roadmap's author). */
export function useStartSliceConversation() {
  return useRoadmapEdit<{ roadmap: string; agent?: string }>(
    (projectId, { roadmap, agent }) =>
      postJson(
        `/api/v1/projects/${projectId}/project/documents/slices/conversation`,
        { path: roadmap, agent },
      ),
  );
}
