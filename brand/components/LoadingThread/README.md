# LoadingThread

The brand's one motion: the loop's thread **weaves through**. It draws in from the left end, through the loop, to the right end, then its tail follows it out the far end, on a continuous 1.8s cycle with no fade. The operator picked it over "draw and fade" and "shuttle" in the thread lab (2026-10-23, https://claude.ai/artifact/GniK2BGBQJzh2ouG3boTpN).

- **It is every loading state in the app.** The app's `LoadingThread` component (`hub/ui/src/components/common/LoadingThread.tsx`) replaces every skeleton placeholder and spinner.
- **Provide:** a label for assistive tech ("Loading tasks") and a size: `panel` (64px, master drawing, centred where the content will appear), `inline` (24px, small drawing, label shown beside it) or `control` (16px, small drawing, in the button's text colour).
- It stays invisible for the first 300ms, so quick loads never flash it.
- The crossing gap opens only once the second stroke reaches it, so the thread visibly passes under itself.
- Under `prefers-reduced-motion` the mark stands still, fully drawn.
- **Don't:** speed it up, colour it anything but `madder` (or the text colour at control size), or use it as decoration on a page that is not loading.
