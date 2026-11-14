import { setWatchedAction } from "@/app/markets/actions";

/** A plain form posting to a server action, so it works without client JavaScript. */
export function WatchButton({
  instrumentId,
  watched,
  compact = false,
}: {
  instrumentId: string;
  watched: boolean;
  compact?: boolean;
}) {
  return (
    <form action={setWatchedAction}>
      <input type="hidden" name="instrument_id" value={instrumentId} />
      <input type="hidden" name="watched" value={watched ? "0" : "1"} />
      <button
        type="submit"
        aria-pressed={watched}
        className={`border-line hover:border-accent rounded border font-mono text-xs ${
          compact ? "px-1.5 py-0.5" : "px-2.5 py-1"
        } ${watched ? "text-accent" : "text-muted"}`}
      >
        {watched ? "Watching" : "Watch"}
      </button>
    </form>
  );
}
