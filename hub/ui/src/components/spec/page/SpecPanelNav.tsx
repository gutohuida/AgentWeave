import * as React from "react";
import { Icon } from "@/components/common/Icon";
import {
  anchors,
  countFilters,
  EVIDENCE_LABEL,
  NO_DOCUMENT_FILTERS,
  TASK_STATUS_LABEL,
  type DocumentFilters,
  type ListPreferences,
  type SpecDocumentView,
  type SpecListEntry,
} from "./model";
import { SpecDocList, SpecDocSwitcher } from "./SpecDocList";
import { DocumentFilterBar } from "./SpecDocumentBody";
import "@/styles/spec-page.css";

/** The document list, when the panel can switch documents (the Spec tab's list, as a popover). */
export interface PanelListProps {
  entries: SpecListEntry[];
  prefs: ListPreferences;
  onPrefsChange: (next: ListPreferences) => void;
  onNew: () => void;
}

export interface SpecPanelNavProps {
  doc: SpecDocumentView;
  tab: "document" | "tasks" | "builds";
  filters: DocumentFilters;
  onFiltersChange: (next: DocumentFilters) => void;
  /** The anchor in view, from the panel's scroller. */
  active: string | null;
  onJump: (anchor: string) => void;
  onOpenDocument: (path: string) => void;
  now: Date;
}

const SECTIONS: Array<{ id: string; label: string }> = [
  { id: "summary", label: "Summary" },
  { id: "problem", label: "Problem" },
  { id: "scope", label: "Scope" },
  { id: "requirements", label: "Requirements" },
  { id: "questions", label: "Questions" },
];

/**
 * The conversation panel's navigation: switch documents without leaving the conversation, jump to
 * any section, requirement or task from a strip that shows each one's state, and filter and order
 * from one tray whose active choices stay visible as chips.
 */
