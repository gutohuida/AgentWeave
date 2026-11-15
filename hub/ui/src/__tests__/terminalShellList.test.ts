import { afterEach, describe, expect, it, vi } from 'vitest'
import * as client from '@/api/client'
import { PAGE_ID, listShells } from '@/api/terminal'

/* FR-9: after a reload the Hub still lists the previous page's shell for its few seconds of grace.
 * The tab must not adopt it, so it opens one fresh shell instead of showing one about to end. */

const shell = (id: string, page: string | null) => ({
  id,
  conversation_id: 'c1',
  shell: 'pwsh',
  label: 'PowerShell 7',
  wsl: false,
  location: 'root',
  directory: 'C:/p',
  running: true,
  exit_code: null,
  page,
})

afterEach(() => vi.restoreAllMocks())

describe('listShells', () => {
  it('leaves out a shell the previous page load opened', async () => {
    vi.spyOn(client, 'getJson').mockResolvedValue({ shells: [shell('old', 'page-before-the-reload')] })
    expect(await listShells('p1', 'c1')).toEqual([])
  })

  it('keeps this page load\'s shells and ones no page owns', async () => {
    vi.spyOn(client, 'getJson').mockResolvedValue({
      shells: [shell('old', 'page-before-the-reload'), shell('mine', PAGE_ID), shell('api', null)],
    })
    expect((await listShells('p1', 'c1')).map((s) => s.id)).toEqual(['mine', 'api'])
  })
})
