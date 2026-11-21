import * as React from 'react'
import { ProfileLink } from '@/components/agents/ProfileLink'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { agentColorVars } from '@/lib/agentColors'
import { formatAgo, formatAgoLong, formatDateTime, formatIn } from '@/lib/format'
import { modelLine, statusWord, type ProfileListItem, type ProfileNow } from './profilesModel'
import '@/styles/profiles.css'

/** The detail's head: who this is, its status, and the two ways to talk to it. */
export function ProfileDetailHeader({
  profile,
  onNewThread,
  onOpenLatestThread,
  hasThread,
}: {
  profile: ProfileListItem
  onNewThread: () => void
  onOpenLatestThread: () => void
  /** Whether the profile has any thread to open. */
  hasThread: boolean
}) {
  const color = agentColorVars(profile.colorIndex)
  const canStart = !profile.archived && profile.status.kind !== 'no-model'
  const why = profile.archived ? 'Archived: restore it under Profile before starting a thread' : profile.status.kind === 'no-model' ? 'It has no model yet: add one under Running' : undefined
  return (
    <header className="aw-pf-head" style={{ '--agent-accent': color.accent } as React.CSSProperties}>
      <div className="aw-pf-head-id">
        <span className="aw-agent-dot aw-pf-head-dot" aria-hidden="true" />
        <div className="aw-pf-head-text">
          <h2 className="aw-pf-head-name" title={profile.name}>
            {profile.name}
          </h2>
          <p className="aw-pf-head-sub">
            <span>{profile.charterName ? `${profile.charterName} charter` : 'No charter'}</span>
            <span aria-hidden="true">·</span>
            <span className="aw-pf-status" data-kind={profile.archived ? 'archived' : profile.status.kind}>
              <span className="aw-pf-status-mark" aria-hidden="true" />
              {profile.archived ? 'Archived' : statusWord(profile.status)}
            </span>
            <span aria-hidden="true">·</span>
            <span className="aw-pf-model">
              {profile.provider ? <ProviderMark provider={profile.provider} label={profile.providerLabel ?? profile.provider} size={12} /> : null}
              {modelLine(profile)}
            </span>
          </p>
        </div>
      </div>
      <div className="aw-pf-head-actions">
        <Button size="sm" variant="outline" disabled={!hasThread} onClick={onOpenLatestThread} title={hasThread ? undefined : 'It has no thread yet'}>
          Open latest thread
        </Button>
        <Button size="sm" variant="primary" disabled={!canStart} onClick={onNewThread} title={why}>
          <Icon name="add" size={14} />
          New thread
        </Button>
      </div>
    </header>
  )
}

/** What the profile is doing, one line: the current task (and build) when it is working, else its
 *  last run. Each link is named for where it goes (P7). */
export function ProfileNowStrip({
  now,
  at,
  profileHref,
  onOpenProfile,
  onOpenTask,
  onOpenBuild,
}: {
  now: ProfileNow
  at: Date
  /** The address of another profile's page, for "Reviewing Builder's work". */
  profileHref: (name: string) => string
  onOpenProfile: (name: string) => void
  onOpenTask: () => void
  onOpenBuild: () => void
}) {
  let body: React.ReactNode
  let taskLink: string | null = null
  let buildLink: string | null = null
  switch (now.kind) {
    case 'working':
    case 'reviewing':
      taskLink = now.task
      buildLink = now.build ?? null
      body = (
        <>
          <span className="aw-pf-now-what">
            {now.kind === 'working' ? 'Working on ' : 'Reviewing '}
            {now.reviewing ? (
              <>
                <ProfileLink name={now.reviewing} href={profileHref(now.reviewing)} onOpen={() => onOpenProfile(now.reviewing!)} className="aw-pf-now-link">
                  {now.reviewing}
                </ProfileLink>
                ’s work on{' '}
              </>
            ) : null}
            <strong>{now.task}</strong>
            {now.build ? <> in {now.build}</> : null}
          </span>
          <span className="aw-pf-now-when" title={`Since ${formatDateTime(now.since, at)}`}>
            for {formatAgo(now.since, at)}
          </span>
        </>
      )
      break
    case 'held':
      taskLink = now.lastTask ?? null
      body = (
        <>
          <span className="aw-pf-now-what">
            Held, {now.reason}
            {now.lastTask ? (
              <>
                {' '}
                while on <strong>{now.lastTask}</strong>
              </>
            ) : null}
          </span>
          {now.until ? (
            <span className="aw-pf-now-when" title={`Resumes ${formatDateTime(now.until, at)}`}>
              resumes {formatIn(now.until, at)}
            </span>
          ) : null}
        </>
      )
      break
    case 'last-run':
      taskLink = now.task ?? null
      body = (
        <>
          <span className="aw-pf-now-what">
            Last run {now.task ? <>on <strong>{now.task}</strong></> : null}
          </span>
          <span className="aw-pf-now-when" title={formatDateTime(now.at, at)}>
            {formatAgoLong(now.at, at)}
          </span>
        </>
      )
      break
    case 'never':
      body = <span className="aw-pf-now-what">Has not run yet. A new thread gives it its first work.</span>
      break
  }
  return (
    <section className="aw-pf-now" aria-label="Now">
      <span className="aw-pf-now-label">Now</span>
      {body}
      <span className="aw-pf-now-links">
        {taskLink ? (
          <button type="button" data-slot="open-task" className="aw-link aw-link-inline" aria-label={`Open task: ${taskLink}`} onClick={onOpenTask}>
            Open task
            <Icon name="arrow_forward" size={11} />
          </button>
        ) : null}
        {buildLink ? (
          <button type="button" data-slot="open-build" className="aw-link aw-link-inline" aria-label={`Open build: ${buildLink}`} onClick={onOpenBuild}>
            Open build
            <Icon name="arrow_forward" size={11} />
          </button>
        ) : null}
      </span>
    </section>
  )
}
