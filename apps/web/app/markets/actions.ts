"use server";

import { revalidatePath } from "next/cache";

import { setWatched } from "@/lib/market";

export async function setWatchedAction(formData: FormData): Promise<void> {
  const instrumentId = formData.get("instrument_id");
  if (typeof instrumentId !== "string" || instrumentId === "") return;
  // A failed write is not hidden: the page re-reads the watchlist from the API, so the
  // button keeps showing the state the API actually holds.
  await setWatched(instrumentId, formData.get("watched") === "1");
  revalidatePath("/", "layout");
}
