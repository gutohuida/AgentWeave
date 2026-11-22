import * as React from "react";
import { useAgents } from "@/api/agents";
import { useBuildRead } from "@/api/buildRead";
import { useOpenStalls } from "@/api/stalls";
import { readableApiError } from "@/api/client";
import {
  agentDestination,
  buildDestination,
  projectDestination,
  type WorkspaceDestination,
} from "@/lib/navigation";
import { BuildView } from "./BuildView";
import type { BuildAddress } from "./buildViewModel";

export interface BuildViewContainerProps {
  projectId: string;
  buildId: string;
  /** The task expanded, the run whose trace is open and the filter, from the destination. */
  address: BuildAddress;
  onNavigate: (
    destination: WorkspaceDestination,
    options?: { replace?: boolean },
  ) => void;
}

/** Ticks, so a running run's duration and "updated 12s ago" stay true between reads. */
function useNow(everyMs = 15_000): Date {
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), everyMs);
    return () => window.clearInterval(timer);
  }, [everyMs]);
  return now;
}

/** The build view in the app: the address in (the destination), the read in (`useBuildRead`, kept
 *  fresh by the event stream and a short backstop), callbacks out. The read is the one the compact
 *  summaries use, so their figures cannot differ from this view's. */
export function BuildViewContainer({
  projectId,
  buildId,
  address,
  onNavigate,
}: BuildViewContainerProps) {
  const { data: read, error, isError, refetch } = useBuildRead(buildId);
  const { data: agents = [], error: agentsError } = useAgents();
  const { data: stalls = [], error: stallsError } = useOpenStalls();
  const now = useNow();
  const colorIndexOf = React.useCallback(
    (name: string) => agents.find((a) => a.name === name)?.color_index,
    [agents],
  );
  const message = isError
    ? readableApiError(
        error,
        "The Hub did not answer: the build could not be read.",
      )
    : null;
  const status = read ? "ready" : isError ? "error" : "loading";
  return (
    // Without the agent list only the agents' colours are lost; `contents` keeps the wrapper out of the layout.
    <div
      style={{ display: "contents" }}
      data-agents-failed={agentsError ? "true" : undefined}
    >
      <BuildView
        read={read ?? null}
        status={status}
        errorMessage={message}
        refreshError={read && message ? message : null}
        now={now}
        address={address}
        // Opening a trace adds a history entry, so Back closes it before leaving the build; every
        // other change (expanding a task, a filter, closing a trace) replaces the entry it is on.
        onAddressChange={(next) =>
          onNavigate(buildDestination(projectId, buildId, next), {
            replace: !(next.run && !address.run),
          })
        }
        onRetry={() => void refetch()}
        onOpenDocument={() =>
          onNavigate(
            projectDestination(
              projectId,
              "spec",
              read?.build.document_path ?? null,
            ),
          )
        }
        onOpenConversation={(run) =>
          onNavigate(
            agentDestination(projectId, run.agent, run.conversation_id),
          )
        }
        colorIndexOf={colorIndexOf}
        stalls={stalls}
        stallsUnread={Boolean(stallsError)}
      />
    </div>
  );
}
