# LoadingThread

The brand's one motion: the loop's thread draws itself from the left end, through the loop, to the right end, holds, fades, and repeats every 1.6s.

- **Provide:** a size (24px inline, 64px in an empty panel) and a label for assistive tech ("Loading").
- Use it for whole-panel or first loads that take longer than about half a second; start it with the app's delayed-loader class so quick loads never flash it. Short inline waits keep the app's ordinary spinner.
- Under `prefers-reduced-motion` the mark stands still, fully drawn.
- **Don't:** loop it faster, colour it anything but `madder`, or use it as decoration on a page that is not loading.