export function SpecPanelNav(props: SpecPanelNavProps) {
  const { doc, tab, filters } = props;
  const [trayOpen, setTrayOpen] = React.useState(false);
  const agents = Array.from(
    new Set(
      doc.tasks.map((t) => t.agent).filter((a): a is string => Boolean(a)),
    ),
  ).sort();
  const active = countFilters(filters);

  const chips: Array<{ key: keyof DocumentFilters; label: string }> = [];
  if (filters.evidence !== "any")
    chips.push({ key: "evidence", label: EVIDENCE_LABEL[filters.evidence] });
  if (filters.task !== "any")
    chips.push({
      key: "task",
      label: `Task: ${doc.tasks.find((t) => t.key === filters.task)?.title ?? filters.task}`,
    });
  if (filters.status !== "any")
    chips.push({ key: "status", label: TASK_STATUS_LABEL[filters.status] });
  if (filters.agent !== "any")
    chips.push({ key: "agent", label: filters.agent });
  if (filters.order !== NO_DOCUMENT_FILTERS.order)
    chips.push({ key: "order", label: "By status" });

  // The strip's items for the open tab, in document order, and where the reader is among them.
  const items =
    tab === "tasks"
      ? doc.tasks.map((t, i) => ({
          anchor: anchors.task(t.key),
          label: String(i + 1),
          title: t.title,
          tone: `var(--sp-status-${t.status ?? "pending"})`,
        }))
      : doc.requirements.map((r) => ({
          anchor: anchors.requirement(r.identifier),
          label: r.identifier.replace("FR-", ""),
          title: `${r.identifier} · ${EVIDENCE_LABEL[r.evidence]}`,
          tone: `var(--sp-ev-${r.evidence})`,
        }));
  const at = items.findIndex((i) => i.anchor === props.active);
  const step = (by: number) => {
    const next =
      items[
        Math.min(
          items.length - 1,
          Math.max(0, (at < 0 ? (by > 0 ? -1 : items.length) : at) + by),
        )
      ];
    if (next) props.onJump(next.anchor);
  };

  if (tab === "builds") return null;
  return (
    <div className="aw-sp-pnav">
      <>
        {tab === "document" ? (
          <div
            className="aw-sp-pnav-sections"
            role="navigation"
            aria-label="Sections"
          >
            {SECTIONS.filter(
              (s) => s.id !== "questions" || doc.openQuestions.length,
            ).map((s) => (
              <button
                key={s.id}
                data-slot="pnav-section"
                type="button"
                className="aw-sp-pnav-section"
                data-active={
                  props.active === anchors.section(s.id) ? "true" : "false"
                }
                onClick={() => props.onJump(anchors.section(s.id))}
              >
                {s.label}
              </button>
            ))}
          </div>
        ) : null}

        <div
          className="aw-sp-pnav-strip"
          role="navigation"
          aria-label={tab === "tasks" ? "Tasks" : "Requirements"}
        >
          <button
            data-slot="pnav-step"
            type="button"
            className="aw-sp-pnav-step"
            aria-label="Previous"
            onClick={() => step(-1)}
            disabled={at === 0}
          >
            <Icon name="chevron_left" size={14} />
          </button>
          <div className="aw-sp-pnav-dots">
            {items.map((i) => (
              <button
                key={i.anchor}
                data-slot="pnav-dot"
                type="button"
                className="aw-sp-pnav-dot"
                style={{ "--tone": i.tone } as React.CSSProperties}
                data-active={i.anchor === props.active ? "true" : "false"}
                title={i.title}
                onClick={() => props.onJump(i.anchor)}
              >
                {i.label}
              </button>
            ))}
          </div>
          <button
            data-slot="pnav-step"
            type="button"
            className="aw-sp-pnav-step"
            aria-label="Next"
            onClick={() => step(1)}
            disabled={at === items.length - 1}
          >
            <Icon name="chevron_right" size={14} />
          </button>
          <span className="aw-sp-pnav-pos">
            {at >= 0 ? `${at + 1} of ${items.length}` : `${items.length}`}
          </span>
        </div>

        <div className="aw-sp-pnav-filter">
          <button
            data-slot="pnav-filter"
            type="button"
            className="aw-sp-pnav-filter-btn"
            aria-expanded={trayOpen}
            data-on={active || trayOpen ? "true" : "false"}
            onClick={() => setTrayOpen((o) => !o)}
          >
            <Icon name="filter_list" size={13} />
            Filter & sort
            {active ? <span className="aw-sp-pnav-count">{active}</span> : null}
          </button>
          {chips.map((c) => (
            <button
              key={c.key}
              data-slot="pnav-chip"
              type="button"
              className="aw-sp-pnav-chip"
              title="Remove this filter"
              onClick={() =>
                props.onFiltersChange({
                  ...filters,
                  [c.key]: NO_DOCUMENT_FILTERS[c.key],
                })
              }
            >
              <span className="truncate">{c.label}</span>
              <Icon name="close" size={11} />
            </button>
          ))}
          {chips.length > 1 ? (
            <button
              data-slot="pnav-clear"
              type="button"
              className="aw-sp-pnav-clear"
              onClick={() => props.onFiltersChange(NO_DOCUMENT_FILTERS)}
            >
              Clear all
            </button>
          ) : null}
        </div>
        {trayOpen ? (
          <div className="aw-sp-pnav-tray">
            <DocumentFilterBar
              doc={doc}
              filters={filters}
              agents={agents}
              showRequirementFilters={tab === "document"}
              showTaskFilters={tab === "tasks"}
              onChange={props.onFiltersChange}
            />
          </div>
        ) : null}
      </>
    </div>
  );
}

/** The panel's document switcher: the Spec tab's list, searchable, filterable and ordered, as a popover. */
export function SpecPanelDocSwitcher({
  doc,
  list,
  onOpenDocument,
  now,
}: {
  doc: SpecDocumentView;
  list: PanelListProps;
  onOpenDocument: (path: string) => void;
  now: Date;
}) {
  return (
    <div className="aw-sp-pnav aw-sp-pnav-top">
      <div className="aw-sp-pnav-docs">
        <SpecDocSwitcher title={doc.title}>
          <SpecDocList
            entries={list.entries}
            active={doc.path}
            prefs={list.prefs}
            onPrefsChange={list.onPrefsChange}
            onOpen={onOpenDocument}
            onNew={list.onNew}
            now={now}
            variant="popover"
          />
        </SpecDocSwitcher>
      </div>
    </div>
  );
}
