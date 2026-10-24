import ThreadLoomScreen from './ThreadLoom'
import '../loom.css'
import type { ScreenProps } from '../routes'

/** Thread tab: the loom, fed this repository's chapters (mock/thread-chapters-fixture.json). */
export default function ThreadScreen({ now }: ScreenProps) {
  return <ThreadLoomScreen now={now} />
}
